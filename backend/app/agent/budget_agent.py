"""
BUDGET AGENT

Tracks what a customer has already spent and how a proposed purchase
sits against their ceiling. Distinct from the risk gate: the risk gate
judges one transaction in isolation, this one judges the running total.

Reads real spend from the customer's Firestore record, which is
incremented on every confirmed payment.
"""
from app.agent import settings


def assess(customer: dict, amount_paise: int) -> dict:
    # Both bounds are tunable from the Budget node on the hive canvas, and
    # any change to them is written to the audit trail as a financial bound
    # movement — see app/agent/settings.py.
    ceiling_paise = settings.get("budget", "session_ceiling_inr") * 100
    warn_at = settings.get("budget", "warn_at_pct") / 100

    spent = customer.get("total_spend_paise", 0) or 0
    projected = spent + (amount_paise or 0)
    ratio = projected / ceiling_paise if ceiling_paise else 0

    if projected > ceiling_paise:
        status = "exceeded"
        summary = (
            f"₹{projected/100:,.0f} would exceed the ₹{ceiling_paise/100:,.0f} ceiling"
        )
    elif ratio >= warn_at:
        status = "near_limit"
        summary = (
            f"₹{projected/100:,.0f} of ₹{ceiling_paise/100:,.0f} ceiling used"
        )
    else:
        status = "ok"
        summary = f"₹{projected/100:,.0f} of ₹{ceiling_paise/100:,.0f} ceiling"

    return {
        "status": status,
        "summary": summary,
        "spent_paise": spent,
        "projected_paise": projected,
        "ceiling_paise": ceiling_paise,
        "ratio": round(ratio, 3),
    }