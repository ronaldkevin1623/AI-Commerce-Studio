"""
THE GROWTH AGENT REGISTRY, AND THE ONE PLACE ACTIONS ARE APPLIED.

Same shape as the sector and venue registries: agents register themselves,
nothing else needs editing when one is added, and a failing agent cannot
stop the others loading.

The important part is `apply`. Agents propose; only this applies. One
function, one gate call, one decision written — so "what did the growth
agents do to my margin today" has exactly one answer and one place to read
it from.
"""
import time
import uuid

from app.growth import gate
from app.growth.base import GrowthAgent, Proposal

_AGENTS: dict = {}


def register(agent) -> None:
    _AGENTS[agent.agent_id] = agent


def agents() -> list:
    return list(_AGENTS.values())


def get(agent_id: str):
    return _AGENTS.get(agent_id)


def bootstrap() -> None:
    """Load the built-in agents. Import failures are isolated per agent."""
    if _AGENTS:
        return
    try:
        from app.growth.recovery import CartRecoveryAgent
        register(CartRecoveryAgent())
    except Exception as exc:
        print(f"[growth] cart recovery unavailable: {exc}", flush=True)
    try:
        from app.growth.crosssell import CrossSellAgent
        register(CrossSellAgent())
    except Exception as exc:
        print(f"[growth] cross-sell unavailable: {exc}", flush=True)
    try:
        from app.growth.offers import DiscountExperimentAgent
        register(DiscountExperimentAgent())
    except Exception as exc:
        print(f"[growth] discount test unavailable: {exc}", flush=True)
    try:
        from app.growth.reactivation import ReactivationAgent
        register(ReactivationAgent())
    except Exception as exc:
        print(f"[growth] reactivation unavailable: {exc}", flush=True)
    try:
        from app.growth.bundles import BundleAgent
        register(BundleAgent())
    except Exception as exc:
        print(f"[growth] bundles unavailable: {exc}", flush=True)


def describe() -> list[dict]:
    bootstrap()
    return [{
        "agent_id": a.agent_id, "name": a.name, "what": a.what,
        "spends_margin": a.spends_margin,
    } for a in agents()]


def scan() -> list[dict]:
    """
    Every agent looks at the real data and proposes, then the gate rules on
    each proposal. Nothing is applied here — this is the review queue.
    """
    bootstrap()
    out = []
    for agent in agents():
        try:
            signals = agent.detect()
            for proposal in agent.propose(signals):
                verdict = gate.evaluate(proposal)
                proposal.verdict = verdict["verdict"]
                proposal.verdict_reason = verdict["reason"]
                out.append(proposal.to_dict())
        except Exception as exc:
            print(f"[growth] {agent.agent_id} failed to scan: {exc}", flush=True)
    # Costed and blocked things first: the merchant should see what wants
    # money and what was refused before what is free.
    out.sort(key=lambda p: (p["verdict"] == "allowed", -p["cost_paise"]))
    return out


