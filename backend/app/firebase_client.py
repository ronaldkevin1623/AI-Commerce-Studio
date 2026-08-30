import time
import firebase_admin
from firebase_admin import credentials, firestore
from app.config import FIREBASE_CREDENTIALS_PATH

cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()


def log_decision(action_type: str, amount_paise: int, decision: str,
                  reason: str, order_id: str = None, customer_id: str = None):
    doc_ref = db.collection("decisions").document()
    doc_ref.set({
        "action_type": action_type,
        "amount_paise": amount_paise,
        "decision": decision,
        "reason": reason,
        "order_id": order_id,
        "customer_id": customer_id,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })
    return doc_ref.id


def get_or_create_customer(name: str, email: str) -> dict:
    customers = db.collection("customers").where("email", "==", email).limit(1).get()
    if customers:
        doc = customers[0]
        return {"id": doc.id, **doc.to_dict()}

    doc_ref = db.collection("customers").document()
    data = {
        "name": name,
        "email": email,
        "trust_score": 100,
        "total_spend_paise": 0,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    doc_ref.set(data)
    return {"id": doc_ref.id, **data}


def adjust_trust_score(customer_id: str, delta: int):
    customer_ref = db.collection("customers").document(customer_id)
    customer_ref.update({"trust_score": firestore.Increment(delta)})


def save_order(order_id: str, razorpay_order_id: str, amount_paise: int,
               product_name: str, customer_id: str, status: str = "created",
               product: dict = None, mandates: dict = None):
    """
    Persist the order plus a snapshot of what was bought.

    The snapshot matters: a listing's price, discount and delivery estimate
    are live values that will have moved by the time anyone opens the order
    again. Storing them at purchase time means the order page shows what was
    actually agreed, not whatever eBay says today.
    """
    payload = {
        "razorpay_order_id": razorpay_order_id,
        "amount_paise": amount_paise,
        "product_name": product_name,
        "customer_id": customer_id,
        "status": status,
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    if product:
        payload["items"] = [{
            "id": str(product.get("id")),
            "name": product.get("name"),
            "image": product.get("image"),
            "url": product.get("url"),
            "condition": product.get("condition"),
            "quantity": 1,
            "price_paise": product.get("price_paise"),
            "original_price_paise": product.get("original_price_paise"),
            "discount_percent": product.get("discount_percent"),
        }]
        payload["shipping_cost_paise"] = product.get("shipping_cost_paise") or 0
        payload["delivery_estimate_from"] = product.get("delivery_estimate_from")
        payload["delivery_estimate_to"] = product.get("delivery_estimate_to")
        payload["price_is_converted"] = bool(product.get("price_is_converted"))

    if mandates:
        # Stored with the order so the chain can be re-verified from scratch
        # later — a proof you can't re-check afterwards isn't much of a proof.
        payload["mandates"] = mandates

    db.collection("orders").document(order_id).set(payload)


def update_order_status(razorpay_order_id: str, status: str,
                        payment_id: str = None):
    """
    Move an order to a new status, recording the payment behind it.

    The payment id is what makes "paid" checkable: anyone can take it to
    Razorpay and confirm the capture independently. Without it a paid order
    is just a field somebody set, and cannot be told apart from one that was.
    """
    orders = db.collection("orders").where(
        "razorpay_order_id", "==", razorpay_order_id).limit(1).get()
    if not orders:
        return

    update = {"status": status}
    if payment_id:
        update["razorpay_payment_id"] = payment_id
        update["paid_at"] = int(time.time())
    orders[0].reference.update(update)


def order_by_razorpay_id(razorpay_order_id: str) -> dict | None:
    """The stored order behind a Razorpay order id, or None."""
    rows = db.collection("orders").where(
        "razorpay_order_id", "==", razorpay_order_id).limit(1).get()
    return rows[0].to_dict() if rows else None


def save_run(run_id: str, query: str, events: list[dict], outcome: str,
             customer_id: str = None):
    """
    The full event stream of one agent run, so it can be replayed later.

    Conversation state lives in browser memory and dies on refresh, which
    meant every run AI Commerce Studio had ever done was unrecoverable the moment the
    tab reloaded. Recording the stream here makes a run a durable artefact:
    the replay is a genuine playback of what the agent did, at the times it
    did it, not a re-enactment.

    Events are stored verbatim. Firestore's 1MB document ceiling is far above
    what a run produces (tens of KB, dominated by candidate images), but the
    write is guarded by the caller so a run is never lost to an analytics
    failure.
    """
    db.collection("runs").document(run_id).set({
        "query": query,
        "events": events,
        "outcome": outcome,
        "event_count": len(events),
        "customer_id": customer_id,
        "created_at": firestore.SERVER_TIMESTAMP,
    })


def list_runs(limit: int = 40) -> list[dict]:
    """Run summaries — deliberately without the event payloads, which are big."""
    docs = (
        db.collection("runs")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .get()
    )
    out = []
    for d in docs:
        data = d.to_dict()
        data.pop("events", None)
        out.append({"id": d.id, **data})
    return out


def get_run(run_id: str) -> dict | None:
    doc = db.collection("runs").document(run_id).get()
    return {"id": doc.id, **doc.to_dict()} if doc.exists else None


def log_market_scan(query: str, candidates: list[dict], flagged: int):
    """
    A compact snapshot of what the market actually looked like for one search.

    Order records only ever capture the single listing someone bought, which
    is far too thin to say anything about prices or discounts. Every run,
    though, genuinely sees ten to thirty live listings with real prices and
    real discounts — throwing that away and then having nothing to chart
    would be a self-inflicted wound. Only aggregate numbers are stored, no
    titles or seller identifiers.
    """
    prices = [c.get("price_paise") for c in candidates if c.get("price_paise")]
    discounts = [c["discount_percent"] for c in candidates if c.get("discount_percent")]
    delivery = [c["delivery_days"] for c in candidates if c.get("delivery_days") is not None]

    if not prices:
        return

    ordered = sorted(prices)
    median = ordered[len(ordered) // 2]

    db.collection("market_scans").document().set({
        "query": query,
        "listing_count": len(candidates),
        "flagged_count": flagged,
        "prices_paise": prices,
        "discount_percents": discounts,
        "discounted_count": len(discounts),
        "delivery_days": delivery,
        "median_price_paise": median,
        "min_price_paise": ordered[0],
        "max_price_paise": ordered[-1],
        "timestamp": firestore.SERVER_TIMESTAMP,
    })


def list_market_scans(limit: int = 300) -> list[dict]:
    docs = (
        db.collection("market_scans")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .get()
    )
    return [d.to_dict() for d in docs]


def list_decisions(limit: int = 1000) -> list[dict]:
    docs = (
        db.collection("decisions")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .get()
    )
    return [d.to_dict() for d in docs]


def get_order(order_id: str) -> dict | None:
    doc = db.collection("orders").document(order_id).get()
    return {"id": doc.id, **doc.to_dict()} if doc.exists else None


def list_orders(limit: int = 40) -> list[dict]:
    docs = (
        db.collection("orders")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .get()
    )
    return [{"id": d.id, **d.to_dict()} for d in docs]


def decisions_for_order(razorpay_order_id: str) -> list[dict]:
    """
    Every logged decision naming this order. Sorted in Python rather than
    Firestore so this needs no composite index to work on the free tier.
    """
    docs = db.collection("decisions").where("order_id", "==", razorpay_order_id).get()
    rows = [{"id": d.id, **d.to_dict()} for d in docs]
    return sorted(rows, key=lambda r: r.get("timestamp") or 0)


def refunds_for_order(order_id: str) -> list[dict]:
    docs = db.collection("refunds").where("order_id", "==", order_id).get()
    return [{"id": d.id, **d.to_dict()} for d in docs]


def log_refund(refund_id: str, order_id: str, amount_paise: int, reason: str):
    db.collection("refunds").document(refund_id).set({
        "order_id": order_id,
        "amount_paise": amount_paise,
        "reason": reason,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })