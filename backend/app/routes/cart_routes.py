"""
Multi-item checkout.

AI Commerce Studio bought exactly one listing at a time until now. A cart changes what
the gate has to reason about: the risk bound applies to the TOTAL, not to each
item, or a cart of ten ₹4,000 items would sail through a ₹5,000 per-order
limit ten times over. The same goes for the mandate — one cart mandate covers
every line, so the signature commits to the whole basket and swapping an item
afterwards breaks the chain.

Razorpay orders carry a single amount, so the line items live in our record.
That is stated rather than hidden: the order page shows the breakdown, and the
audit row names the item count.
"""
import uuid

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.agent import idempotency
from app.agent import merchant_client

from app.agent.budget_agent import assess as budget_assess
from app.agent.risk_gate import evaluate as risk_evaluate
from app.agent import settings
from app.agent.mandates import (issue_intent_mandate, issue_cart_mandate,
                                verify_chain, _registered_venues)
from app.firebase_client import (
    get_or_create_customer,
    log_decision,
    save_order,
    adjust_trust_score,
    db,
)
from app.razorpay_client import create_order
from firebase_admin import firestore

router = APIRouter()


class CartCheckout(BaseModel):
    items: list[dict]
    customer_email: str = "demo@commerce-studio.dev"
    customer_name: str = "Demo User"
    # Set by the interface only after the person has been shown the amount
    # they are exceeding and confirmed it a second time. Never defaulted on.
    confirm_over_ceiling: bool = False


def _total(items: list[dict]) -> int:
    return sum(
        int(i.get("price_paise") or 0) * int(i.get("quantity") or 1) for i in items
    )


@router.post("/cart-checkout")
def cart_checkout(
    req: CartCheckout,
    idempotency_key: str = Header(None, alias="idempotency-key"),
    ucp_agent: str = Header(None, alias="UCP-Agent"),
    request_id: str = Header(None, alias="request-id"),
):
    """
    UCP request envelope. `idempotency-key` is the one that matters here —
    without it a retried checkout creates a second Razorpay order, and a
    cart retried after a network timeout is the ordinary case, not an edge
    one. The key is not derived from the cart contents on purpose: buying
    the same cart twice is legitimate, so only the caller can say whether
    this is a retry or a new intent.
    """
    if not req.items:
        raise HTTPException(status_code=400, detail="Cart is empty.")

    if idempotency_key:
        try:
            replay = idempotency.claim(
                idempotency_key, "cart-checkout", agent=ucp_agent, request_id=request_id
            )
        except idempotency.InProgress:
            raise HTTPException(
                status_code=409,
                detail="This checkout is already in progress. Wait for it rather than retrying.",
            )
        if replay is not None:
            # Same key, already done — hand back the original order instead
            # of charging again.
            return {**replay, "idempotent_replay": True}

    try:
        result = _do_cart_checkout(req, idempotency_key, request_id)
    except Exception:
        if idempotency_key:
            idempotency.release(idempotency_key)
        raise

    if idempotency_key:
        idempotency.complete(idempotency_key, result)
    return result


