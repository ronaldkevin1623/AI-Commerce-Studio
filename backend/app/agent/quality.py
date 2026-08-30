"""
HOW GOOD IS THIS LISTING — from signals eBay publishes, never from a guess.

Ranking by price alone answers the wrong question. Nobody wants the cheapest
thing; they want the best thing they can have for their money, and the
cheapest listing in a result set is often cheap for a reason. This scores
what is actually knowable about a listing so the budget can be spent rather
than merely respected.

Four real signals, in the order they deserve trust:

  Product reviews — genuine stars and a review count from eBay's catalogue.
  The strongest evidence available, and the rarest: roughly a quarter of
  listings carry any, so this cannot be the only input.

  Seller reputation, weighted by volume. A percentage on its own is
  misleading — 100% across 72 sales is a weaker claim than 99.8% across
  400,000 — so the percentage is pulled toward the market average in
  proportion to how little evidence stands behind it. Small samples move
  the score less, which is what "not enough evidence" should mean.

  eBay's top-rated badge, awarded against their own service criteria.

  Condition, ranked by the coded id rather than by matching strings.

What this deliberately does not do is invent a number when a signal is
missing. An unknown stays unknown and simply does not contribute, because
"no reviews" is not "bad reviews", and the difference matters when the
result decides where someone's money goes.
"""

# How close two quality scores must be before price is allowed to decide
# between them. See value_key for why this is five and not ten or two.
BAND_WIDTH = 5

# What using the whole budget is worth, in quality points, when the request
# asks for the best of something.
#
# Within a category price is the only proxy for capability in this data —
# nothing in a listing says an S25 is a better phone than an S20 — and a
# stated budget is a statement about which class of thing was meant. Fifteen
# points is enough to move a modern handset above an older one with a
# slightly better seller, and nowhere near enough to lift a listing the
# quality score genuinely distrusts.
CAPABILITY_WEIGHT = 15.0

# The market average a thin reputation is pulled toward, and how much
# evidence it takes to escape it. 97% is roughly the eBay baseline: sellers
# below it are unusual, so a small sample should not read as excellent.
_PRIOR_FEEDBACK = 97.0
_PRIOR_WEIGHT = 200

# The same idea applied to the overall score. A listing known only by its
# condition should sit near the middle, not at the top: 70 is "unremarkable
# but not suspect", and the prior weight is roughly a third of a fully
# evidenced listing, so real evidence still dominates once it exists.
_NEUTRAL_SCORE = 70.0
_EVIDENCE_PRIOR = 4.0

# eBay condition ids. Higher is better; anything unlisted scores neutral.
_CONDITION_RANK = {
    "1000": 1.0,   # New
    "1500": 0.9,   # New other
    "1750": 0.85,  # New with defects
    "2000": 0.8,   # Certified refurbished
    "2010": 0.75,  # Excellent refurbished
    "2020": 0.7,   # Very good refurbished
    "2030": 0.65,  # Good refurbished
    "2500": 0.6,   # Seller refurbished
    "3000": 0.5,   # Used
    "4000": 0.4,   # Very good
    "5000": 0.35,  # Good
    "6000": 0.3,   # Acceptable
    "7000": 0.0,   # For parts or not working
}


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def shrunk_feedback(percent, count):
    """
    A reputation percentage discounted by how little evidence supports it.

    Returns None when there is no percentage at all — the caller must treat
    that as unknown rather than substituting a value.
    """
    pct = _num(percent)
    if pct is None:
        return None

    n = _num(count, 0) or 0

    # eBay reports 0.0% for a seller nobody has rated yet. Reading that as
    # "rated zero percent" invents the worst possible reputation out of an
    # absence of evidence — the same fabrication as the invented 4.0 star
    # rating this module replaced, pointing the other way. No ratings means
    # unknown, and unknown does not contribute.
    if n <= 0:
        return None

    return (pct * n + _PRIOR_FEEDBACK * _PRIOR_WEIGHT) / (n + _PRIOR_WEIGHT)


