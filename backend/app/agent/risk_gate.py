"""
THE CORE OF THE PROJECT.

Every proposed purchase passes through here BEFORE any Razorpay API
is called. This is what makes the agent "explainable, bounded, and
gated" rather than a bare LLM-to-checkout pipe.

Returns one of: "allowed", "escalated", "blocked" — plus the reason,
which gets written verbatim to the audit trail.
"""
import time

from app.agent import settings

# In-memory recent-order cache for duplicate detection.
# (For the hackathon this is fine; a real system would query Firestore.)
_recent_orders: dict[str, float] = {}

# customer_id -> timestamps of purchases the gate allowed, trimmed to the
# velocity window on each read. In-process like the duplicate tracker above:
# both are bounds on one agent's behaviour in one session, not an accounting
# record, and the audit trail is where the durable history lives.
_purchase_times: dict[str, list] = {}


def evaluate(customer: dict, product: dict, record: bool = True,
             allowed_venues: set = None) -> dict:
    """
    `record=False` evaluates without remembering the attempt.

    The duplicate check works by noting each allowed purchase, which makes
    evaluate() quietly stateful — and that broke the propose/confirm split:
    proposing recorded the order, then confirming re-evaluated and rejected
    it as a duplicate of itself. A dry run must be able to ask "would this
    pass?" without the asking becoming the thing that fails it.
    """
    # Every bound below is tunable from the Risk node on the hive canvas.
    # These control how much money can move without a human, so changing
    # them is itself logged to the audit trail — see app/agent/settings.py.
    auto_approve_limit_paise = settings.get("risk", "auto_approve_limit_inr") * 100
    duplicate_window = settings.get("risk", "duplicate_window_seconds")
    min_trust_score = settings.get("risk", "min_trust_score")
    max_per_window = settings.get("risk", "max_purchases_per_window")
    velocity_window = settings.get("risk", "velocity_window_seconds")

    # Live marketplace data doesn't always carry every field, so read
    # defensively — a KeyError here would kill the agent mid-run.
    amount = product.get("price_paise")
    customer_id = customer.get("id")

    if not amount or amount <= 0:
        return _result("blocked", "Product has no usable price")

    # Rule 1 — stock check
    if product.get("stock", 1) <= 0:
        return _result("blocked", "Product is out of stock")

    # Rule 2 — duplicate order check (same customer, same product, recent)
    key = f"{customer_id}:{product.get('id')}"
    now = time.time()
    last_ordered = _recent_orders.get(key)
    if duplicate_window and last_ordered and (now - last_ordered) < duplicate_window:
        return _result(
            "blocked",
            f"Duplicate of an order placed {int(now - last_ordered)}s earlier"
        )

    # Rule 3 — trust score gate
    if customer.get("trust_score", 100) < min_trust_score:
        return _result(
            "blocked",
            "Customer trust score too low for autonomous purchase"
        )

    # Rule 4 — spending bound
    if amount > auto_approve_limit_paise:
        return _result(
            "escalated",
            f"Amount ₹{amount / 100:.2f} exceeds auto-approve limit "
            f"of ₹{auto_approve_limit_paise / 100:.2f}"
        )

    # Rule 5 — velocity
    #
    # Every check above looks at one purchase in isolation, so an agent
    # buying ten different things just under the limit satisfies all of them.
    # That is what a runaway loop looks like from the inside: not one bad
    # decision, but many defensible ones in a row.
    if max_per_window:
        recent = _purchase_times.get(customer_id, [])
        recent = [t for t in recent if now - t < velocity_window]
        _purchase_times[customer_id] = recent
        if len(recent) >= max_per_window:
            return _result(
                "escalated",
                f"{len(recent)} purchases in the last "
                f"{int(velocity_window / 60)} min — over the limit of {max_per_window}"
            )

    # Rule 6 — payee allowlist
    #
    # Money may only move to a venue the person's mandate authorised. The
    # constraint has been in the signed mandate from the start; until now
    # nothing read it.
    venue = (product.get("source") or "ebay").lower()
    if allowed_venues is not None and venue not in allowed_venues:
        return _result(
            "blocked",
            f"Seller '{venue}' is not in the authorised list "
            f"({', '.join(sorted(allowed_venues))})"
        )

    # All checks passed
    if record:
        _recent_orders[key] = now
        _purchase_times.setdefault(customer_id, []).append(now)
    return _result("allowed", "Within spending bound, stock verified")


def _result(decision: str, reason: str) -> dict:
    return {"decision": decision, "reason": reason}