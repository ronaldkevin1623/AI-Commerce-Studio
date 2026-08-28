from fastapi import APIRouter

from app.agent.growth_agent import build_insights

router = APIRouter()


@router.get("/growth-insights")
def growth_insights():
    """
    Merchant-side analytics, computed live from Firestore on every request.

    Deliberately not cached: the dataset is small enough that a fresh read
    costs nothing, and a stale dashboard that silently disagrees with the
    audit trail would be worse than a slow one.
    """
    return build_insights()
