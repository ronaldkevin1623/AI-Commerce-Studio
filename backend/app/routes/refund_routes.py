"""
REFUNDS — the only path in this project that moves money back.

The agent spends money on someone's behalf, so "the agent got it wrong" has
to be a first-class outcome rather than an apology. This is that path, and
it is gated exactly as hard as the one that spends.

The previous version took the amount from the caller and passed it straight
to Razorpay. It never checked that the payment existed, that it had been
captured, that it belonged to the order it was being logged against, or that
it had not already been refunded — and an unknown id came back as a 500 with
a stack trace, the same failure already fixed twice on the payment path.

Five things are established before any money moves:

  The payment is real and captured, according to Razorpay rather than us.
  The order is one we actually recorded, and it is marked paid.
  The payment belongs to that order — a refund logged against the wrong
    order is a false record even when the money movement is correct.
  The amount is computed here, from what Razorpay says was captured minus
    what it says was already refunded. The caller does not get to name it.
  Nothing is left to refund only if Razorpay says so.

Every refusal is logged with its reason, because a refund that did not
happen is exactly as interesting to a person reading the audit trail as one
that did.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.razorpay_client import create_refund, fetch_payment
from app.firebase_client import (
    log_refund,
    log_decision,
    order_by_razorpay_id,
    update_order_status,
    refunds_for_order,
)

router = APIRouter()


class RefundRequest(BaseModel):
    payment_id: str
    order_id: str
    reason: str
    # Optional, and treated as a request rather than an instruction: the
    # server still bounds it by what is genuinely refundable.
    amount_paise: int | None = None


def _refuse(order_id: str, reason: str, status: int = 409, amount: int = 0):
    """Log the refusal, then raise it. A blocked refund is a real event."""
    log_decision(
        action_type="refund_blocked",
        amount_paise=amount,
        decision="blocked",
        reason=reason,
        order_id=order_id,
    )
    raise HTTPException(status_code=status, detail=reason)


@router.post("/refund")
def issue_refund(req: RefundRequest):
    order = order_by_razorpay_id(req.order_id)
    if not order:
        _refuse(req.order_id, "No such order in this system.", 404)

    status = (order.get("status") or "").lower()
    if status == "refunded":
        _refuse(req.order_id, "This order has already been refunded in full.")
    if status != "paid":
        _refuse(req.order_id,
                f"That order is {status or 'unpaid'}, so there is "
                f"nothing to refund.")

    # Razorpay is the authority on whether money moved, not our record of it.
    try:
        payment = fetch_payment(req.payment_id)
    except Exception as exc:
        _refuse(req.order_id,
                f"That payment id could not be verified with Razorpay: {exc}",
                402)

    if payment.get("status") != "captured":
        _refuse(req.order_id,
                f"Razorpay reports this payment as {payment.get('status')}, "
                f"not captured — there is nothing to return.", 402)

    # A refund recorded against the wrong order is a false record even when
    # the money movement itself is correct.
    if payment.get("order_id") and payment["order_id"] != req.order_id:
        _refuse(req.order_id,
                "That payment belongs to a different order.", 409)

    captured = int(payment.get("amount") or 0)
    already = int(payment.get("amount_refunded") or 0)
    refundable = captured - already
    if refundable <= 0:
        _refuse(req.order_id,
                f"₹{captured / 100:,.2f} was captured and ₹{already / 100:,.2f} "
                f"has already been returned — nothing is left to refund.",
                409, captured)

    # The caller may ask for less than the full amount; it may not ask for
    # more than exists, and it does not get to decide what exists.
    amount = refundable
    if req.amount_paise is not None:
        requested = int(req.amount_paise)
        if requested <= 0:
            _refuse(req.order_id, "A refund has to be for more than zero.", 400)
        if requested > refundable:
            _refuse(req.order_id,
                    f"₹{requested / 100:,.2f} was requested but only "
                    f"₹{refundable / 100:,.2f} is refundable.", 409, requested)
        amount = requested

    reason = (req.reason or "").strip() or "No reason given"

    try:
        refund = create_refund(req.payment_id, amount, notes={"reason": reason})
    except Exception as exc:
        # The money did not move. Say so plainly rather than returning a 500.
        _refuse(req.order_id,
                f"Razorpay refused the refund: {exc}", 502, amount)

    log_refund(
        refund_id=refund["id"],
        order_id=req.order_id,
        amount_paise=amount,
        reason=reason,
    )

    # The order must stop counting as captured revenue. Partial refunds keep
    # the order paid, because part of it still is.
    fully = (already + amount) >= captured
    if fully:
        update_order_status(req.order_id, "refunded")

    log_decision(
        action_type="refund_issued",
        amount_paise=amount,
        decision="allowed",
        reason=f"{reason} — ₹{amount / 100:,.2f} of ₹{captured / 100:,.2f} "
               f"returned via the Razorpay Refunds API",
        order_id=req.order_id,
        customer_id=order.get("customer_id"),
    )

    return {
        "status": "refunded" if fully else "partially_refunded",
        "razorpay_refund_id": refund["id"],
        "amount_paise": amount,
        "captured_paise": captured,
        "remaining_paise": captured - already - amount,
    }


@router.get("/refundable/{razorpay_order_id}")
def refundable(razorpay_order_id: str):
    """
    What could be returned for this order, and why not if nothing.

    Exists so the interface can show the real figure and disable itself with
    a stated reason, rather than offering a button that fails on click.
    """
    order = order_by_razorpay_id(razorpay_order_id)
    if not order:
        return {"refundable_paise": 0, "reason": "No such order."}

    payment_id = order.get("razorpay_payment_id")
    status = (order.get("status") or "").lower()

    # A refunded order was paid — saying it "has not been paid" is false, and
    # it is the state the panel shows immediately after a successful refund,
    # so it is the message most likely to be read.
    if status == "refunded":
        return {"refundable_paise": 0,
                "payment_id": payment_id,
                "prior_refunds": len(refunds_for_order(razorpay_order_id)),
                "reason": "This order has already been refunded in full."}

    if status != "paid" or not payment_id:
        return {"refundable_paise": 0,
                "reason": "This order has not been paid, so nothing can be "
                          "returned."}

    try:
        payment = fetch_payment(payment_id)
    except Exception as exc:
        return {"refundable_paise": 0,
                "reason": f"Razorpay could not be reached: {exc}"}

    captured = int(payment.get("amount") or 0)
    already = int(payment.get("amount_refunded") or 0)
    remaining = max(0, captured - already)

    return {
        "refundable_paise": remaining,
        "captured_paise": captured,
        "already_refunded_paise": already,
        "payment_id": payment_id,
        "prior_refunds": len(refunds_for_order(razorpay_order_id)),
        "reason": None if remaining else "Already fully refunded.",
    }
