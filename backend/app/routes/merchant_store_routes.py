"""
The merchant's own UCP surface.

Everything here is the seller talking, not the buyer. It publishes a
discovery document declaring a real checkout capability and a Razorpay
payment handler, exposes its catalogue, and turns a checkout session into a
genuine Razorpay order.

WHY THE MANIFEST LIVES UNDER /merchant:
UCP puts discovery at a host's `/.well-known/ucp`, and AI Commerce Studio already
serves its own there as a buyer. Two parties on one host cannot both own that
path, so the merchant's sits at `/merchant/.well-known/ucp`. In a real
deployment these are separate hosts and both would be at the root — the
compromise is here because this is one process pretending to be two parties,
which is stated rather than glossed.
"""
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.merchant import store
from app.merchant import growth as growth_metrics
from app.merchant import promotions
from app.agent import idempotency
from app.firebase_client import log_decision
from app.razorpay_client import create_order, fetch_payment

router = APIRouter(prefix="/merchant")

UCP_VERSION = "2026-04-08"


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.get("/.well-known/ucp")
def merchant_discovery(request: Request):
    """
    What the store offers.

    Unlike AI Commerce Studio's buyer manifest, this one does declare a checkout
    capability and a payment handler — because unlike AI Commerce Studio, this party
    can actually take money for goods it holds.
    """
    base = _base(request)
    return {
        "ucp": {
            "version": UCP_VERSION,
            "supported_versions": {UCP_VERSION: f"{base}/merchant/.well-known/ucp"},
            "merchant": {
                "id": store.MERCHANT_ID,
                "name": store.MERCHANT_NAME,
                "disclosure": (
                    "A first-party demo store operated by the AI Commerce Studio project. "
                    "Inventory is operator-declared. Buyer and merchant share one "
                    "Razorpay test account, so this proves the protocol and the "
                    "gate rather than settlement between two separate parties."
                ),
            },
            "services": {
                "dev.ucp.shopping": [
                    {
                        "version": UCP_VERSION,
                        "spec": f"https://ucp.dev/{UCP_VERSION}/specification/overview/",
                        "transport": "rest",
                        "endpoint": f"{base}/merchant",
                    }
                ]
            },
            "capabilities": {
                "dev.ucp.shopping.catalog.search": [
                    {"version": UCP_VERSION, "endpoint": f"{base}/merchant/catalog"}
                ],
                "dev.ucp.shopping.checkout": [
                    {
                        "version": UCP_VERSION,
                        "endpoint": f"{base}/merchant/checkout",
                        "config": {
                            "currency": "INR",
                            "stock_checked": True,
                            "idempotency": "required-header:idempotency-key",
                        },
                    }
                ],
            },
            "payment_handlers": {
                "com.razorpay": [
                    {
                        "version": UCP_VERSION,
                        "name": "Razorpay",
                        "mode": "test",
                        "instruments": ["netbanking", "wallet", "card"],
                        "note": (
                            "Cards are rejected on this test account and UPI is not "
                            "enabled. Netbanking completes in test mode."
                        ),
                    }
                ]
            },
        }
    }


@router.get("/catalog")
def catalog(q: str = "", max_price_inr: int = 0):
    """The store's own stock. Read-only, no gate — browsing costs nothing."""
    items = store.search(q, int(max_price_inr) * 100 if max_price_inr else 0)
    return {
        "merchant": {"id": store.MERCHANT_ID, "name": store.MERCHANT_NAME},
        "count": len(items),
        "terms": store.STORE_TERMS,
        # The agent-readable shape: availability and inventory as separate
        # facts, the merchant's declared delivery and returns windows, and
        # what this store will accept from an agent. `image` is carried
        # alongside rather than inside it — a data URI is for rendering, not
        # for reasoning, and it dwarfs every other field in the payload.
        "products": [{**store.agent_view(i),
                      "id": i["id"],
                      "price_inr": round(i["price_paise"] / 100, 2),
                      "stock": i.get("stock"),
                      "image": i.get("image")} for i in items],
    }


@router.get("/catalog/{product_id}")
def catalog_item(product_id: str):
    """
    One product, in full, for an agent that has narrowed to a candidate.

    A draft is a 404 here rather than a record with status=draft: the agent
    catalogue is what is for sale, and a half-finished product being
    discoverable is the exact failure the status field exists to prevent.
    """
    product = store.get_product(product_id)
    if not product or (product.get("status") or "active") != "active":
        raise HTTPException(status_code=404,
                            detail="No such product is published for sale.")
    return {**store.agent_view(product),
            "id": product["id"],
            "image": product.get("image"),
            # What the shop has OBSERVED goes with it...
            "complements": _complements(product_id),
            # ...and what the merchant has actually APPROVED showing beside
            # it. These are different claims: the first is the evidence, the
            # second is a decision somebody made and can be audited.
            "offer": store.live_offer(product_id)}


