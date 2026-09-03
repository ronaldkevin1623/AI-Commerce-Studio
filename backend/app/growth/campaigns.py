"""
CAMPAIGNS: A BOUNDED PROGRAMME, NOT A LOOP THAT RUNS AGENTS.

A single proposal is one decision. A campaign is a commitment: "spend up to
this much, over this window, pursuing this goal, using these agents" — and
the difference that matters is that a campaign can END. An orchestrator
that cannot stop itself is a scheduler with a marketing name.

So a campaign has three ways to finish, and all three are enforced here
rather than left to whoever remembers to switch it off:

    budget spent     the envelope is gone
    window closed    the end time has passed
    paused           a person stopped it

THE ENVELOPE IS A SECOND BOUND, NOT A REPLACEMENT

Every action a campaign takes still passes the growth gate — the daily cap,
the per-action cap, the discount ceiling and the evidence floor all still
apply. The campaign budget sits INSIDE those. A campaign can therefore be
stopped by its own envelope or by the gate, and whichever binds first wins.
Nothing about running inside a campaign loosens anything.

WHAT A TICK DOES

Scans, keeps only what this campaign's agents proposed, and applies what
the gate allowed until the envelope runs out. Anything the gate escalated
is left alone: a campaign cannot approve on a person's behalf, which is the
same rule everywhere else in this system.

ON SCHEDULING

Nothing here runs on a timer. `tick()` is called by a person or by an
external scheduler, and the campaign record says when it was last ticked so
nobody has to guess whether it is actually running. Claiming an unattended
cadence this build does not have would be the easiest lie in the feature.
"""
import time
import uuid

COLLECTION = "growth_campaigns"


def _db():
    from app.firebase_client import db
    return db


def _epoch(value) -> float:
    from app.growth.recovery import _epoch as convert
    return convert(value)


def create(goal: str, budget_paise: int, window_hours: int,
           agent_ids: list[str], created_by: str = "") -> dict:
    """Open a campaign. Nothing runs until it is ticked."""
    campaign_id = f"gc-{uuid.uuid4().hex[:12]}"
    now = time.time()
    record = {
        "campaign_id": campaign_id,
        "goal": goal,
        "budget_paise": int(budget_paise),
        "spent_paise": 0,
        "agent_ids": list(agent_ids),
        "created_at": now,
        "ends_at": now + int(window_hours) * 3600,
        "state": "running",
        "created_by": created_by or "merchant",
        "ticks": 0,
        "last_tick_at": 0,
        "applied": [],
        "stopped_reason": "",
    }
    _db().collection(COLLECTION).document(campaign_id).set(record)

    from app.firebase_client import log_decision
    log_decision(
        action_type="campaign_opened",
        amount_paise=int(budget_paise),
        decision="allowed",
        reason=(f"Campaign {campaign_id} opened: {goal}. Envelope "
                f"₹{budget_paise / 100:,.2f} over {window_hours}h using "
                f"{', '.join(agent_ids)}. Every action inside it still passes "
                f"the growth gate; this budget sits inside those bounds, not "
                f"instead of them."),
    )
    return record


def get(campaign_id: str) -> dict | None:
    doc = _db().collection(COLLECTION).document(campaign_id).get()
    return doc.to_dict() if doc.exists else None


def all_campaigns() -> list[dict]:
    rows = [d.to_dict() or {} for d in _db().collection(COLLECTION).stream()]
    rows.sort(key=lambda r: -_epoch(r.get("created_at")))
    return rows


def _stop(campaign: dict, reason: str) -> dict:
    campaign["state"] = "finished"
    campaign["stopped_reason"] = reason
    _db().collection(COLLECTION).document(campaign["campaign_id"]).set(campaign)
    from app.firebase_client import log_decision
    log_decision(
        action_type="campaign_finished",
        amount_paise=int(campaign.get("spent_paise") or 0),
        decision="allowed",
        reason=(f"Campaign {campaign['campaign_id']} finished — {reason}. "
                f"Spent ₹{(campaign.get('spent_paise') or 0) / 100:,.2f} of "
                f"₹{(campaign.get('budget_paise') or 0) / 100:,.2f}."),
    )
    return campaign


def pause(campaign_id: str) -> dict | None:
    campaign = get(campaign_id)
    if not campaign:
        return None
    campaign["state"] = "paused"
    _db().collection(COLLECTION).document(campaign_id).set(campaign)
    return campaign


def resume(campaign_id: str) -> dict | None:
    campaign = get(campaign_id)
    if not campaign or campaign.get("state") == "finished":
        return campaign
    campaign["state"] = "running"
    _db().collection(COLLECTION).document(campaign_id).set(campaign)
    return campaign


