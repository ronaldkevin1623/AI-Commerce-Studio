"""
Orders and their tracking state.

WHAT AI COMMERCE STUDIO CAN AND CANNOT SEE, because this endpoint is the place it
matters most: the payment lifecycle is real and fully observable — Razorpay
tells us when an order is created, captured, failed or refunded, and all of
it is already in Firestore. Fulfilment is not. AI Commerce Studio never notifies the
eBay seller, has no carrier integration, and eBay's Browse API is read-only,
so there is no shipment to track and no delivery to confirm.

A four-step "Packed → In transit → Out for delivery → Delivered" bar would
therefore be pure invention. So the stages below report exactly two real
things and then say, in the payload itself, that the rest is not tracked.
The delivery date that *is* shown is eBay's own estimate for that listing,
captured at purchase time and labelled as an estimate rather than a promise.
"""
from fastapi import APIRouter, HTTPException

from app.firebase_client import (
    get_order,
    list_orders,
    decisions_for_order,
    refunds_for_order,
    list_runs,
    get_run,
)
from app.agent import mandates as mandate_lib

router = APIRouter()

# Statuses Razorpay can report that mean the money did not land.
FAILED_STATUSES = {"failed", "attempted", "created"}


def _iso(value):
    """Firestore timestamps are datetimes; everything else passes through."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _stages(order: dict, decisions: list[dict], refunds: list[dict]) -> list[dict]:
    status = order.get("status")
    paid = status == "paid"

    confirmation = next(
        (d for d in decisions if d.get("action_type") == "payment_confirmed"), None
    )
    failure = next(
        (d for d in decisions if d.get("action_type") == "payment_failed"), None
    )

    stages = [
        {
            "key": "placed",
            "label": "Order placed",
            "state": "done",
            "at": _iso(order.get("created_at")),
            "detail": f"Razorpay order {order.get('razorpay_order_id')}",
        },
        {
            "key": "paid",
            "label": "Payment confirmed",
            "state": "done" if paid else ("failed" if failure else "pending"),
            "at": _iso(confirmation.get("timestamp")) if confirmation else None,
            "detail": (
                "Verified against the Razorpay Payments API"
                if paid
                else (failure.get("reason") if failure else "Awaiting checkout")
            ),
        },
    ]

    # Past payment, whether anything is known depends entirely on who sold it.
    #
    # For an eBay listing nothing is: AI Commerce Studio pays through Razorpay and has
    # no relationship with the seller, so a packed date would be invention and
    # these stay dashed. For the demo store we operate the seller, so its own
    # record of packing and handing over a parcel is a real assertion by the
    # party who would know — the same standing as its stock or its prices.
    fulfilment = None
    try:
        from app.merchant import store as merchant_store
        fulfilment = merchant_store.fulfilment_for_order(order.get("razorpay_order_id"))
    except Exception as exc:
        print(f"[orders] fulfilment lookup skipped: {exc}", flush=True)

    if fulfilment:
        seen = {h["state"]: h for h in fulfilment["history"]}
        for key, label in (("packed", "Packed"), ("shipped", "Shipped"),
                           ("delivered", "Delivered")):
            entry = seen.get(key)
            detail = f"{fulfilment['merchant']} — not yet"
            if entry:
                detail = entry.get("note") or label
                if key == "shipped":
                    detail = (f"{entry.get('carrier')} · "
                              f"{entry.get('tracking_reference')}")
            stages.append({
                "key": key,
                "label": label,
                "state": "done" if entry else "pending",
                "at": _iso(entry["at"]) if entry else None,
                "detail": detail,
            })
    else:
        stages += [
            {
                "key": "shipped",
                "label": "Shipped",
                "state": "not_tracked",
                "at": None,
                "detail": "AI Commerce Studio has no fulfilment integration with this seller.",
            },
            {
                "key": "delivered",
                "label": "Delivered",
                "state": "not_tracked",
                "at": None,
                "detail": "eBay's own delivery estimate is shown below; no carrier confirms it.",
            },
        ]

    if refunds:
        total = sum(r.get("amount_paise") or 0 for r in refunds)
        stages.append({
            "key": "refunded",
            "label": "Refunded",
            "state": "done",
            "at": _iso(refunds[0].get("timestamp")),
            "detail": f"₹{total / 100:,.0f} returned via the Razorpay Refunds API",
        })

    return stages


def _totals(order: dict) -> dict:
    """
    Every figure here is arithmetic over stored values — nothing estimated.

    Subtotal is the LIST price, not what was paid, so that the discount line
    actually resolves: subtotal − discount + delivery = total. Reporting the
    already-discounted price as the subtotal and then showing a discount
    beneath it makes the column fail to add up, which reads as a mistake even
    when every individual number is right.
    """
    items = order.get("items") or []

    subtotal = 0
    discount = 0
    for item in items:
        quantity = item.get("quantity") or 1
        price = item.get("price_paise") or 0
        original = item.get("original_price_paise")
        listed = original if original and original > price else price
        subtotal += listed * quantity
        discount += (listed - price) * quantity

    paid = sum((i.get("price_paise") or 0) * (i.get("quantity") or 1) for i in items)
    if not subtotal:
        # Orders stored before item snapshots existed still have an amount.
        subtotal = paid = order.get("amount_paise") or 0

    shipping = order.get("shipping_cost_paise") or 0

    return {
        "subtotal_paise": subtotal,
        "discount_paise": discount,
        "shipping_paise": shipping,
        # What Razorpay was actually asked to charge. Shipping is listed
        # separately because eBay reports it separately and it was not part
        # of the amount put through checkout.
        "charged_paise": order.get("amount_paise") or 0,
        "total_paise": paid + shipping,
    }


def _shape(order: dict, with_tracking: bool) -> dict:
    payload = {
        "id": order.get("id"),
        "razorpay_order_id": order.get("razorpay_order_id"),
        "status": order.get("status"),
        "created_at": _iso(order.get("created_at")),
        "customer_id": order.get("customer_id"),
        "product_name": order.get("product_name"),
        "items": order.get("items") or [],
        "item_count": sum((i.get("quantity") or 1) for i in (order.get("items") or [])) or 1,
        "delivery_estimate_from": order.get("delivery_estimate_from"),
        "delivery_estimate_to": order.get("delivery_estimate_to"),
        "price_is_converted": order.get("price_is_converted", False),
        "totals": _totals(order),
    }

    if with_tracking:
        decisions = decisions_for_order(order.get("razorpay_order_id"))
        # Keyed by the Razorpay order id, like decisions above. These two
        # lookups used different ids for the same order, so the first real
        # refund was written under one and read under the other — the money
        # moved, the record existed, and the tracking page showed no
        # refunded stage at all.
        refunds = refunds_for_order(order.get("razorpay_order_id"))
        payload["stages"] = _stages(order, decisions, refunds)
        payload["decisions"] = [
            {
                "action_type": d.get("action_type"),
                "decision": d.get("decision"),
                "reason": d.get("reason"),
                "at": _iso(d.get("timestamp")),
            }
            for d in decisions
        ]
        payload["fulfilment_tracked"] = False

    return payload


@router.get("/product/{item_id:path}")
def product_detail(item_id: str, query: str = ""):
    """
    Full detail for one listing, fetched live when the product drawer opens.

    Search results carry a single image and no prose; the gallery, the
    description and the seller's own shipping estimate only exist on eBay's
    single-item endpoint. Fetching on open also means the price in the drawer
    is current rather than however old the search results are.

    `item_id:path` because eBay ids contain pipes and slashes (v1|1234|0).
    """
    from app.agent.ebay_client import get_item

    try:
        item = get_item(item_id, category=query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"eBay lookup failed: {exc}")

    if not item:
        raise HTTPException(status_code=404, detail="That listing is no longer available.")
    return item


@router.get("/runs")
def all_runs(limit: int = 40):
    """Recorded agent runs, newest first. Summaries only — events are large."""
    return {"runs": list_runs(limit)}


@router.get("/runs/{run_id}")
def one_run(run_id: str):
    """One run's full event stream, with the timing offsets replay needs."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"No run {run_id}")
    return run