def apply(proposal_dict: dict, approved_by: str = "",
          campaign_id: str = "") -> dict:
    """
    THE ONLY PLACE A GROWTH ACTION TAKES EFFECT.

    Re-gates from scratch rather than trusting the verdict the scan
    returned. The scan may be minutes old, the daily budget may have been
    spent by another action since, and the dials may have moved — the same
    reason the buyer's broker re-evaluates at confirm time instead of
    trusting what it decided at propose time.
    """
    from app.firebase_client import log_decision

    proposal = Proposal(
        agent=proposal_dict.get("agent", ""),
        kind=proposal_dict.get("kind", ""),
        headline=proposal_dict.get("headline", ""),
        detail=proposal_dict.get("detail", ""),
        cost_paise=int(proposal_dict.get("cost_paise") or 0),
        target_kind=proposal_dict.get("target_kind", ""),
        target_id=proposal_dict.get("target_id", ""),
        sample_size=int(proposal_dict.get("sample_size") or 0),
        evidence_note=proposal_dict.get("evidence_note", ""),
        params=proposal_dict.get("params") or {},
    )

    verdict = gate.evaluate(proposal)

    # A HUMAN CAN CLEAR AN ESCALATION. A BLOCK IS NOT AN ESCALATION.
    #
    # These two verdicts mean different things and used to be treated as one.
    # `escalated` means "this is beyond what the agent may decide alone, so a
    # person decides" — an approval is exactly the answer to it. `blocked`
    # means no: growth is switched off, or the day's budget is gone. Letting
    # an approval clear that turned the daily cap into a suggestion, and the
    # merchant console duly reported ₹1,557.60 committed against a ₹500 cap
    # — every individual decision looking correct in the log, the bound
    # nonetheless exceeded threefold.
    refuse = (verdict["verdict"] == "blocked"
              or (verdict["verdict"] != "allowed" and not approved_by))
    if refuse:
        log_decision(
            action_type="growth_refused",
            amount_paise=proposal.cost_paise,
            decision=verdict["verdict"],
            reason=(f"[{proposal.agent}] {proposal.headline} — "
                    f"{verdict['reason']}"
                    + (" A human approval cannot clear a block."
                       if approved_by else "")),
        )
        return {"ok": False, "verdict": verdict["verdict"],
                "reason": verdict["reason"]}

    # THE DAILY CAP IS CHECKED HERE TOO, AND NOT ONLY BY `evaluate`.
    #
    # Two reasons, and neither is belt-and-braces. First, `evaluate` returns
    # on its FIRST failing bound: a proposal over the per-action cap returns
    # `escalated` at bound 2 and never reaches the daily check at bound 3, so
    # an approved action of any size used to reach here having never been
    # counted against the day at all. Second, evaluate-then-apply is
    # check-then-act — two approvals in flight together both read the same
    # remaining headroom and both fit. The reservation is transactional, so
    # the second sees the first.
    reservation = gate.reserve(proposal.cost_paise)
    if not reservation["ok"]:
        reason = (f"₹{reservation['committed_paise'] / 100:,.2f} of today's "
                  f"₹{reservation['cap_paise'] / 100:,.0f} growth budget is "
                  f"already committed, so this ₹{proposal.cost_paise / 100:,.2f} "
                  f"does not fit. Approval cannot widen a daily cap.")
        log_decision(
            action_type="growth_refused",
            amount_paise=proposal.cost_paise,
            decision="blocked",
            reason=f"[{proposal.agent}] {proposal.headline} — {reason}",
        )
        return {"ok": False, "verdict": "blocked", "reason": reason}

    offer_id = f"go-{uuid.uuid4().hex[:12]}"
    record = {
        "offer_id": offer_id,
        "agent": proposal.agent,
        "kind": proposal.kind,
        "target_kind": proposal.target_kind,
        "target_id": proposal.target_id,
        "cost_paise": proposal.cost_paise,
        "params": proposal.params,
        "approved_by": approved_by or "auto",
        # Which campaign placed this, so outcomes can be attributed to one
        # programme rather than to "growth" in general.
        "campaign_id": campaign_id,
        "created_at": time.time(),
        "state": "live",
    }
    try:
        from app.firebase_client import db
        db.collection("growth_offers").document(offer_id).set(record)
    except Exception as exc:
        # The margin was reserved a moment ago and this action is not
        # happening, so give it back rather than letting it hold the budget
        # down for the rest of the day.
        gate.release(proposal.cost_paise)
        return {"ok": False, "verdict": "blocked",
                "reason": f"The offer could not be stored, so it was not "
                          f"applied: {exc}"}

    log_decision(
        action_type="growth_applied",
        amount_paise=proposal.cost_paise,
        decision="allowed",
        reason=(f"[{proposal.agent}] {proposal.headline}. "
                f"{verdict['reason']} Evidence: {proposal.evidence_note} "
                f"Offer {offer_id} against {proposal.target_kind} "
                f"{proposal.target_id}. "
                + (f"Approved by {approved_by}." if approved_by
                   else "Within bounds, applied without escalation.")
                + (f" Part of campaign {campaign_id}." if campaign_id else "")),
    )
    return {"ok": True, "offer_id": offer_id, "record": record,
            "reason": verdict["reason"]}


def offers_for(target_id: str) -> list[dict]:
    """Live offers held against one target, newest first."""
    try:
        from app.firebase_client import db
        rows = [d.to_dict() or {} for d in
                db.collection("growth_offers")
                  .where("target_id", "==", target_id).stream()]
    except Exception:
        return []
    now = time.time()
    live = []
    for row in rows:
        if row.get("state") != "live":
            continue
        hours = float((row.get("params") or {}).get("expires_in_hours") or 0)
        from app.growth.recovery import _epoch
        if hours and now - _epoch(row.get("created_at")) > hours * 3600:
            continue
        live.append(row)
    from app.growth.recovery import _epoch
    live.sort(key=lambda r: -_epoch(r.get("created_at")))
    return live
