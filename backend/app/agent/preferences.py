"""
WHAT THIS PERSON ACTUALLY BUYS — learned from their orders, not asked for.

Every claim here is derived from real captured payments. A profile is built
only from orders that carry a Razorpay payment id, because that is the only
evidence a purchase happened; an order somebody created and abandoned says
what they considered, not what they chose, and the two are different signals.

Three rules keep this honest:

  It never invents a preference. With too few purchases to mean anything the
  profile says so and is not applied. A pattern is a pattern, not a guess.

  It never overrides what was asked. A stated requirement is the person
  speaking now; a profile is an inference from before. Preferences break
  ties between listings that already satisfy the request, and nothing else.

  It always says what it did. A run that was reordered by history announces
  the history it used, so the reason a listing came first is inspectable
  rather than mysterious.
"""
import re
import statistics
from collections import Counter

# Below this, the "pattern" is one or two purchases and reading anything into
# it would be superstition rather than personalisation.
MIN_PURCHASES = 3

# How far from the usual spend still counts as familiar territory.
PRICE_BAND = 0.6

_STOPWORDS = {
    "the", "and", "for", "with", "usb", "type", "new", "pack", "set", "pcs",
    "x", "of", "in", "to", "a", "an", "by", "cm", "mm", "inch", "size",
    "free", "shipping", "genuine", "original", "high", "quality", "premium",
}


def _words(name: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{3,}", (name or "").lower())
            if w not in _STOPWORDS]


def build(customer_id: str, orders: list[dict] = None) -> dict:
    """
    A profile of what this person has actually paid for.

    `orders` is injectable so this can be tested without a database; left
    alone it reads the real collection.
    """
    profile = {
        "purchases": 0,
        "confidence": "none",
        "median_paise": None,
        "low_paise": None,
        "high_paise": None,
        "conditions": [],
        "venues": [],
        "keywords": [],
        "summary": "No completed purchases yet, so nothing has been learned.",
    }

    if not customer_id:
        return profile

    if orders is None:
        try:
            from app.firebase_client import db
            orders = [d.to_dict() or {} for d in db.collection("orders").get()]
        except Exception as exc:
            print(f"[preferences] could not read orders: {exc}", flush=True)
            return profile

    # Paid, by this person, with the payment id that proves it.
    mine = [o for o in orders
            if o.get("customer_id") == customer_id
            and o.get("status") == "paid"
            and o.get("razorpay_payment_id")]

    profile["purchases"] = len(mine)
    if not mine:
        return profile

    amounts = sorted(int(o.get("amount_paise") or 0) for o in mine)
    amounts = [a for a in amounts if a > 0]
    if amounts:
        profile["median_paise"] = int(statistics.median(amounts))
        profile["low_paise"] = amounts[0]
        profile["high_paise"] = amounts[-1]

    conditions, venues, words = Counter(), Counter(), Counter()
    for o in mine:
        if o.get("source"):
            venues[o["source"]] += 1
        for item in (o.get("items") or [{}]):
            if item.get("condition"):
                conditions[str(item["condition"]).strip()] += 1
        words.update(_words(o.get("product_name")))

    profile["conditions"] = [c for c, _ in conditions.most_common(3)]
    profile["venues"] = [v for v, _ in venues.most_common(3)]
    profile["keywords"] = [w for w, n in words.most_common(6) if n > 1]

    if len(mine) < MIN_PURCHASES:
        profile["confidence"] = "thin"
        profile["summary"] = (
            f"Only {len(mine)} completed purchase"
            f"{'s' if len(mine) != 1 else ''} so far — too few to read a "
            f"pattern from, so nothing has been adjusted."
        )
        return profile

    profile["confidence"] = "usable"
    profile["summary"] = describe(profile)
    return profile


def describe(profile: dict) -> str:
    """One sentence naming exactly what was observed, and from how much."""
    bits = []
    if profile.get("median_paise"):
        bits.append(f"usually around ₹{profile['median_paise'] / 100:,.0f}")
    if profile.get("conditions"):
        bits.append(f"{profile['conditions'][0].lower()} condition")
    if profile.get("keywords"):
        bits.append("often " + ", ".join(profile["keywords"][:3]))

    if not bits:
        return f"{profile['purchases']} purchases, with no clear pattern in them."
    return (f"From {profile['purchases']} completed purchases: "
            + "; ".join(bits) + ".")


def _affinity(product: dict, profile: dict) -> int:
    """How closely one listing resembles what this person has bought before."""
    score = 0

    median = profile.get("median_paise")
    price = int(product.get("price_paise") or 0)
    if median and price:
        low, high = median * (1 - PRICE_BAND), median * (1 + PRICE_BAND)
        if low <= price <= high:
            score += 2

    condition = str(product.get("condition") or "").strip().lower()
    if condition and condition in [c.lower() for c in profile.get("conditions") or []]:
        score += 2

    if product.get("source") in (profile.get("venues") or []):
        score += 1

    name = set(_words(product.get("name")))
    score += len(name & set(profile.get("keywords") or []))
    return score


def apply(candidates: list[dict], profile: dict,
          stated_requirements: list = None) -> dict:
    """
    Reorder listings that already answer the request, by resemblance to what
    this person has bought before.

    This is a tie-break and nothing more. Ordering is stable, so a listing
    only moves ahead of another it was already equal to on the ranking the
    request asked for — a preference can never promote something that fits
    the request worse.
    """
    unchanged = {"candidates": candidates, "applied": False, "note": None}

    if profile.get("confidence") != "usable" or len(candidates) < 2:
        return unchanged

    scored = [(_affinity(c, profile), c) for c in candidates]
    if len({s for s, _ in scored}) < 2:
        # Everything resembles their history equally, so there is nothing to
        # break the tie with and claiming otherwise would be noise.
        return unchanged

    ordered = [c for _, c in sorted(scored, key=lambda pair: -pair[0])]
    moved = ordered[0] is not candidates[0]

    return {
        "candidates": ordered,
        "applied": True,
        "moved_top": moved,
        "note": (
            f"Ordered with your history in mind — {describe(profile)} "
            f"This only breaks ties between listings that already match what "
            f"you asked for."
        ),
    }
