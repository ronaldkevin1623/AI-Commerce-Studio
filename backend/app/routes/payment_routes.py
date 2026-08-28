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

from app.razorpay_client import fetch_payment, create_order
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
