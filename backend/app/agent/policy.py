"""
THE TRANSACTION POLICY, AS ONE READABLE DOCUMENT.

Every bound in this project was already enforced somewhere — the spending
ceiling in `risk_gate`, the duplicate window beside it, the autonomy caps in
`settings`, the refusal to retry a failed payment in the fact that no code
path retries one. Enforced, but scattered: to answer "what exactly is this
agent allowed to do with my money" you had to read five modules.

This assembles that answer in one place, from the live values rather than a
copy of them, so the policy an agent quotes cannot drift from the policy the
gate applies. Change the auto-approve limit on the hive canvas and this
document changes on the next read.

TWO RULES ABOUT WHAT GOES IN HERE

A line may only appear if something actually enforces it. `auto_retry_payment:
false` is in this document because no code path in this project retries a
payment — not because it would look good next to the others. Where a claim
would be aspirational it is left out entirely; a policy document that
overstates itself is worse than no policy document, because it is the thing
people will quote in place of reading the code.

And every line names its enforcement point. `enforced_by` is a real module
and function you can go and read. If a bound cannot name where it is
applied, it does not belong here.
"""
from app.agent import settings

# Razorpay orders in this project are created in INR and nothing converts a
# charge into another currency. Listing prices sourced from eBay are USD
# converted at a fixed approximate rate — which is a display concern, and is
# disclosed separately rather than pretended away here.
CURRENCY = "INR"


def _int(node: str, key: str, fallback: int = 0) -> int:
    try:
        return int(settings.get(node, key) or 0)
    except Exception:
        return fallback


def transaction_policy() -> dict:
    """
    What may be spent, by whom, without a person — read live.

    Shaped so an agent can reason over it directly: every bound is a number
    with a unit in its key, and every entry says who enforces it.
    """
    auto_approve_inr = _int("risk", "auto_approve_limit_inr", 5000)
    duplicate_window = _int("risk", "duplicate_window_seconds")
    min_trust = _int("risk", "min_trust_score")
    max_per_window = _int("risk", "max_purchases_per_window")
    velocity_window = _int("risk", "velocity_window_seconds")
    session_ceiling_inr = _int("budget", "session_ceiling_inr")

    return {
        "version": 1,
        "currency": CURRENCY,
        "bounds": [
            {
                "key": "max_transaction_inr",
                "label": "Maximum transaction without approval",
                "value": auto_approve_inr,
                "unit": "INR",
                "on_breach": "escalated",
                "enforced_by": "app/agent/risk_gate.py::evaluate rule 4",
            },
            {
                "key": "session_ceiling_inr",
                "label": "Cumulative ceiling for one session",
                "value": session_ceiling_inr,
                "unit": "INR",
                "on_breach": "blocked",
                "enforced_by": "app/agent/budget_agent.py",
            },
            {
                "key": "max_purchases_per_window",
                "label": "Purchases allowed in the velocity window",
                "value": max_per_window,
                "unit": "purchases",
                "window_seconds": velocity_window,
                "on_breach": "escalated",
                "enforced_by": "app/agent/risk_gate.py::evaluate rule 5",
                "note": ("Every other bound judges one purchase alone, so an "
                         "agent buying ten different things just under the "
                         "limit satisfies all of them. This is the one that "
                         "sees the pattern."),
            },
            {
                "key": "duplicate_window_seconds",
                "label": "Same customer, same product, blocked within",
                "value": duplicate_window,
                "unit": "seconds",
                "on_breach": "blocked",
                "enforced_by": "app/agent/risk_gate.py::evaluate rule 2",
            },
            {
                "key": "min_trust_score",
                "label": "Minimum customer trust score to buy unattended",
                "value": min_trust,
                "unit": "score",
                "on_breach": "blocked",
                "enforced_by": "app/agent/risk_gate.py::evaluate rule 3",
            },
        ],
        "behaviours": [
            {
                "key": "require_approval_over_limit",
                "value": True,
                "statement": ("A purchase over the maximum is escalated to a "
                              "person. The agent that proposed it cannot clear "
                              "its own escalation — no exposed tool moves that "
                              "state."),
                "enforced_by": "app/agent/broker.py + /approvals",
            },
            {
                # True because nothing retries, not because a flag is off.
                "key": "auto_retry_payment",
                "value": False,
                "statement": ("A failed payment is never retried automatically. "
                              "No code path in this project re-attempts a "
                              "charge; the next attempt is a fresh, separately "
                              "gated and separately logged action taken by a "
                              "person."),
                "enforced_by": "absence — no retry exists to disable",
            },
            {
                "key": "max_payment_attempts_per_decision",
                "value": 1,
                "statement": ("One gate verdict authorises one charge. The "
                              "idempotency claim is an atomic create, so two "
                              "concurrent retries cannot both charge; a failed "
                              "operation releases its key, which makes the next "
                              "attempt a deliberate new one that is gated and "
                              "logged from scratch."),
                "enforced_by": "app/agent/idempotency.py — atomic create()",
            },
            {
                "key": "refund_initiated_by",
                "value": "human",
                "statement": ("No agent tool can issue a refund. The MCP tool "
                              "list has no refund tool at all, so this is not a "
                              "permission an agent could be granted by mistake "
                              "— a person issues it from the Orders page."),
                "enforced_by": "backend/mcp_server.py::TOOLS — no refund tool",
            },
            {
                "key": "payee_allowlist",
                "value": True,
                "statement": ("Money may only move to a venue the signed "
                              "mandate authorised."),
                "enforced_by": "app/agent/risk_gate.py::evaluate rule 6",
            },
        ],
        "disclosure": (
            "Read live from the same settings the gate reads, so this cannot "
            "drift from what is actually enforced. Every entry names the "
            "module that applies it."
        ),
    }


def check(amount_paise: int) -> dict:
    """
    Would this amount clear the spending bound, and by how much?

    The amount test alone — deliberately not the whole gate. `risk_gate` also
    weighs stock, trust, duplicates and velocity, and a screen that showed
    "within policy" from this function while the gate later refused on one of
    those would be worse than showing nothing. So the payload says outright
    that it is one bound of several.
    """
    limit_paise = _int("risk", "auto_approve_limit_inr", 5000) * 100
    amount_paise = int(amount_paise or 0)
    within = amount_paise <= limit_paise
    return {
        "amount_paise": amount_paise,
        "limit_paise": limit_paise,
        "currency": CURRENCY,
        "within_policy": within,
        "headroom_paise": limit_paise - amount_paise,
        "outcome": "may proceed" if within else "requires human approval",
        "checked": "the spending bound only",
        "not_checked": ["stock", "trust score", "duplicate window",
                        "velocity", "payee allowlist"],
        "note": ("This is one of six checks in the gate. Clearing it is not a "
                 "guarantee the purchase will be allowed — the gate rules on "
                 "all six at the moment of purchase."),
    }