def _complements(product_id: str) -> dict:
    """
    What the store has observed going with this product.

    Folded into the product view because an agent assembling a basket should
    not have to know that a second endpoint exists to find out. The basis
    travels with it, so "bought together twice" and "filed under the same
    heading" cannot be confused for one another.
    """
    try:
        from app.growth import graph
        rows = graph.complements(product_id, limit=3)
    except Exception as exc:
        return {"items": [], "note": f"The relationship graph is unavailable: {exc}"}
    return {
        "items": [{"product_id": r["id"], "name": r["name"],
                   "price_paise": r["price_paise"],
                   "basis": r["basis"], "support": r["support"],
                   "why": r["why"]} for r in rows],
        "note": ("`basis` matters: co_purchase was observed in this store's "
                 "own orders, category_adjacency is an assumption from "
                 "shared category and is not evidence anyone bought them "
                 "together."),
    }


class CheckoutRequest(BaseModel):
    line_items: list[dict]
    buyer: dict | None = None


@router.post("/checkout")
def open_checkout(
    req: CheckoutRequest,
    idempotency_key: str = Header(None, alias="idempotency-key"),
    ucp_agent: str = Header(None, alias="UCP-Agent"),
    request_id: str = Header(None, alias="request-id"),
):
    """
    Open a checkout session and create the Razorpay order behind it.

    The merchant prices the basket from its own records — the buyer supplies
    ids and quantities and nothing else, so an agent cannot name its own
    price. Stock is checked here too, for the same reason.
    """
    if idempotency_key:
        try:
            replay = idempotency.claim(
                idempotency_key, "merchant-checkout", agent=ucp_agent, request_id=request_id
            )
        except idempotency.InProgress:
            raise HTTPException(status_code=409, detail="That checkout is already being opened.")
        if replay is not None:
            return {**replay, "idempotent_replay": True}

    try:
        opened = store.create_session(req.line_items, req.buyer)
        if not opened.get("ok"):
            raise HTTPException(status_code=400, detail=opened["error"])

        session = opened["session"]
        order = create_order(
            amount_paise=session["total_paise"],
            receipt=f"cds-{uuid.uuid4().hex[:16]}",
            notes={"checkout_session": session["id"], "merchant": store.MERCHANT_ID},
        )
        store.attach_order(session["id"], order["id"])

        log_decision(
            action_type="merchant_checkout_opened",
            amount_paise=session["total_paise"],
            decision="allowed",
            reason=(
                f"{store.MERCHANT_NAME} opened checkout {session['id']} for "
                f"{len(session['line_items'])} line item(s)"
            ),
            order_id=order["id"],
        )

        result = {
            "session_id": session["id"],
            "status": "awaiting_payment",
            "currency": "INR",
            "line_items": session["line_items"],
            "total_paise": session["total_paise"],
            "razorpay_order_id": order["id"],
            "payment_handler": "com.razorpay",
            "instrument_note": "Use Netbanking — cards are rejected on this test account.",
        }
    except HTTPException:
        if idempotency_key:
            idempotency.release(idempotency_key)
        raise
    except Exception:
        if idempotency_key:
            idempotency.release(idempotency_key)
        raise

    if idempotency_key:
        idempotency.complete(idempotency_key, result)
    return result


@router.get("/checkout/{session_id}")
def read_checkout(session_id: str):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"No checkout session {session_id}")
    session.pop("created_at", None)
    session.pop("paid_at", None)
    return session


class Settle(BaseModel):
    razorpay_payment_id: str


