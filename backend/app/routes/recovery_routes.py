"""
FAILED PURCHASES, AND WHAT CAN BE DONE ABOUT THEM.

  POST /payment-failure              a real payment failed; keep the product
  GET  /failed-purchases             the queue, newest first
  POST /failed-purchases/{id}/close  it was retried, paid or given up on
  GET  /payment-rails                which rails can actually take money
  POST /payment-retry                clear the way for a fresh attempt

WHY THIS EXISTS SEPARATELY FROM THE DECISION LOG

The audit trail records that a payment failed. It does not record WHAT
somebody was trying to buy, because a decision is about money and not about
merchandise — and widening the audit record to carry product fields would
put shopping data into the one collection whose shape everything else
depends on.

But "your payment failed" is not actionable and "your payment for the
Braided USB-C Cable failed because this account rejects foreign cards" is.
So a failure writes twice: a decision for the auditor, and a purchase record
here for the person who still wants the thing. The purchase record stores
the decision's id, so the two can always be walked between.

THE FAILURES ARE RAZORPAY'S OWN

Nothing here manufactures a failure. Razorpay Checkout emits `payment.failed`
with its own error code, description and step, and that payload is what gets
stored and shown — quoted rather than paraphrased. On this account a card
attempt really does fail, every time, which is why no simulation is needed to
demonstrate one.
"""
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.firebase_client import db, log_decision

router = APIRouter(tags=["recovery"])

COLLECTION = "failed_purchases"


def _summarise(error: dict, rails: dict | None = None) -> str:
    """
    One short line a person can act on.

    Razorpay's own description is used wherever it is already plain — it
    usually is, and rewriting it would mean this page and the Razorpay
    dashboard disagreeing about the same failure. What gets added is the
    part Razorpay cannot know: which rail on THIS account would have worked.
    """
    description = str((error or {}).get("description") or "").strip()
    reason = str((error or {}).get("reason") or "").strip()
    step = str((error or {}).get("step") or "").strip()

    line = description or reason or "The payment did not complete."
    if not line.endswith("."):
        line += "."

    if rails and rails.get("resolved"):
        working = rails["resolved"]["label"]
        if working.lower() not in line.lower():
            line += f" {working} is the only rail with a capture behind it here."

    if step and step not in line:
        line += f" (failed at: {step})"
    return line


class FailureReport(BaseModel):
    razorpay_order_id: str = ""
    amount_paise: int = 0
    customer_id: str = ""
    # Whatever the buyer was looking at. Sent by the client because the
    # client is the only party that has the listing in front of it.
    product: dict | None = None
    # Razorpay's own error object, passed through unedited.
    error: dict | None = None


@router.post("/payment-failure")
def record_failure(body: FailureReport):
    """
    A real payment failed. Keep the product so the purchase can be resumed.

    Called from the checkout's `payment.failed` handler, which is the only
    place that sees a card rejected inside Razorpay's own modal — the server
    never hears about those otherwise, and until now they vanished.
    """
    error = body.error or {}
    product = body.product or {}

    try:
        from app.agent import rails as rails_module
        rails = rails_module.status()
    except Exception:
        rails = None

    summary = _summarise(error, rails)

    decision_id = log_decision(
        action_type="payment_failed",
        amount_paise=int(body.amount_paise or 0),
        decision="blocked",
        reason=(f"{summary} Razorpay reported "
                f"{error.get('code') or 'no code'}"
                + (f" / {error.get('reason')}" if error.get("reason") else "")
                + ". Not retried automatically — the transaction policy "
                  "allows one attempt per decision, so the next attempt is a "
                  "fresh, separately gated action taken by a person."),
        order_id=body.razorpay_order_id or None,
        customer_id=body.customer_id or None,
    )

    record = {
        "id": f"fp-{uuid.uuid4().hex[:12]}",
        "decision_id": decision_id,
        "razorpay_order_id": body.razorpay_order_id or "",
        "amount_paise": int(body.amount_paise or 0),
        "customer_id": body.customer_id or "",
        "product": {
            "id": product.get("id") or "",
            "name": product.get("name") or "Unnamed item",
            "image": product.get("image") or "",
            "price_paise": int(product.get("price_paise") or body.amount_paise or 0),
            "source": product.get("source") or "",
            "url": product.get("url") or "",
        },
        "error": {
            "code": error.get("code") or "",
            "description": error.get("description") or "",
            "reason": error.get("reason") or "",
            "step": error.get("step") or "",
            "source": error.get("source") or "",
        },
        "summary": summary,
        "suggested_rail": (rails or {}).get("resolved", {}).get("label") if rails else None,
        "state": "open",
        "created_at": time.time(),
    }
    try:
        db.collection(COLLECTION).document(record["id"]).set(record)
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail=f"The failure could not be stored: {exc}")
    return record


