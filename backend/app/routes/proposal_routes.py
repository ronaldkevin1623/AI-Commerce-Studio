"""
The human end of the external-agent boundary.

An agent working over MCP can propose a purchase but cannot clear its own
escalation. These endpoints are the only way that state moves, and they are
served to AI Commerce Studio's own UI — a person, in a browser, looking at what the
agent asked for before saying yes.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent import broker

router = APIRouter()


def _shape(proposal: dict) -> dict:
    product = proposal.get("product") or {}
    return {
        "id": proposal.get("id"),
        "status": proposal.get("status"),
        "decision": proposal.get("decision"),
        "reason": proposal.get("reason"),
        "budget": (proposal.get("budget") or {}).get("summary"),
        "source": proposal.get("source"),
        "customer_email": proposal.get("customer_email"),
        "human_decision": proposal.get("human_decision"),
        "order_id": proposal.get("order_id"),
        "query": proposal.get("query"),
        "created_at": (
            proposal["created_at"].isoformat()
            if hasattr(proposal.get("created_at"), "isoformat") else None
        ),
        "product": {
            "id": str(product.get("id")),
            "name": product.get("name"),
            "image": product.get("image"),
            "url": product.get("url"),
            "condition": product.get("condition"),
            "seller_feedback": product.get("seller_feedback"),
            "price_paise": product.get("price_paise"),
            "discount_percent": product.get("discount_percent"),
            "trust": product.get("trust"),
        },
    }


@router.get("/proposals/pending")
def pending_proposals():
    """Everything an external agent has parked for a human decision."""
    return {"proposals": [_shape(p) for p in broker.pending()]}


@router.get("/proposals")
def recent_proposals(limit: int = 40):
    return {"proposals": [_shape(p) for p in broker.recent(limit)]}


class Decision(BaseModel):
    approved: bool
    note: str | None = None


@router.post("/proposals/{proposal_id}/decide")
def decide_proposal(proposal_id: str, body: Decision):
    result = broker.decide(proposal_id, body.approved, body.note)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error"))
    return result


@router.post("/proposals/{proposal_id}/confirm")
def confirm_proposal(proposal_id: str):
    """
    Let a person finish an approved proposal from the UI.

    The agent would normally call confirm_purchase itself after polling, but
    a person who has just approved something shouldn't have to wait for the
    agent to notice. Same broker call, same re-verification.
    """
    return broker.confirm(proposal_id)