@router.get("/mandates/jwk")
def signing_key():
    """
    The public key the mandates are signed with.

    Published so a mandate can be verified by someone who doesn't trust this
    server — which is the entire point of signing them.
    """
    return {"keys": [mandate_lib.public_jwk()], "algorithm": mandate_lib.ALGORITHM}


@router.get("/orders/{order_id}/mandate")
def order_mandate(order_id: str):
    """
    Re-verify a stored chain from scratch, right now.

    Deliberately not a stored verdict: it re-runs the signature and hash
    checks against the tokens on the order, so a tampered record fails here
    rather than replaying an old "verified" flag.
    """
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"No order {order_id}")

    stored = order.get("mandates") or {}
    intent_jwt = stored.get("intent_jwt")
    cart_jwt = stored.get("cart_jwt")

    if not intent_jwt or not cart_jwt:
        # Orders created before the mandate chain existed. Say so plainly
        # rather than reporting an empty chain as a failed one.
        return {
            "present": False,
            "reason": "This order predates the mandate chain.",
        }

    verification = mandate_lib.verify_chain(intent_jwt, cart_jwt)
    return {
        "present": True,
        "verified_now": verification["ok"],
        "checks": verification["checks"],
        "reason": verification["reason"],
        "chain": mandate_lib.summarise(intent_jwt, cart_jwt),
        "tokens": {"intent_jwt": intent_jwt, "cart_jwt": cart_jwt},
    }


@router.get("/orders")
def all_orders(limit: int = 40):
    return {"orders": [_shape(o, with_tracking=False) for o in list_orders(limit)]}


@router.get("/orders/{order_id}")
def one_order(order_id: str):
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"No order {order_id}")
    return _shape(order, with_tracking=True)