@router.get("/failed-purchases")
def failed_purchases(include_closed: bool = False, limit: int = 20):
    """The queue. Open first, newest first, because that is what is actionable."""
    try:
        rows = [d.to_dict() or {} for d in db.collection(COLLECTION).stream()]
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail=f"The recovery queue could not be read: {exc}")
    if not include_closed:
        rows = [r for r in rows if r.get("state") == "open"]
    rows.sort(key=lambda r: -float(r.get("created_at") or 0))
    return {
        "count": len(rows),
        "purchases": rows[:max(1, min(limit, 100))],
        "note": ("Every one of these is a real Razorpay failure carrying the "
                 "error Razorpay itself reported. Nothing here is simulated."),
    }


class CloseRequest(BaseModel):
    outcome: str = "cancelled"     # retried | paid | cancelled
    note: str = ""


@router.post("/failed-purchases/{purchase_id}/close")
def close_purchase(purchase_id: str, body: CloseRequest):
    """
    Take it off the queue, and say why.

    Closing is logged. A recovery queue that can be emptied silently is a
    queue somebody will empty silently.
    """
    ref = db.collection(COLLECTION).document(purchase_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="No such failed purchase.")
    record = doc.to_dict() or {}
    outcome = body.outcome if body.outcome in ("retried", "paid", "cancelled") \
        else "cancelled"

    ref.update({"state": "closed", "outcome": outcome,
                "closed_at": time.time(), "close_note": body.note})

    log_decision(
        action_type="failed_purchase_closed",
        amount_paise=int(record.get("amount_paise") or 0),
        decision="allowed",
        reason=(f"{record.get('product', {}).get('name', 'An item')} — the "
                f"failed purchase was closed as {outcome}. "
                + (body.note or "")).strip(),
        order_id=record.get("razorpay_order_id") or None,
        customer_id=record.get("customer_id") or None,
    )
    return {"ok": True, "id": purchase_id, "outcome": outcome}


@router.get("/payment-rails")
def payment_rails():
    """
    Which rails can actually take money on this account, read from history.

    A GET with no side effects: enumerating the options costs nothing and
    should not require a failure to have happened first.
    """
    from app.agent import rails
    return rails.status()


class RetryRequest(BaseModel):
    purchase_id: str = ""
    razorpay_order_id: str = ""
    amount_paise: int = 0
    customer_id: str = ""


@router.post("/payment-retry")
def authorise_retry(body: RetryRequest):
    """
    Work out which rail can complete, and authorise a fresh attempt.

    THIS DOES NOT PAY, and cannot: netbanking is the only rail with a capture
    behind it on this account, and netbanking puts a person on the bank's own
    page. What an agent can honestly do is resolve the rails and hand over at
    the step that requires a human — which is what this returns.

    The attempt that follows re-enters the gate from the top. Nothing here
    resumes the attempt that failed.
    """
    from app.agent import rails as rails_module
    resolved = rails_module.status()

    log_decision(
        action_type="payment_retry_authorised",
        amount_paise=int(body.amount_paise or 0),
        decision="allowed",
        reason=("A person asked for another attempt after a failed payment. "
                "Rails re-resolved from this account's payment history: "
                + ", ".join(f"{r['label']} {r['verdict']}"
                            for r in resolved.get("rails", []))
                + ". "
                + (f"Resolved to {resolved['resolved']['label']}, which still "
                   f"requires a person at the bank page. "
                   if resolved.get("resolved") else "No rail can complete. ")
                + "This is a fresh attempt, gated from the top."),
        order_id=body.razorpay_order_id or None,
        customer_id=body.customer_id or None,
    )

    # DELIBERATELY DOES NOT CLOSE THE PURCHASE.
    #
    # Authorising a retry is not the same as having retried. The gate still
    # rules on the new order and can refuse it — a duplicate inside the
    # window, a spent budget, a fallen trust score — and an item that left
    # the queue on authorisation would vanish from the one place somebody
    # was going to notice it from. It closes when the retry actually
    # resolves: paid, or superseded by a newer failure.

    return {
        "ok": True,
        **resolved,
        "next_step": (
            f"Open the item again and pay with {resolved['resolved']['label']}."
            if resolved.get("resolved") else
            "There is no rail on this account that can complete a payment."
        ),
    }
