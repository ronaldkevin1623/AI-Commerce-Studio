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

from app.razorpay_client import fetch_payment
from app.firebase_client import update_order_status, log_decision, adjust_trust_score

router = APIRouter()


class VerifyPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    customer_id: str | None = None


@router.post("/verify-payment")
def verify_payment(req: VerifyPaymentRequest):
    payment = fetch_payment(req.razorpay_payment_id)

    status = payment.get("status")
    amount = payment.get("amount")

    if status == "captured":
        update_order_status(req.razorpay_order_id, "paid")
        log_decision(
            action_type="payment_confirmed",
            amount_paise=amount,
            decision="allowed",
            reason="Payment verified directly via Razorpay Payments API",
            order_id=req.razorpay_order_id,
            customer_id=req.customer_id,
        )
        if req.customer_id:
            adjust_trust_score(req.customer_id, 2)
        return {"status": "confirmed", "razorpay_status": status}

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