def assess(product: dict) -> dict:
    """
    A 0–100 quality score, plus the signals it was actually built from.

    `basis` lists only signals that were present, ordered by how much each
    says about the product itself — reviews, then who made it, then who is
    selling it, then its condition. The explanation quotes the front of this
    list, so the order decides what the agent offers as its reason.

    A listing scored on two signals and one scored on four are not equally
    well understood, and the caller can see which is which instead of
    comparing two bare numbers.
    """
    parts = []      # (weight, 0-1 value)
    basis = []

    stars = _num(product.get("review_stars"))
    reviews = _num(product.get("review_count"), 0) or 0
    if stars is not None and reviews > 0:
        # Confidence grows with review count and saturates; 20 reviews is
        # treated as a solid sample, 2 is not.
        confidence = min(1.0, reviews / 20.0)
        parts.append((5.0 * confidence, stars / 5.0))
        basis.append(f"{stars:g} stars from {int(reviews)} reviews")

    # How established the maker is in this category, by eBay's own listing
    # counts. Weighted below reviews and seller record deliberately: a big
    # brand says something about the maker, not about whether this
    # particular listing is genuine.
    standing = product.get("brand_standing") or {}
    if standing.get("score") is not None:
        parts.append((1.5, standing["score"]))
        n = int(standing["listings"])
        basis.append(f"{standing['brand']} — {n:,} "
                     f"listing{'' if n == 1 else 's'} in this category on eBay")

    feedback = shrunk_feedback(product.get("seller_feedback"),
                               product.get("seller_feedback_count"))
    if feedback is not None:
        # Map 90–100% onto 0–1; below 90 on eBay is genuinely poor.
        value = max(0.0, min(1.0, (feedback - 90.0) / 10.0))
        parts.append((3.0, value))
        count = int(_num(product.get("seller_feedback_count"), 0) or 0)
        raw = _num(product.get("seller_feedback"))
        # count is always > 0 here — shrunk_feedback returns None otherwise —
        # so the sentence can state the sample size without a fallback that
        # would print "seller 0%" for a seller nobody has rated.
        basis.append(f"seller {raw:g}% over {count:,} ratings")

    if product.get("top_rated_seller"):
        parts.append((1.0, 1.0))
        basis.append("eBay top-rated seller")

    rank = _CONDITION_RANK.get(str(product.get("condition_id") or ""))
    if rank is not None:
        parts.append((2.0, rank))
        basis.append(str(product.get("condition") or "condition known").lower())

    if product.get("returns_accepted"):
        parts.append((0.5, 1.0))
        basis.append("returns accepted")

    if not parts:
        return {"score": None, "basis": [], "confidence": "unknown"}

    total_weight = sum(w for w, _ in parts)
    raw_score = sum(w * v for w, v in parts) / total_weight * 100

    # Shrink toward neutral by how little evidence there is — the same
    # correction applied to a seller's percentage, for the same reason.
    #
    # Without it, a listing whose only known signal is "New" scores a
    # flawless 100 on one data point and outranks a listing with 298 reviews
    # and 400,000 seller ratings behind a 96.9. A weighted average of one
    # perfect signal is perfect, which is exactly the wrong summary of "we
    # barely know anything about this."
    effective = ((raw_score * total_weight + _NEUTRAL_SCORE * _EVIDENCE_PRIOR)
                 / (total_weight + _EVIDENCE_PRIOR))

    # How much of the possible evidence was actually available.
    confidence = ("high" if total_weight >= 9 else
                  "medium" if total_weight >= 5 else "low")

    return {
        "score": round(effective, 1),
        "basis": basis,
        "confidence": confidence,
        # Kept so the shrinkage is inspectable rather than mysterious.
        "unshrunk_score": round(raw_score, 1),
        "evidence_weight": round(total_weight, 1),
    }


def value_key(product: dict, budget_paise: int = 0, bias: str = "neutral"):
    """
    Sort key for "the best one I can have for this money".

    Quality leads. Price only separates listings of genuinely similar
    quality, so a slightly dearer listing that is clearly better wins, while
    two comparable listings are settled by price. Quality is banded rather
    than compared exactly, because a fraction of a point in a score built
    from partial evidence is noise, not a preference.

    The width was measured, not chosen by taste. At ten points a listing
    scoring 90.7 shared a band with one scoring 98.9, and price handed the
    result to a ₹93 lot listing over a ₹450 one that was clearly better —
    the exact failure this ranking exists to prevent. At two points the
    banding paid ₹581 more for a 1.6-point gain, which is buying noise.
    Five keeps the worst observed gap to 1.6 points while leaving price
    something real to decide.

    A stated budget also says what *class* of thing is wanted. Someone who
    says ₹30,000 for a phone is describing the kind of phone they mean, so
    among listings of equal quality the one that uses the budget is closer to
    the request than the one that leaves most of it unspent. Without a stated
    budget there is no such signal and the cheaper of two equals wins.

    Saying "cheapest" still ranks by price outright — this only governs what
    happens when the request does not say.
    """
    assessment = assess(product)
    score = assessment["score"]
    price = _num(product.get("price_paise"), 0) or 0

    if score is None:
        # Nothing is known about it. It sorts behind everything that has
        # evidence, rather than being assumed average.
        return (99, price)

    # "Best … under N" is a request about the product. Add what the listing
    # spends of the budget to its score rather than widening the band around
    # it: banding made the result depend on which side of a boundary two
    # scores happened to fall, so five points decided it in one case and six
    # did not in another.
    if bias == "best" and budget_paise:
        share = min(1.0, price / budget_paise) if price else 0.0
        effective = score + CAPABILITY_WEIGHT * share
        # Ranked outright, not banded — the capability term is already
        # continuous, so a band would only reintroduce the edge it replaced.
        return (-effective, -price)

    band = -int(score // BAND_WIDTH)
    if budget_paise:
        # Everything here is already within the ceiling, so "closest to the
        # budget" is the dearest of the band.
        return (band, -price)
    return (band, price)


def annotate(candidates: list[dict]) -> list[dict]:
    """Attach the assessment to each listing, in place, and return them."""
    for product in candidates:
        product["quality"] = assess(product)
    return candidates
