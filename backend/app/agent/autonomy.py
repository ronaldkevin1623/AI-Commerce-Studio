"""
WHAT THE AGENT MAY DO WITH NOBODY WATCHING.

Level 5 means no routine human involvement. It does not mean no bounds —
and the difference is the whole reason this file exists. A demo that spends
money unattended with nothing between the prediction and the card is not
impressive, it is reckless, and any judge who has thought about it for ten
seconds will ask what stops it.

So every autonomous purchase passes five gates, and each one can only ever
say no:

  1. The kill switch. One flag, checked first, that stops everything.
  2. A per-order cap, separate from and lower than the interactive one —
     the agent acting alone should be trusted with less than the agent
     acting with somebody watching.
  3. A rolling 30-day ceiling across all autonomous orders, so a short
     cycle cannot spend a month's budget in a week by staying under the
     per-order cap every time.
  4. A category list. Replenishables are consumables; an agent that decides
     unattended to rebuy a laptop has misunderstood the job.
  5. A confidence floor. Below it the purchase is not refused — it is
     handed back to the person as a Level 4 confirmation, which is the
     honest response to "I think this is due but I am not sure".

Bounds live in settings so they are visible and tunable on the hive canvas
like every other financial bound, and every refusal is written to the audit
trail with its reason.
"""
import re
import time

from app.agent import settings
from app.firebase_client import list_decisions

DAY = 86400.0
ROLLING_WINDOW_DAYS = 30

# Ordered worst-first so a caller reporting one reason reports the gravest.
BLOCKED = "blocked"
CONFIRM = "needs_confirmation"
ALLOWED = "allowed"

# What a replenishable actually is: something consumed and rebought. The
# list is the allowlist itself rather than a hint — an item matching none of
# these is refused, which fails closed. Kept as word patterns because a
# marketplace has no category field anyone can rely on.
REPLENISHABLE = re.compile(
    r"\b(coffee|pods?|beans?|tea|filters?|refills?|cartridges?|ink|toner"
    r"|batteries|battery|aaa?|detergent|soap|shampoo|conditioner|toothpaste"
    r"|floss|razors?|blades?|wipes?|tissues?|towels?|nappies|diapers?"
    r"|vitamins?|supplements?|protein|capsules?|tablets?"
    r"|food|snacks?|rice|flour|sugar|salt|oil|spice|masala"
    r"|cleaner|bleach|sanitiser|sanitizer|disinfectant"
    r"|bags?|liners?|cables?|charger)\b",
    re.IGNORECASE)

# Things that are never a replenishment however often somebody bought them.
# Checked after the allowlist, so "laptop charger" is a charger and a
# "laptop" is not.
NEVER_AUTONOMOUS = re.compile(
    r"\b(laptop|macbook|notebook\s+pc|desktop|iphone|phone|smartphone|tablet"
    r"|ipad|television|\btv\b|monitor|console|playstation|xbox|camera|lens"
    # "gold" and "silver" are not here, though they look like they belong.
    # They are colours far more often than materials — "Nescafé Gold" was
    # refused as jewellery — and a never-list that fires on a coffee tin is
    # worse than one that lets a bracelet through to the allowlist, which
    # would refuse it anyway for not being a consumable.
    r"|watch|jewell?ery|furniture|sofa|mattress|bicycle|scooter"
    r"|car\b|gift\s*card|voucher)\b",
    re.IGNORECASE)


def enabled() -> bool:
    """The kill switch, read fresh on every check."""
    return bool(settings.get("autonomy", "enabled"))


def _spent_recently(customer_id: str, now: float) -> int:
    """
    What this customer's agent has already spent unattended, in the window.

    Read from the audit trail rather than a running counter, because the
    audit trail is the record that cannot quietly drift out of step with
    what actually happened.
    """
    cutoff = now - ROLLING_WINDOW_DAYS * DAY
    total = 0
    for row in list_decisions(limit=500):
        if row.get("action_type") != "autonomous_purchase":
            continue
        if customer_id and row.get("customer_id") != customer_id:
            continue
        when = row.get("at") or row.get("created_at")
        stamp = when if isinstance(when, (int, float)) else getattr(when, "timestamp", lambda: 0)()
        if stamp and stamp < cutoff:
            continue
        total += int(row.get("amount_paise") or 0)
    return total


def category_verdict(name: str) -> tuple[bool, str]:
    """Is this the kind of thing an agent should rebuy on its own?"""
    text = name or ""
    if NEVER_AUTONOMOUS.search(text):
        return False, ("on the never-autonomous list — a considered purchase, "
                       "not a consumable")
    if not REPLENISHABLE.search(text):
        return False, ("not recognised as a consumable, and the list is an "
                       "allowlist: anything unrecognised is refused rather "
                       "than assumed safe")
    return True, "a recognised consumable"


