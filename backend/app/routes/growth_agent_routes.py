"""
THE GROWTH AGENTS OVER HTTP.

  GET  /growth/agents     what is registered, and which can spend margin
  GET  /growth/scan       real signals -> bounded proposals -> gate verdicts
  POST /growth/apply      the one place an action takes effect
  GET  /growth/offers     what is currently live, and what it has cost

`scan` performs nothing. It is a review queue: every proposal arrives with
the gate's verdict already on it, so a merchant sees what would be given
away and what was refused before deciding anything.

`apply` re-gates from scratch rather than trusting the verdict the scan
returned — the scan may be minutes old and the budget may have moved since.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.growth import campaigns, registry

router = APIRouter(prefix="/growth", tags=["growth"])


@router.get("/agents")
def list_agents():
    return {
        "agents": registry.describe(),
        "note": ("Growth agents propose; they never apply. Anything that "
                 "gives away margin passes the same kind of bound the "
                 "buying agent's spending does."),
    }


@router.get("/scan")
def scan():
    """Look at the real data now and return proposals with verdicts."""
    try:
        proposals = registry.scan()
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail=f"The growth scan could not run: {exc}")
    costed = sum(p["cost_paise"] for p in proposals if p["verdict"] == "allowed")
    return {
        "proposals": proposals,
        "count": len(proposals),
        "would_cost_paise": costed,
        "note": ("Nothing here has been applied. Each proposal carries the "
                 "sample it is based on, because a recommendation from one "
                 "observation is a case and not a trend."),
    }


class ApplyRequest(BaseModel):
    proposal: dict
    # Set when a human is clearing something the gate escalated. An agent
    # can never fill this in for itself.
    approved_by: str = ""


@router.post("/apply")
def apply(body: ApplyRequest):
    result = registry.apply(body.proposal, approved_by=body.approved_by)
    if not result.get("ok"):
        # 409, not 400: the request was well formed and the gate refused it.
        # That distinction matters when reading the logs afterwards.
        raise HTTPException(status_code=409, detail=result.get("reason"))
    return result


@router.get("/offers")
def offers(target_id: str = ""):
    """Live offers — all of them, or the ones held against one target."""
    from app.firebase_client import db
    if target_id:
        rows = registry.offers_for(target_id)
    else:
        try:
            rows = [d.to_dict() or {}
                    for d in db.collection("growth_offers").stream()]
        except Exception as exc:
            raise HTTPException(status_code=503,
                                detail=f"Offers could not be read: {exc}")
    live = [r for r in rows if r.get("state") == "live"]
    return {
        "offers": live,
        "count": len(live),
        "committed_paise": sum(int(r.get("cost_paise") or 0) for r in live),
        "note": ("Committed is what these offers would cost if every one is "
                 "taken. Nothing is charged to the merchant here — this "
                 "build has no merchant billing rail, and an offer that is "
                 "never redeemed costs nothing at all."),
    }


# ── campaigns ───────────────────────────────────────────────────────────


class CampaignRequest(BaseModel):
    goal: str
    budget_paise: int
    window_hours: int = 24
    agent_ids: list[str] = []


@router.post("/campaigns")
def open_campaign(body: CampaignRequest):
    if body.budget_paise <= 0:
        raise HTTPException(status_code=400,
                            detail="A campaign with no budget cannot do anything.")
    if not body.agent_ids:
        raise HTTPException(status_code=400,
                            detail="A campaign needs at least one agent to run.")
    known = {a["agent_id"] for a in registry.describe()}
    unknown = [a for a in body.agent_ids if a not in known]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"No such agent(s): {', '.join(unknown)}. Registered: "
                   f"{', '.join(sorted(known))}.")
    return campaigns.create(body.goal, body.budget_paise,
                            body.window_hours, body.agent_ids)


@router.get("/campaigns")
def list_campaigns():
    rows = campaigns.all_campaigns()
    return {
        "campaigns": rows,
        "count": len(rows),
        "note": ("Nothing here runs on a timer. A campaign advances when it "
                 "is ticked, and each record says when that last happened so "
                 "nobody has to guess whether it is actually running."),
    }


@router.post("/campaigns/{campaign_id}/tick")
def tick_campaign(campaign_id: str):
    result = campaigns.tick(campaign_id)
    if not result.get("ok"):
        # 409 rather than 400: the request was fine, the campaign's own
        # bounds refused it.
        raise HTTPException(status_code=409, detail=result.get("error"))
    return result


@router.post("/campaigns/{campaign_id}/pause")
def pause_campaign(campaign_id: str):
    row = campaigns.pause(campaign_id)
    if not row:
        raise HTTPException(status_code=404, detail="No such campaign.")
    return row


@router.post("/campaigns/{campaign_id}/resume")
def resume_campaign(campaign_id: str):
    row = campaigns.resume(campaign_id)
    if not row:
        raise HTTPException(status_code=404, detail="No such campaign.")
    return row


@router.get("/campaigns/{campaign_id}/measure")
def measure_campaign(campaign_id: str):
    result = campaigns.measure(campaign_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.get("/graph")
def relationship_graph():
    """
    The product relationship graph the cross-sell and bundle agents reason
    over, exposed so the basis for a recommendation can be inspected rather
    than taken on trust. Every edge says whether it was observed in real
    orders or assumed from category.
    """
    from app.growth import graph
    return graph.build()


@router.get("/graph/{product_id}")
def relationship_for(product_id: str, limit: int = 3):
    from app.growth import graph
    complements = graph.complements(product_id, limit=limit)
    return {
        "product_id": product_id,
        "complements": complements,
        "note": ("Observed co-purchase outranks category adjacency "
                 "absolutely — one real pairing beats any number of products "
                 "filed in the same folder."),
    }


@router.get("/attribution")
def attribution(days: int = 30):
    """
    What the growth agents cost and what can honestly be traced back to
    them. Attributed, not incremental — the payload says so itself.
    """
    from app.growth import attribution as attribution_module
    return attribution_module.build(days=days)
