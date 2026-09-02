"""
WHEN WILL THIS RUN OUT?

The consumption model behind Level 5's "predicts your needs, auto-places
orders of replenishables". It reads a customer's own paid orders, works out
how often they actually rebuy a thing, and says when the next one is due.

Deliberately a simple interval model, and deliberately honest about being
one. Two decisions carry most of the weight:

  It needs at least two purchases of the same item before it will predict
  anything. One purchase gives no interval, and the tempting fix — assume a
  category default, "coffee is a 30-day product" — would be inventing the
  central fact. A single purchase produces no prediction and says so.

  It reports how confident it is from the evidence it actually has: how many
  intervals it has seen, and how much they disagree. Somebody who reorders
  every 28, 30 and 29 days is predictable; somebody who reorders after 5,
  60 and 12 days is not, and the second case must not be dressed up as the
  first, because the whole point is that an order gets placed without anyone
  being asked.

An ML model could replace `_interval_stats` later and nothing else here
would change: everything downstream reads `due_at`, `confidence` and
`intervals_seen`, not how they were derived.
"""
import statistics
import time

# Two purchases give one interval, which is a coincidence rather than a
# pattern. Three give two intervals and something worth calling a cycle.
MIN_PURCHASES = 2
CONFIDENT_PURCHASES = 3

# How far the intervals may disagree before this stops claiming to know.
# Expressed as coefficient of variation — the spread relative to the length
# of the cycle, so a 3-day wobble means something different on a 7-day
# cycle than on a 90-day one.
STEADY_CV = 0.35
ERRATIC_CV = 0.75

# Nothing bought once a year is a replenishable in any useful sense, and a
# cycle under a day is a data error rather than a habit.
MIN_CYCLE_DAYS = 1
MAX_CYCLE_DAYS = 180

DAY = 86400.0


def _as_epoch(value):
    """Firestore timestamps, floats and datetimes all arrive here."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    for attr in ("timestamp",):
        fn = getattr(value, attr, None)
        if callable(fn):
            try:
                return float(fn())
            except Exception:
                return None
    return None


def _key(item: dict) -> str:
    """
    What counts as "the same thing bought again".

    The product id is exact but too strict for a marketplace: the same
    coffee relisted next month is a different eBay id, and a model that
    keyed on id alone would never see a second purchase. The normalised
    name is what a person means by "the same thing".
    """
    name = (item.get("name") or item.get("product_name") or "").strip().lower()
    return " ".join(name.split())[:80]


def _interval_stats(times: list[float]) -> dict | None:
    """Median cycle length and how much the intervals disagree."""
    if len(times) < MIN_PURCHASES:
        return None
    ordered = sorted(times)
    gaps = [(b - a) / DAY for a, b in zip(ordered, ordered[1:])]
    gaps = [g for g in gaps if MIN_CYCLE_DAYS <= g <= MAX_CYCLE_DAYS]
    if not gaps:
        return None

    median = statistics.median(gaps)
    spread = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
    cv = (spread / median) if median else 1.0
    return {"cycle_days": round(median, 1), "intervals": len(gaps),
            "spread_days": round(spread, 1), "cv": round(cv, 3),
            "last_at": ordered[-1]}


def _confidence(stats: dict, purchases: int) -> str:
    """
    How much this prediction should be trusted, from evidence alone.

    Two things have to be true for "high": enough repeats to call it a
    habit, and intervals that agree with each other. Either one failing
    drops it, because a confident-looking date derived from two wildly
    different gaps is the failure mode that spends someone's money on a
    guess.
    """
    if purchases < CONFIDENT_PURCHASES or stats["cv"] > ERRATIC_CV:
        return "low"
    if stats["cv"] <= STEADY_CV:
        return "high"
    return "medium"


def profile(orders: list[dict], now: float = None) -> list[dict]:
    """
    Every repeat-purchased item for one customer, with its next due date.

    Only paid orders count. An order that was created and never captured is
    a thing somebody looked at, not a thing they consume, and treating the
    two alike would have the agent reordering abandoned carts.
    """
    now = now or time.time()
    seen: dict[str, dict] = {}

    for order in orders or []:
        # "demo_paid" is seeded history, kept distinct from a real capture
        # everywhere else; the model reads both because a demo needs a past
        # to reason about, and reading it changes nothing about what "paid"
        # means to the integrity checks or to revenue.
        if (order.get("status") or "") not in ("paid", "demo_paid"):
            continue
        when = _as_epoch(order.get("created_at")) or _as_epoch(order.get("paid_at"))
        if when is None:
            continue

        items = order.get("items") or [{
            "name": order.get("product_name"),
            "price_paise": order.get("amount_paise"),
        }]
        for item in items:
            key = _key(item)
            if not key:
                continue
            row = seen.setdefault(key, {"key": key, "times": [], "last": item})
            row["times"].append(when)
            if when >= (_as_epoch(row["last"].get("_at")) or 0):
                row["last"] = {**item, "_at": when}

    predictions = []
    for row in seen.values():
        purchases = len(row["times"])
        stats = _interval_stats(row["times"])
        item = row["last"]

        if not stats:
            # Said out loud rather than filled in with a category default.
            predictions.append({
                "key": row["key"],
                "name": item.get("name") or row["key"],
                "purchases": purchases,
                "predictable": False,
                "reason": ("Bought once — there is no interval to measure yet, "
                           "and guessing one from the category would be "
                           "inventing the thing this is supposed to know."
                           if purchases < MIN_PURCHASES else
                           "The gaps between purchases are outside anything "
                           "that reads as a cycle."),
                "confidence": "unknown",
            })
            continue

        due_at = stats["last_at"] + stats["cycle_days"] * DAY
        predictions.append({
            "key": row["key"],
            "name": item.get("name") or row["key"],
            "product": {k: v for k, v in item.items() if not k.startswith("_")},
            "purchases": purchases,
            "predictable": True,
            "cycle_days": stats["cycle_days"],
            "intervals_seen": stats["intervals"],
            "spread_days": stats["spread_days"],
            "last_bought_at": stats["last_at"],
            "due_at": due_at,
            "days_until_due": round((due_at - now) / DAY, 1),
            "due": due_at <= now,
            "confidence": _confidence(stats, purchases),
        })

    predictions.sort(key=lambda p: p.get("due_at") or float("inf"))
    return predictions


def due_now(orders: list[dict], now: float = None) -> list[dict]:
    """The items whose predicted depletion date has arrived or passed."""
    return [p for p in profile(orders, now) if p.get("predictable") and p["due"]]


def explain(prediction: dict) -> str:
    """One sentence a person can check the arithmetic of."""
    if not prediction.get("predictable"):
        return prediction.get("reason", "Not predictable yet.")
    return (
        f"Bought {prediction['purchases']} times, about every "
        f"{prediction['cycle_days']:g} days"
        + (f" (±{prediction['spread_days']:g})" if prediction["spread_days"] else "")
        + f", across {prediction['intervals_seen']} "
        f"interval{'s' if prediction['intervals_seen'] != 1 else ''}. "
        f"Last bought "
        f"{max(0, round((time.time() - prediction['last_bought_at']) / DAY))} days ago, "
        f"so the next one is due "
        + ("now" if prediction["due"]
           else f"in {prediction['days_until_due']:g} days") + "."
    )