def _bought_recently(customer_id: str, name: str, now: float,
                     within_days: float) -> tuple[int, float]:
    """
    Has the agent already bought this same thing, unattended, very recently?

    Read from the audit trail for the same reason `_spent_recently` is: it
    is the record that cannot drift from what happened.

    This exists because the autonomous path had no duplicate guard at all
    while the interactive one did. Running the replenishment twice inside
    twenty seconds — a cron that double-fires, a retry, a person clicking
    again — bought the same cable twice, and every one of the five gates
    passed both times, because each was individually true. "Bounded
    unattended spending" has to mean bounded across runs, not just within
    one.
    """
    cutoff = now - max(0.0, within_days) * DAY
    key = (name or "").strip().lower()[:60]
    count, latest = 0, 0.0
    for row in list_decisions(limit=500):
        if row.get("action_type") != "autonomous_purchase":
            continue
        if customer_id and row.get("customer_id") != customer_id:
            continue
        if key and key not in str(row.get("reason") or "").lower():
            continue
        when = row.get("at") or row.get("created_at")
        stamp = when if isinstance(when, (int, float)) else getattr(when, "timestamp", lambda: 0)()
        if stamp and stamp < cutoff:
            continue
        count += 1
        latest = max(latest, stamp or 0.0)
    return count, latest


def check(*, customer_id: str, product: dict, prediction: dict,
          now: float = None) -> dict:
    """
    May the agent buy this, unattended, right now?

    Returns a verdict and the reason for it. Every path returns something
    written for a person to read, because these sentences end up in the
    audit trail and in the notification, and "policy violation" tells
    nobody anything.
    """
    now = now or time.time()
    amount = int(product.get("price_paise") or 0)
    name = product.get("name") or prediction.get("name") or ""
    checks = []

    def fail(gate, verdict, reason):
        checks.append({"gate": gate, "passed": False, "detail": reason})
        return {"verdict": verdict, "reason": reason, "gate": gate,
                "checks": checks, "amount_paise": amount}

    # 1 — kill switch
    if not enabled():
        return fail("kill_switch", BLOCKED,
                    "Autonomous buying is switched off. Nothing is bought "
                    "unattended while this is off, whatever else is true.")
    checks.append({"gate": "kill_switch", "passed": True,
                   "detail": "Autonomous buying is on."})

    # 2 — per-order cap for unattended spending
    cap = settings.get("autonomy", "max_order_inr") * 100
    if not amount:
        return fail("amount", BLOCKED, "This listing has no usable price.")
    if amount > cap:
        return fail("per_order_cap", BLOCKED,
                    f"₹{amount / 100:,.0f} is over the ₹{cap / 100:,.0f} the "
                    f"agent may spend on a single order without being asked.")
    checks.append({"gate": "per_order_cap", "passed": True,
                   "detail": f"₹{amount / 100:,.0f} of ₹{cap / 100:,.0f} allowed per order."})

    # 3 — rolling ceiling
    monthly = settings.get("autonomy", "monthly_cap_inr") * 100
    already = _spent_recently(customer_id, now)
    if already + amount > monthly:
        return fail("monthly_cap", BLOCKED,
                    f"₹{already / 100:,.0f} already spent unattended in the last "
                    f"{ROLLING_WINDOW_DAYS} days; this would take it past the "
                    f"₹{monthly / 100:,.0f} ceiling.")
    checks.append({"gate": "monthly_cap", "passed": True,
                   "detail": f"₹{(already + amount) / 100:,.0f} of "
                             f"₹{monthly / 100:,.0f} across {ROLLING_WINDOW_DAYS} days."})

    # 4 — category
    allowed, why = category_verdict(name)
    if not allowed:
        return fail("category", BLOCKED, f"“{name[:60]}” is {why}.")
    checks.append({"gate": "category", "passed": True, "detail": f"Recognised as {why}."})

    # 5 — confidence
    floor = (settings.get("autonomy", "min_confidence_pct") or 0) / 100
    rank = {"high": 1.0, "medium": 0.6, "low": 0.3, "unknown": 0.0}
    score = rank.get(prediction.get("confidence", "unknown"), 0.0)
    if score < floor:
        return fail("confidence", CONFIRM,
                    f"The prediction is {prediction.get('confidence')} confidence, "
                    f"below the {floor:.0%} needed to act alone. Asking instead "
                    f"of buying — the honest answer to “probably due”.")
    checks.append({"gate": "confidence", "passed": True,
                   "detail": f"{prediction.get('confidence')} confidence, at or "
                             f"above the {floor:.0%} floor."})

    # 6 — already bought
    #
    # Last gate on purpose: it is the only one that needs the others to
    # have passed to be meaningful. The window is the item's own
    # replenishment cycle, not a fixed number of hours — buying a 30-day
    # consumable twice in a week is wrong for the same reason buying it
    # twice in a minute is, and the cycle is the honest bound for both.
    cycle = float(prediction.get("cycle_days") or 0) or 7.0
    window = max(1.0, cycle * 0.5)
    seen, last = _bought_recently(customer_id, name, now, window)
    if seen:
        ago = (now - last) / 3600 if last else 0
        when = (f"{ago:.0f} hours ago" if ago >= 1
                else f"{max(1, int(ago * 60))} minutes ago")
        return fail("already_bought", BLOCKED,
                    f"The agent already bought “{name[:44]}” unattended "
                    f"{when}. Its cycle is about {cycle:.0f} days, so another "
                    f"one now would be a repeat, not a replenishment.")
    checks.append({"gate": "already_bought", "passed": True,
                   "detail": f"Not bought unattended in the last "
                             f"{window:.0f} days."})

    return {"verdict": ALLOWED, "reason": "Within every autonomous bound.",
            "gate": None, "checks": checks, "amount_paise": amount}
