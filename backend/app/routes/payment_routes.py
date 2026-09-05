"""
Called by the frontend right after Razorpay's Checkout.js popup closes
successfully. This pulls the real payment status directly from
Razorpay's API rather than waiting on a webhook — useful for local
development/demos where you don't have a public URL for webhooks
to reach. (Webhooks remain the more robust production pattern, but
this gives you a genuine, real-time confirmation path without ngrok.)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.razorpay_client import (fetch_payment, capture_payment, create_order,
                                 fetch_order)
from app.agent.risk_gate import evaluate as risk_evaluate
from app.agent import merchant_client
from app.firebase_client import (
    order_by_razorpay_id,
    update_order_status,
    log_decision,
    adjust_trust_score,
    get_or_create_customer,
    save_order,
)
import uuid

router = APIRouter()


class VerifyPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    customer_id: str | None = None


@router.post("/verify-payment")
def verify_payment(req: VerifyPaymentRequest):
    # THE SPLIT CHECK.
    #
    # A checkout has two halves separated by a human on a bank page. If the
    # server restarts between them and comes back bound to a different
    # datastore, the order is in one store and this capture is about to be
    # written to another. Neither store then holds a complete record, and
    # nothing anywhere says why.
    #
    # This cannot repair that — the other store may not even be reachable
    # from here. What it can do is refuse to record it silently, which is
    # the difference between an anomaly someone can trace and a number that
    # is quietly wrong.
    try:
        from app.firebase_client import (store_binding,
                                         record_for_razorpay_order)
        existing, kind = record_for_razorpay_order(req.razorpay_order_id)
        if existing is None:
            log_decision(
                action_type="order_missing_locally",
                amount_paise=0,
                decision="flagged",
                reason=(f"Capture {req.razorpay_payment_id} arrived for order "
                        f"{req.razorpay_order_id}, which has no record in this "
                        f"datastore (binding={store_binding()}). Either the "
                        f"order was created under a different datastore "
                        f"binding, or it was never stored. Money may have "
                        f"moved without a local order behind it."),
                order_id=req.razorpay_order_id,
                customer_id=req.customer_id,
            )
        elif existing.get("store") and existing["store"] != store_binding():
            log_decision(
                action_type="datastore_binding_changed",
                amount_paise=int(existing.get("amount_paise") or 0),
                decision="flagged",
                reason=(f"{kind.capitalize()} {req.razorpay_order_id} was created against "
                        f"{existing['store']} but is being confirmed against "
                        f"{store_binding()}. The two halves of this checkout "
                        f"landed in different datastores."),
                order_id=req.razorpay_order_id,
                customer_id=req.customer_id,
            )
    except Exception as exc:
        print(f"[payment] split check skipped: {exc}", flush=True)

    # Razorpay raises for an unknown id rather than returning a status, so an
    # unverifiable payment has to be refused explicitly — otherwise it leaves
    # here as a 500 with a stack trace instead of a clear "not verified".
    try:
        payment = fetch_payment(req.razorpay_payment_id)
    except Exception as exc:
        log_decision(
            action_type="payment_failed",
            amount_paise=0,
            decision="blocked",
            reason=f"Payment id could not be verified with Razorpay: {exc}",
            order_id=req.razorpay_order_id,
            customer_id=req.customer_id,
        )
        raise HTTPException(
            status_code=402,
            detail="That payment id could not be verified with Razorpay.",
        )

    status = payment.get("status")
    amount = payment.get("amount")

    # Authorised means the person paid and the bank agreed; only the capture
    # is outstanding. Whether that happens automatically is an account
    # setting, so do it here rather than reporting a completed payment as a
    # failure. Any error leaves `status` as it was and falls through to the
    # honest refusal below.
    if status == "authorized":
        try:
            capture_payment(req.razorpay_payment_id, amount)
            payment = fetch_payment(req.razorpay_payment_id)
            status = payment.get("status")
            amount = payment.get("amount")
            log_decision(
                action_type="payment_captured",
                amount_paise=amount,
                decision="allowed",
                reason="Payment was authorised but not auto-captured; "
                       "captured explicitly via the Payments API",
                order_id=req.razorpay_order_id,
                customer_id=req.customer_id,
            )
        except Exception as exc:
            print(f"[payment] explicit capture failed: {exc}", flush=True)

    if status == "captured":
        update_order_status(req.razorpay_order_id, "paid",
                            payment_id=req.razorpay_payment_id)
        # If this order came from a sector that names the record it is
        # paying for, put that record in THIS row rather than leaving it
        # to be joined from the order-creation row. "Traceable via a join"
        # and "traceable" are not the same claim, and the one that was
        # asked for is the stronger one: hotel record → asserted price →
        # capture id, all visible in the row that records the capture.
        provenance = ""
        try:
            notes = (payment.get("notes") or {}) if isinstance(payment, dict) else {}
            if not notes.get("hotel_record_id"):
                notes = fetch_order(req.razorpay_order_id).get("notes") or {}
            if notes.get("hotel_record_id"):
                provenance = (
                    f" [sector={notes.get('sector')} leg={notes.get('leg')} "
                    f"record={notes['hotel_record_id']} "
                    f"name={notes.get('hotel_name')!r} "
                    f"asserted={int(amount) / 100:,.2f} "
                    f"capture={req.razorpay_payment_id}] "
                    f"The amount was derived from that dataset row, not from "
                    f"the client. Demo-merchant stand-in, not a hotel booking."
                )
        except Exception as exc:
            # A missing provenance note must never fail a confirmed payment.
            print(f"[payment] provenance lookup failed: {exc}", flush=True)

        log_decision(
            action_type="payment_confirmed",
            amount_paise=amount,
            decision="allowed",
            reason=("Payment verified directly via Razorpay Payments API"
                    + provenance),
            order_id=req.razorpay_order_id,
            customer_id=req.customer_id,
        )
        # A trip is only 'booked' once its stay is actually captured.
        try:
            from app.firebase_client import mark_trip_booked
            mark_trip_booked(req.razorpay_order_id, req.razorpay_payment_id)
        except Exception as exc:
            print(f"[payment] trip not marked booked: {exc}", flush=True)

        if req.customer_id:
            adjust_trust_score(req.customer_id, 2)

        settlement = _settle_with_merchant(req.razorpay_order_id, req.razorpay_payment_id)
        return {"status": "confirmed", "razorpay_status": status, **settlement}

    # Any non-captured status (failed, pending, etc.) is logged honestly,
    # not silently treated as success
    update_order_status(req.razorpay_order_id, status)
    log_decision(
        action_type="payment_failed",
        amount_paise=amount,
        decision="blocked",
        reason=f"Razorpay reported payment status: {status}",
        order_id=req.razorpay_order_id,
        customer_id=req.customer_id,
    )
    raise HTTPException(status_code=402, detail=f"Payment not captured (status: {status})")


class RepickRequest(BaseModel):
    product: dict
    customer_email: str = "demo@commerce-studio.dev"
    customer_name: str = "Demo User"


@router.post("/repick-order")
def repick_order(req: RepickRequest):
    """
    Creates a fresh Razorpay order for a different product after a
    failed or abandoned payment. The agent's WebSocket run has already
    ended by this point, so this runs the same risk gate over REST —
    a re-pick is still a real purchase attempt and is gated and logged
    exactly like the original one.
    """
    customer = get_or_create_customer(req.customer_name, req.customer_email)
    product = req.product

    risk_result = risk_evaluate(customer, product)
    log_decision(
        action_type="repick_attempt",
        amount_paise=product["price_paise"],
        decision=risk_result["decision"],
        reason=risk_result["reason"],
        customer_id=customer["id"],
    )

    if risk_result["decision"] == "blocked":
        adjust_trust_score(customer["id"], -5)
        raise HTTPException(status_code=403, detail=risk_result["reason"])

    receipt_id = f"cp-{uuid.uuid4().hex[:16]}"
    razorpay_order = create_order(
        amount_paise=product["price_paise"],
        receipt=receipt_id,
        notes={"customer_id": customer["id"], "product_id": str(product["id"])},
    )

    save_order(
        order_id=razorpay_order["receipt"],
        razorpay_order_id=razorpay_order["id"],
        amount_paise=product["price_paise"],
        product_name=product["name"],
        customer_id=customer["id"],
        product=product,
    )

    return {
        "razorpay_order_id": razorpay_order["id"],
        "amount_paise": product["price_paise"],
        "product_name": product["name"],
        "customer_id": customer["id"],
        "risk": risk_result,
    }


class AbandonRequest(BaseModel):
    query: str
    stage: str | None = None


@router.post("/abandon-run")
def abandon_run(req: AbandonRequest):
    """
    Records that a purchase run was deliberately ended by the person
    before completing. Logged as a real decision so the audit trail
    shows why a started run has no matching order, rather than the
    run simply disappearing.
    """
    log_decision(
        action_type="run_abandoned",
        amount_paise=0,
        decision="blocked",
        reason=f"Person ended the run at stage: {req.stage or 'running'}",
    )
    return {"status": "recorded"}

def _settle_with_merchant(razorpay_order_id: str, payment_id: str) -> dict:
    """
    Tell the seller the money arrived, for orders a seller actually opened.

    Razorpay confirming a capture settles the payment, not the sale — the
    merchant still holds the stock until it has checked the payment against
    its own session. It re-verifies with Razorpay rather than believing us,
    so this call is a notification, not an instruction.

    A failure here is reported, never swallowed: the buyer has genuinely
    paid at this point, and an order that is paid but unfulfilled is exactly
    the state a person needs to be told about.
    """
    order = order_by_razorpay_id(razorpay_order_id) or {}
    session_id = order.get("merchant_checkout_session")
    if not session_id:
        # TWO REASONS TO HAVE NO SESSION, AND ONLY ONE IS A PROBLEM.
        #
        # Most orders here were bought at another venue. There is no
        # merchant checkout to settle and never was, so this returns
        # quietly — logging those would bury the trail in an entry that
        # means "nothing happened, correctly".
        #
        # An order from THIS store with no session id is the other thing
        # entirely: the shop sold the goods, the buyer paid, and the shop
        # is never going to be told. It holds stock against a checkout that
        # stays `awaiting_payment` forever, and the money is captured at
        # Razorpay with nothing on the merchant side to match it against —
        # the same shape as an unrecorded capture, which is precisely what
        # the reconciliation audit exists to catch. Silence here is how a
        # discrepancy becomes untraceable, so it is written down.
        if (order.get("source") or "") == "merchant":
            log_decision(
                action_type="merchant_settlement_skipped",
                amount_paise=int(order.get("amount_paise") or 0),
                decision="flagged",
                reason=(f"Capture {payment_id} settled for order "
                        f"{razorpay_order_id}, which came from the merchant "
                        f"store but carries no checkout session. The store "
                        f"cannot be told this was paid, so its session stays "
                        f"open and its stock stays held. Money moved; the "
                        f"seller does not know."),
                order_id=razorpay_order_id,
                customer_id=order.get("customer_id"),
            )
        return {}

    try:
        merchant_client.settle(session_id, payment_id)
        return {"merchant_settled": True, "merchant_checkout_session": session_id}
    except Exception as exc:
        log_decision(
            action_type="merchant_settlement_failed",
            amount_paise=order.get("amount_paise") or 0,
            decision="blocked",
            reason=f"Paid, but {order.get('merchant_name') or 'the merchant'} did not "
                   f"confirm fulfilment for {session_id}: {exc}",
            order_id=razorpay_order_id,
        )
        return {
            "merchant_settled": False,
            "merchant_checkout_session": session_id,
            "merchant_error": (
                "Your payment went through, but the seller has not confirmed the "
                "order yet. It is recorded in the audit trail."
            ),
        }
