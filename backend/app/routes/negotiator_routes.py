"""
Seller contact. Drafting a message is not a financial action, but it is a
step in a purchase the audit trail should be able to explain — a run that
paused to question the seller looks different from one that simply stalled.
So the draft is logged like everything else.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.negotiator_agent import draft_message
from app.firebase_client import log_decision

router = APIRouter()


class ContactSellerRequest(BaseModel):
    product: dict
    goal: str = "condition"
    customer_id: str | None = None


@router.post("/contact-seller")
def contact_seller(req: ContactSellerRequest):
    if not req.product.get("name"):
        raise HTTPException(status_code=400, detail="Product has no title to ground a message in")

    result = draft_message(req.product, req.goal)

    article = "an" if result["goal"][0] in "aeiou" else "a"
    log_decision(
        action_type="seller_contact_drafted",
        amount_paise=req.product.get("price_paise") or 0,
        decision="allowed",
        reason=f"Drafted {article} {result['goal']} message about: {req.product.get('name')}",
        customer_id=req.customer_id,
    )

    return result
