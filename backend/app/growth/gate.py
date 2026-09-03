"""
THE MERCHANT-SIDE GATE.

`risk_gate` stops the buying agent spending more of the shopper's money
than it was allowed. This stops the growth agents giving away more of the
merchant's than they were allowed. Same shape, same rules, opposite
pocket — and that symmetry is the point: the brief asks for every money
action to be explainable, bounded and gated, and a discount is a money
action even though nothing is charged.

Every bound here can only ever say no. None of them can widen anything, and
an agent cannot clear its own proposal — same rule the buyer's broker
follows, for the same reason.

FIVE BOUNDS, in the order they are cheapest to check:

    1. kill switch          growth off entirely
    2. per-action cap       the most one proposal may give away
    3. daily cap            the most all of them may give away today
    4. discount ceiling     a percentage bound, not just an absolute one,
                            because 20% off a cable and 20% off a laptop
                            are very different amounts of margin
    5. evidence floor       refuse to act on a sample too thin to mean
                            anything, unless the action costs nothing

The last one is the one a growth tool would normally leave out. A
recommendation from a sample of one is not a trend, and an agent that
spends real margin on it is guessing with the merchant's money.
"""
from app.agent import settings


def _dial(key: str, fallback):
    try:
        value = settings.get("growthgate", key)
        return fallback if value is None else value
    except Exception:
        return fallback


def spent_today_paise() -> int:
    """
    Margin already given away today by growth agents, from the log.

    Read from the decision log rather than a counter, because the log is
    the thing that gets audited. A separate tally could drift from it, and
    then the number a merchant is shown would not be the number anyone can
    check.
    """
    try:
        import time
        from app.firebase_client import db
        day_start = time.time() - (time.time() % 86400)
        total = 0
        for doc in db.collection("decisions").where(
                "action_type", "==", "growth_applied").stream():
            row = doc.to_dict() or {}
            stamp = row.get("timestamp")
            when = getattr(stamp, "timestamp", lambda: 0)()
            if when >= day_start:
                total += int(row.get("amount_paise") or 0)
        return total
    except Exception as exc:
        print(f"[growth] could not total today's spend: {exc}", flush=True)
        # Fail CLOSED: unknown spend is treated as the cap being used up,
        # so a datastore problem cannot become an unbounded giveaway.
        return int(_dial("daily_cap_inr", 500)) * 100


def evaluate(proposal) -> dict:
    """
    Decide whether a growth proposal may be applied.

    Returns {verdict, reason}. `escalated` means a human must approve —
    the same escalation the buyer's risk gate uses, landing in the same
    Approvals queue.
    """
    cost = int(proposal.cost_paise or 0)

    if not _dial("enabled", False):
        return {"verdict": "blocked",
                "reason": "Growth agents are switched off. Nothing they "
                          "propose can be applied until that is turned on."}

    per_action = int(_dial("max_giveaway_inr", 200)) * 100
    if cost > per_action:
        return {"verdict": "escalated",
                "reason": f"₹{cost / 100:,.2f} is more than the ₹{per_action / 100:,.0f} "
                          f"a single growth action may give away. A person has "
                          f"to approve it."}

    daily = int(_dial("daily_cap_inr", 500)) * 100
    already = spent_today_paise()
    if already + cost > daily:
        return {"verdict": "blocked",
                "reason": f"₹{already / 100:,.2f} of today's ₹{daily / 100:,.0f} "
                          f"growth budget is already committed; this would take "
                          f"it to ₹{(already + cost) / 100:,.2f}."}

    pct = int(proposal.params.get("discount_pct") or 0)
    ceiling = int(_dial("max_discount_pct", 15))
    if pct > ceiling:
        return {"verdict": "escalated",
                "reason": f"{pct}% off is deeper than the {ceiling}% ceiling. "
                          f"A percentage bound matters as much as a rupee one — "
                          f"the same discount is very different margin on a "
                          f"cable and on a laptop."}

    # Evidence last, and only for actions that actually cost something.
    floor = int(_dial("min_sample", 3))
    if cost > 0 and int(proposal.sample_size or 0) < floor:
        return {"verdict": "escalated",
                "reason": f"Only {proposal.sample_size} observation(s) behind "
                          f"this, below the {floor} needed to act on it "
                          f"unattended. It may well be right — but spending "
                          f"margin on a sample this thin is guessing, so a "
                          f"person decides."}

    return {"verdict": "allowed",
            "reason": (f"₹{cost / 100:,.2f} is within the ₹{per_action / 100:,.0f} "
                       f"per-action cap and today's remaining "
                       f"₹{(daily - already) / 100:,.2f}."
                       if cost else
                       "Costs the merchant nothing — it rearranges what is "
                       "already shown rather than giving anything away.")}