@router.post("/checkout/{session_id}/settle")
def settle(session_id: str, body: Settle):
    """
    Confirm a payment against Razorpay and release the stock.

    The payment status is fetched from Razorpay rather than taken from the
    caller. An agent that simply asserted "I paid" would otherwise walk off
    with the goods.
    """
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"No checkout session {session_id}")
    if session.get("status") == "paid":
        return {"status": "paid", "note": "Already settled.", "session_id": session_id}

    # An agent probing with a made-up payment id used to crash this endpoint:
    # razorpay raises BadRequestError for an unknown id, which surfaced as a
    # 500 and a stack trace. A refusal is the correct answer, and it should
    # look like one.
    try:
        payment = fetch_payment(body.razorpay_payment_id)
    except Exception as exc:
        log_decision(
            action_type="merchant_settle_rejected",
            amount_paise=session.get("total_paise") or 0,
            decision="blocked",
            reason=f"Unverifiable payment id offered for checkout {session_id}: {exc}",
            order_id=session.get("razorpay_order_id"),
        )
        raise HTTPException(
            status_code=402,
            detail="That payment id could not be verified with Razorpay.",
        )

    status = payment.get("status")

    if status != "captured":
        log_decision(
            action_type="merchant_payment_failed",
            amount_paise=session.get("total_paise") or 0,
            decision="blocked",
            reason=f"Razorpay reported payment status: {status}",
            order_id=session.get("razorpay_order_id"),
        )
        raise HTTPException(status_code=402, detail=f"Payment not captured (status: {status})")

    if payment.get("order_id") != session.get("razorpay_order_id"):
        raise HTTPException(status_code=409, detail="That payment belongs to a different order.")

    store.mark_paid(session_id, body.razorpay_payment_id)
    log_decision(
        action_type="merchant_payment_captured",
        amount_paise=session.get("total_paise") or 0,
        decision="allowed",
        reason=f"{store.MERCHANT_NAME} captured payment for checkout {session_id}",
        order_id=session.get("razorpay_order_id"),
    )
    return {"status": "paid", "session_id": session_id, "amount_paise": session["total_paise"]}


class NewProduct(BaseModel):
    name: str
    price_paise: int
    stock: int = 0
    category: str | None = None
    condition: str | None = "New"
    description: str | None = None
    image: str | None = None
    status: str | None = "active"
    attributes: dict | None = None


@router.get("/products")
def admin_products():
    """
    The operator's own view of the catalogue — drafts included.

    Deliberately separate from /catalog: that one answers a buying agent and
    must only ever show what is actually for sale. This one answers the shop
    owner, who needs to see the things that are not.
    """
    items = sorted(store.list_products(), key=lambda i: i.get("name") or "")
    return {
        "merchant": {"id": store.MERCHANT_ID, "name": store.MERCHANT_NAME},
        "count": len(items),
        "products": [{
            "id": i["id"],
            "name": i["name"],
            "category": i.get("category"),
            "price_paise": i["price_paise"],
            "stock": i.get("stock"),
            "status": i.get("status") or "active",
            "condition": i.get("condition"),
            "description": i.get("description"),
            "image": i.get("image"),
            "attributes": i.get("attributes") or {},
        } for i in items],
    }


@router.post("/products")
def add_product(body: NewProduct):
    """Add a product to the store's own stock."""
    created = store.create_product(body.model_dump())
    if not created.get("ok"):
        raise HTTPException(status_code=400, detail=created["error"])

    product = created["product"]
    log_decision(
        action_type="merchant_product_added",
        amount_paise=product["price_paise"],
        decision="allowed",
        reason=(
            f"{store.MERCHANT_NAME} added {product['name']} "
            f"({product['status']}, stock {product['stock']})"
        ),
    )
    return product


class Fulfil(BaseModel):
    state: str
    carrier: str | None = None
    tracking_reference: str | None = None


@router.get("/orders")
def merchant_orders():
    """
    The store's own orders, newest first, with where each one has got to.

    This is the seller's view: what has been paid for and what still needs
    handing over. The buyer sees the same transitions on their tracking page.
    """
    rows = [d.to_dict() for d in store.db.collection(store.SESSIONS).get()]
    rows.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
    return {
        "count": len(rows),
        "orders": [{
            "session_id": r.get("id"),
            "razorpay_order_id": r.get("razorpay_order_id"),
            "status": r.get("status"),
            "fulfilment_state": r.get("fulfilment_state") or (
                "paid" if r.get("status") == "paid" else None),
            "total_paise": r.get("total_paise"),
            "line_items": r.get("line_items") or [],
            "carrier": r.get("carrier"),
            "tracking_reference": r.get("tracking_reference"),
            "fulfilment_history": r.get("fulfilment_history") or [],
        } for r in rows[:60]],
    }


