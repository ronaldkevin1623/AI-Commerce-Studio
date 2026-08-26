from fastapi import APIRouter
from pydantic import BaseModel

from app.razorpay_client import create_refund
from app.firebase_client import log_refund, log_decision

router = APIRouter()


class RefundRequest(BaseModel):
    payment_id: str
    order_id: str
    amount_paise: int
    reason: str


@router.post("/refund")
def issue_refund(req: RefundRequest):
    refund = create_refund(req.payment_id, req.amount_paise, notes={"reason": req.reason})

    log_refund(
        refund_id=refund["id"],
        order_id=req.order_id,
        amount_paise=req.amount_paise,
        reason=req.reason,
    )
    log_decision(
        action_type="refund_issued",
        amount_paise=req.amount_paise,
        decision="allowed",
        reason=req.reason,
        order_id=req.order_id,
    )

    return {"status": "refunded", "razorpay_refund_id": refund["id"]}