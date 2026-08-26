from fastapi import APIRouter, Request, HTTPException
from app.razorpay_client import verify_webhook_signature
from app.firebase_client import update_order_status, log_decision

router = APIRouter()


@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not verify_webhook_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")

    if event == "payment.captured":
        payment = payload["payload"]["payment"]["entity"]
        razorpay_order_id = payment["order_id"]
        update_order_status(razorpay_order_id, "paid")
        log_decision(
            action_type="payment_confirmed",
            amount_paise=payment["amount"],
            decision="allowed",
            reason="Webhook verified, payment captured",
            order_id=razorpay_order_id,
        )

    elif event == "payment.failed":
        payment = payload["payload"]["payment"]["entity"]
        razorpay_order_id = payment.get("order_id")
        update_order_status(razorpay_order_id, "failed")
        log_decision(
            action_type="payment_failed",
            amount_paise=payment["amount"],
            decision="blocked",
            reason=payment.get("error_description", "Payment declined"),
            order_id=razorpay_order_id,
        )

    return {"status": "ok"}