@router.post("/checkout/{session_id}/fulfil")
def fulfil(session_id: str, body: Fulfil):
    """Move an order along. Forward only, and only once it is paid for."""
    result = store.advance_fulfilment(
        session_id, body.state, body.carrier, body.tracking_reference)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result["error"])

    session = store.get_session(session_id) or {}
    log_decision(
        action_type="merchant_fulfilment",
        amount_paise=session.get("total_paise") or 0,
        decision="allowed",
        reason=f"{store.MERCHANT_NAME} marked {session_id} {result['state']}"
               + (f" ({body.carrier}, {body.tracking_reference})"
                  if result["state"] == "shipped" else ""),
        order_id=session.get("razorpay_order_id"),
    )
    return result


@router.get("/growth")
def merchant_growth(days: int = 30, start: str = "", end: str = ""):
    """
    Growth for the storefront, over a window.

    `days` is a rolling window ending now. `start`/`end` (ISO dates) is a
    fixed window someone picked off a calendar, and wins where both are
    given — a range that ended last Tuesday must still end last Tuesday when
    the page is reloaded on Thursday.
    """
    return {
        **growth_metrics.build(days, start_date=start, end_date=end),
        "discoverability": growth_metrics.discoverability(),
    }


@router.get("/analytics")
def merchant_analytics(days: int = 30, start: str = "", end: str = ""):
    """
    The shop's numbers for a window, against the window before it.

    Same two ways to ask as /merchant/growth: `days` for a rolling window,
    `start`/`end` for one pinned to dates.
    """
    from app.merchant import analytics
    return analytics.build(days, start_date=start, end_date=end)


class Ask(BaseModel):
    text: str


@router.post("/ask")
def merchant_ask(body: Ask):
    """
    The merchant command centre: one question in, one analysis out.

    Every figure in the reply is computed from this shop's own records by
    the same agents that populate the Growth pages. Nothing is phrased by a
    language model — see the module docstring for why that is deliberate.
    """
    from app.merchant import advisor
    answer = advisor.ask(body.text or "")
    try:
        log_decision(
            action_type="merchant_question",
            amount_paise=0,
            decision="allowed",
            reason=(f"Merchant asked: {(body.text or '')[:120]!r} — answered as "
                    f"{answer.get('intent')} from "
                    f"{len(answer.get('findings') or [])} finding(s) and "
                    f"{len(answer.get('actions') or [])} proposed action(s)."),
        )
    except Exception:
        # A question that cannot be logged is still a question worth
        # answering; the log is the record, not the gate.
        pass
    return answer


@router.post("/seed")
def seed_catalogue(force: bool = False):
    """Write the operator-declared catalogue into Firestore."""
    return {"written": store.seed(force=force), "products": len(store.SEED)}


# ── Retail media ─────────────────────────────────────────────────────────
#
# What a merchant can buy from this agent, and what they cannot, is set out
# in app/merchant/promotions.py. The short version, which the UI repeats
# rather than hiding: a promotion buys consideration for category-adjacent
# searches the store's own keyword match would miss, and a label if the
# product then earns a place. It buys nothing in the ranking.

class NewPromotion(BaseModel):
    product_id: str
    bid_paise: int
    daily_budget_paise: int
    active: bool = True


@router.get("/promotions")
def list_promotions():
    """
    Every promotion, with what it has actually done.

    `considered` is what the merchant paid for the chance at; `placed` is
    what reached a shopper and was charged; `screened_out` is what the
    agent's filters dropped, with the stage named — that last number is the
    one worth acting on, because a placement dying at precision usually
    means the catalogue says out of stock.
    """
    rows = promotions.list_all()
    return {
        "promotions": rows,
        "accrued_today_paise": sum(p["spent_today_paise"] for p in rows),
        "active": sum(1 for p in rows if p["active"] and not p["exhausted"]),
        # Repeated in the payload so no surface can render this as revenue
        # owed or an invoice raised.
        "billed": False,
        "billing_note": ("Spend is accrued per placement against the daily "
                         "budget and written to the decision log. Nothing "
                         "bills it — this build has no merchant billing rail."),
        "buys": ["Consideration for category-adjacent searches",
                 "A sponsored label if the product earns a place"],
        "does_not_buy": ["Any position in the ranking",
                         "Exemption from relevance, trust or stock screens",
                         "Any change to the risk gate or the mandate"],
    }


@router.post("/promotions")
def upsert_promotion(body: NewPromotion):
    result = promotions.set_promotion(
        body.product_id, bid_paise=body.bid_paise,
        daily_budget_paise=body.daily_budget_paise, active=body.active)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/promotions/{product_id}")
def delete_promotion(product_id: str):
    if not promotions.remove(product_id):
        raise HTTPException(status_code=404, detail="No such promotion.")
    return {"ok": True, "removed": product_id}