def tick(campaign_id: str) -> dict:
    """
    One pass: scan, apply what fits, stop if the campaign is done.

    Returns what happened rather than just a status, so the caller can show
    a merchant exactly which actions this pass took and which it left for a
    person.
    """
    from app.growth import registry

    campaign = get(campaign_id)
    if not campaign:
        return {"ok": False, "error": "No such campaign."}
    if campaign.get("state") == "paused":
        return {"ok": False, "error": "That campaign is paused.",
                "campaign": campaign}
    if campaign.get("state") == "finished":
        return {"ok": False, "error": f"That campaign already finished — "
                                      f"{campaign.get('stopped_reason')}.",
                "campaign": campaign}

    now = time.time()
    if now >= float(campaign.get("ends_at") or 0):
        return {"ok": False, "error": "Its window has closed.",
                "campaign": _stop(campaign, "the window closed")}

    remaining = int(campaign["budget_paise"]) - int(campaign.get("spent_paise") or 0)
    if remaining <= 0:
        return {"ok": False, "error": "Its budget is spent.",
                "campaign": _stop(campaign, "the budget was spent")}

    mine = [p for p in registry.scan() if p["agent"] in campaign["agent_ids"]]
    applied, skipped, escalated = [], [], []
    # Tracked so a campaign that can no longer afford anything can finish
    # rather than tick forever. "Budget spent" is not the only way to be
    # done — "what is left buys nothing" is the same state.
    unaffordable = 0

    for proposal in mine:
        if proposal["verdict"] == "escalated":
            # A campaign never approves on a person's behalf.
            escalated.append(proposal["headline"])
            continue
        if proposal["verdict"] != "allowed":
            skipped.append((proposal["headline"], proposal["verdict_reason"]))
            continue
        cost = int(proposal["cost_paise"])
        if cost > remaining:
            unaffordable += 1
            skipped.append((proposal["headline"],
                            f"₹{cost / 100:,.2f} is more than the "
                            f"₹{remaining / 100:,.2f} left in this campaign."))
            continue

        result = registry.apply(proposal, campaign_id=campaign_id)
        if result.get("ok"):
            applied.append({"headline": proposal["headline"],
                            "offer_id": result["offer_id"],
                            "cost_paise": cost})
            remaining -= cost
            campaign["spent_paise"] = int(campaign.get("spent_paise") or 0) + cost
            campaign["applied"] = (campaign.get("applied") or []) + [result["offer_id"]]
        else:
            # The gate can refuse at apply time even having allowed at scan
            # time — the budget may have moved since. That is the point of
            # re-gating rather than trusting the queue.
            skipped.append((proposal["headline"], result.get("reason", "")))

    campaign["ticks"] = int(campaign.get("ticks") or 0) + 1
    campaign["last_tick_at"] = now
    _db().collection(COLLECTION).document(campaign_id).set(campaign)

    if remaining <= 0:
        _stop(campaign, "the budget was spent")
    elif unaffordable and not applied:
        # Everything on offer costs more than what is left. The envelope is
        # not literally empty, but it can no longer buy anything the agents
        # propose, and a campaign that ticks forever without acting is the
        # failure this design is supposed to avoid.
        _stop(campaign,
              f"the remaining ₹{remaining / 100:,.2f} is too small for "
              f"anything the agents propose")

    return {"ok": True, "campaign": campaign, "applied": applied,
            "escalated": escalated, "skipped": skipped,
            "remaining_paise": max(0, remaining)}


def measure(campaign_id: str) -> dict:
    """
    What the campaign actually achieved, with the sample stated.

    Attribution is deliberately narrow: an offer counts as converted only
    if the checkout it was attached to was subsequently paid. No modelled
    uplift, no "influenced revenue" — those need a control group this store
    does not have the traffic for, and inventing one would be the most
    flattering possible lie.
    """
    campaign = get(campaign_id)
    if not campaign:
        return {"ok": False, "error": "No such campaign."}

    try:
        from app.merchant import store
        offers = [d.to_dict() or {} for d in
                  _db().collection("growth_offers")
                       .where("campaign_id", "==", campaign_id).stream()]
        sessions = {s.get("id"): s for s in
                    [d.to_dict() or {}
                     for d in store.db.collection(store.SESSIONS).stream()]}
    except Exception as exc:
        return {"ok": False, "error": f"Could not read outcomes: {exc}"}

    converted = recovered = 0
    for offer in offers:
        session = sessions.get(offer.get("target_id")) or {}
        if (session.get("status") or "") == "paid":
            converted += 1
            recovered += int(session.get("total_paise") or 0)

    spent = int(campaign.get("spent_paise") or 0)
    note = (
        f"{converted} of {len(offers)} offer(s) placed by this campaign were "
        f"attached to a checkout that was later paid."
    )
    if len(offers) < 5:
        note += (" That is too few to read as a rate — it is a count of what "
                 "happened, not evidence that the campaign caused it. No "
                 "control group exists here, so no uplift is claimed.")

    return {
        "ok": True,
        "campaign_id": campaign_id,
        "goal": campaign.get("goal"),
        "state": campaign.get("state"),
        "offers_placed": len(offers),
        "converted": converted,
        "margin_committed_paise": spent,
        "revenue_recovered_paise": recovered,
        "sample_size": len(offers),
        "note": note,
    }