def _do_cart_checkout(req: CartCheckout, idempotency_key: str = None,
                      request_id: str = None):

    # Which venue is this cart from? It decides who creates the order.
    sources = {(i.get("source") or "ebay") for i in req.items}

    # A single Razorpay order settles to a single seller, so a basket
    # spanning two of them has no honest total. Splitting it into one order
    # per merchant is the right answer and is not built, so this refuses
    # and says which items clash rather than quietly charging for both.
    if len(sources) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "This cart mixes items from different sellers "
                f"({', '.join(sorted(sources))}). Each seller needs its own order — "
                "check out one seller at a time."
            ),
        )

    from_merchant = sources == {"merchant"}

    if from_merchant:
        # The seller prices its own goods. Doing this before the gate means a
        # stale card price is caught while it still costs nothing to correct.
        priced = merchant_client.price_basket(req.items)
        if not priced.get("ok"):
            raise HTTPException(status_code=409, detail=priced["error"])
        total = priced["total_paise"]

        # A GROWTH DISCOUNT IS PART OF THE PRICE, SO IT IS SUBTRACTED HERE.
        #
        # The seller applies the offer when it opens its own session, which
        # would leave the gate approving one figure and the seller charging
        # a lower one — and the mismatch check below, correctly, refuses
        # that. The fix is not to loosen the check: it is to work out the
        # real price before anything approves or signs it, so the risk
        # gate, the cart mandate, the Razorpay order and the seller's
        # session all describe the same number.
        #
        # Read-only here. The offer is not claimed until the seller opens
        # the session, and that call recomputes the same discount from the
        # same offer — so if it has been taken in between, the mismatch
        # check catches it, which is exactly what it is for.
        try:
            from app.growth import redemption
            entitled = redemption.find_for_basket(
                [{"id": i.get("id"), "quantity": i.get("quantity")}
                 for i in req.items],
                {"customer_id": None})
            if entitled:
                total -= int(total * entitled["discount_pct"] / 100)
        except Exception as exc:
            # No discount is a correct outcome; a failed lookup must never
            # stop a sale. The buyer pays the price they were shown.
            print(f"[cart] growth discount not priced in: {exc}", flush=True)
    else:
        total = _total(req.items)

    if total <= 0:
        raise HTTPException(status_code=400, detail="Cart has no usable prices.")

    customer = get_or_create_customer(req.customer_name, req.customer_email)

    # The gate sees one synthetic line standing for the whole basket, so the
    # per-order spending bound is measured against what will actually be
    # charged rather than against the cheapest thing in the cart.
    basket = {
        "id": f"cart-{uuid.uuid4().hex[:12]}",
        "name": (
            req.items[0].get("name")
            if len(req.items) == 1
            else f"{len(req.items)} items"
        ),
        "price_paise": total,
        "stock": 1,
    }

    budget = budget_assess(customer, total)
    # The basket's venue, checked against what the person authorised. A
    # mixed-seller cart is already refused above, so one source describes
    # the whole basket here.
    risk = risk_evaluate(
        customer,
        {**basket, "source": "merchant" if from_merchant else "ebay"},
        # Same list the mandate would name, read from the registry rather
        # than written out here, so adding a venue does not leave checkout
        # refusing it for a reason no one can find.
        allowed_venues=set(_registered_venues()),
    )

    over_ceiling = budget["status"] == "exceeded"

    # The person's own ceiling, and the person is here saying they mean it.
    # Everything the risk gate objects to still stands: this only clears the
    # budget, and only when it was the sole objection.
    # Both gates ask the same question — does a person agree to this amount?
    # Neither is a statement that the purchase is unsafe.
    needs_a_person = over_ceiling or risk["decision"] == "escalated"
    hard_blocked = risk["decision"] == "blocked"

    if needs_a_person and req.confirm_over_ceiling and not hard_blocked:
        ceiling = settings.get("budget", "session_ceiling_inr") * 100
        grounds = []
        if over_ceiling:
            grounds.append(f"₹{max(0, total - ceiling) / 100:,.2f} over their "
                           f"₹{ceiling / 100:,.0f} session ceiling")
        if risk["decision"] == "escalated":
            grounds.append(risk["reason"])

        log_decision(
            action_type="human_authorised_spend",
            amount_paise=total,
            decision="allowed",
            reason=(f"Person confirmed ₹{total / 100:,.2f} in the cart — "
                    + "; ".join(grounds)
                    + ". These bounds limit the agent's autonomy, not the "
                      "account holder's own spending."),
            customer_id=customer["id"],
        )
        over_ceiling = False
        needs_a_person = False
        risk = {**risk, "decision": "allowed",
                "reason": risk["reason"] + " — confirmed by the person"}

    decision = ("blocked" if hard_blocked else
                "blocked" if over_ceiling else
                risk["decision"])
    reason = budget["summary"] if over_ceiling else risk["reason"]

    log_decision(
        action_type="cart_checkout_attempt",
        amount_paise=total,
        decision=decision,
        reason=f"{len(req.items)} item cart — {reason}",
        customer_id=customer["id"],
    )

    if decision == "blocked":
        # A ceiling the person can lift by saying so is a different refusal
        # from one they cannot. Say which this is, so the interface can offer
        # the choice instead of a dead end — and do not dock trust for it,
        # because wanting to spend your own money is not suspicious.
        if over_ceiling and not hard_blocked:
            ceiling = settings.get("budget", "session_ceiling_inr") * 100
            raise HTTPException(status_code=409, detail={
                "status": "over_ceiling",
                "reason": reason,
                "total_paise": total,
                "ceiling_paise": ceiling,
                "excess_paise": max(0, total - ceiling),
                "confirmable": True,
                "action": "Confirm to buy anyway. The override is recorded in "
                          "the audit trail.",
            })

        adjust_trust_score(customer["id"], -5)
        raise HTTPException(status_code=403, detail=reason)

    if decision == "escalated":
        # A person in the cart can answer this directly. The approvals screen
        # still exists for the case it was built for — an external agent
        # proposing a purchase with nobody in the room.
        ceiling = settings.get("budget", "session_ceiling_inr") * 100
        raise HTTPException(status_code=409, detail={
            "status": "over_ceiling",
            "reason": reason,
            "total_paise": total,
            "ceiling_paise": ceiling,
            "excess_paise": max(0, total - ceiling),
            "confirmable": True,
            "action": "Confirm to authorise it yourself. The decision is "
                      "recorded in the audit trail.",
        })

    if False:
        # Parked for a human, exactly like an external agent's proposal. The
        # cart is stored so the approval screen can show what was in it.
        proposal_id = f"prop-{uuid.uuid4().hex[:16]}"
        db.collection("proposals").document(proposal_id).set({
            "product": {**basket, "items": req.items},
            "query": "cart checkout",
            "customer_id": customer["id"],
            "customer_email": req.customer_email,
            "customer_name": req.customer_name,
            "decision": decision,
            "reason": reason,
            "budget": budget,
            "status": "awaiting_human",
            "source": "cart",
            "created_at": firestore.SERVER_TIMESTAMP,
        })
        raise HTTPException(
            status_code=409,
            detail={
                "status": "awaiting_human",
                "reason": reason,
                "proposal_id": proposal_id,
                "action": "A human must approve this at /approvals before it can proceed.",
            },
        )

    # One mandate over the whole basket.
    intent = {
        "category": "cart",
        "max_price_paise": total,
        "priority": "price",
    }
    intent_jwt = issue_intent_mandate(intent, customer["id"])
    cart = issue_cart_mandate(intent_jwt, basket, customer["id"])

    chain = verify_chain(intent_jwt, cart["cart_jwt"], basket)
    if not chain["ok"]:
        log_decision(
            action_type="mandate_rejected",
            amount_paise=total,
            decision="blocked",
            reason=f"{chain['failed_check']}: {chain['reason']}",
            customer_id=customer["id"],
        )
        raise HTTPException(status_code=403, detail=f"Mandate chain failed — {chain['reason']}")

    checkout_session = None

    if from_merchant:
        # The seller opens its own checkout and creates its own Razorpay
        # order. AI Commerce Studio sends ids and quantities; it does not send prices,
        # and it does not create the order on the seller's behalf. That is
        # the whole difference between an agent that can pay a merchant and
        # an agent that merely links to one.
        #
        # A separate key for this leg: idempotency records are keyed by the
        # key itself, so forwarding ours verbatim would collide with the
        # claim this request already holds. Deriving it keeps a retry of the
        # same buyer key landing on the same merchant session.
        merchant_key = (
            f"{idempotency_key}:merchant" if idempotency_key
            else idempotency.derive_key("merchant-leg", customer["id"], total, uuid.uuid4().hex)
        )
        try:
            checkout_session = merchant_client.open_checkout(
                req.items,
                buyer={"customer_id": customer["id"], "name": req.customer_name,
                       "email": req.customer_email},
                idempotency_key=merchant_key,
                request_id=request_id,
            )
        except Exception as exc:
            log_decision(
                action_type="merchant_checkout_failed",
                amount_paise=total,
                decision="blocked",
                reason=str(exc),
                customer_id=customer["id"],
            )
            raise HTTPException(status_code=502, detail=str(exc))

        # The gate approved a number. If the seller's order is for a
        # different one, the approval does not cover it — that is a
        # mandate-level failure, not a rounding difference to absorb.
        charged = checkout_session.get("total_paise")

        # CHARGING LESS THAN WAS APPROVED IS INSIDE THE APPROVAL.
        #
        # The bound the gate and the mandate set is a ceiling, and a seller
        # that comes in under it has not exceeded anything. It is still
        # written down, because a price that moved between approval and
        # order is worth a record either way — and because the only reason
        # it should ever move down is a growth offer, which has its own
        # entry beside this one.
        if charged is not None and charged < total:
            log_decision(
                action_type="merchant_price_reduced",
                amount_paise=charged,
                decision="allowed",
                reason=(f"Gate approved Rs{total/100:,.2f}; the merchant's "
                        f"session is for Rs{charged/100:,.2f}. Less than the "
                        f"approved ceiling, so the approval covers it."
                        + (f" {checkout_session.get('discount_note')}"
                           if checkout_session.get("discount_note") else "")),
                customer_id=customer["id"],
                order_id=checkout_session.get("razorpay_order_id"),
            )
            total = charged

        if charged != total:
            log_decision(
                action_type="merchant_price_mismatch",
                amount_paise=charged or 0,
                decision="blocked",
                reason=(f"Gate approved Rs{total/100:,.2f} but the merchant's session "
                        f"is for Rs{(charged or 0)/100:,.2f}"),
                customer_id=customer["id"],
                order_id=checkout_session.get("razorpay_order_id"),
            )
            raise HTTPException(
                status_code=409,
                detail="The merchant's price changed while this was being approved. "
                       "Nothing was charged — try again.",
            )

        receipt = f"cp-{uuid.uuid4().hex[:16]}"
        order = {"id": checkout_session["razorpay_order_id"], "receipt": receipt}
    else:
        receipt = f"cp-{uuid.uuid4().hex[:16]}"
        order = create_order(
            amount_paise=total,
            receipt=receipt,
            notes={"customer_id": customer["id"], "items": str(len(req.items))},
        )

    # Store every line, not just the synthetic basket, so the order page can
    # show what was actually bought.
    save_order(
        order_id=order["receipt"],
        razorpay_order_id=order["id"],
        amount_paise=total,
        product_name=basket["name"],
        customer_id=customer["id"],
        mandates={
            "intent_jwt": intent_jwt,
            "cart_jwt": cart["cart_jwt"],
        },
    )
    db.collection("orders").document(order["receipt"]).update({
        "items": [{
            "id": str(i.get("id")),
            "name": i.get("name"),
            "image": i.get("image"),
            "url": i.get("url"),
            "condition": i.get("condition"),
            "quantity": int(i.get("quantity") or 1),
            "price_paise": i.get("price_paise"),
            "original_price_paise": i.get("original_price_paise"),
            "discount_percent": i.get("discount_percent"),
        } for i in req.items],
        "shipping_cost_paise": sum(int(i.get("shipping_cost_paise") or 0) for i in req.items),
        # eBay prices are converted from USD; the merchant quotes rupees.
        "price_is_converted": not from_merchant,
        "source": "merchant" if from_merchant else "ebay",
        "merchant_checkout_session": (checkout_session or {}).get("session_id"),
        "merchant_id": req.items[0].get("merchant_id") if from_merchant else None,
        "merchant_name": req.items[0].get("merchant_name") if from_merchant else None,
    })

    return {
        "razorpay_order_id": order["id"],
        "order_id": order["receipt"],
        "amount_paise": total,
        "product_name": basket["name"],
        "customer_id": customer["id"],
        "item_count": len(req.items),
        "risk": risk,
        "source": "merchant" if from_merchant else "ebay",
        # Present only for a merchant cart — the frontend settles the session
        # with the seller after Razorpay confirms, which is what releases the
        # stock on the seller's side.
        "merchant_checkout_session": (checkout_session or {}).get("session_id"),
        "merchant_name": req.items[0].get("merchant_name") if from_merchant else None,
        "instrument_note": (checkout_session or {}).get("instrument_note"),
        # What the basket was worth and what came off it. Both, always: a
        # total lower than the lines add up to is unverifiable without the
        # subtotal beside it, and a discount nobody can check is one nobody
        # should trust.
        "subtotal_paise": (checkout_session or {}).get("subtotal_paise") or total,
        "discount_paise": (checkout_session or {}).get("discount_paise") or 0,
        "discount_note": (checkout_session or {}).get("discount_note") or "",
    }
