"""
HOW ESTABLISHED IS THIS BRAND — measured, and labelled as what it measures.

The quality score could say whether a seller was reliable and whether a
listing had reviews, but nothing about whether the thing itself came from a
name anyone recognises. Asked for the best pendrive under ₹2,000, it had no
way to prefer SanDisk over a name invented last week.

Guessing brands out of titles was tried first and does not work: the tokens
that recur across listings are feature words — "cancelling", "noise",
"in-1" — not makers. So the brand names are not guessed here. eBay publishes
an aspect distribution for every search, naming each brand in the result set
and how many listings carry it, and that is what this reads.

What the number means, precisely: **how established a brand is within this
category on eBay**, by listing count. Nike shows 829,151 running-shoe
listings against Saucony's 53,600, and both are real. That is a defensible
proxy for recognition and it is not the same thing as global brand fame —
which is why the disclosure says "on eBay" and the score is never presented
as a measure of how good a product is.

Two values are treated as absence rather than as a verdict. eBay marks
listings "Unbranded" or "Not Specified", and neither means bad; they mean
nothing is claimed. They contribute no recognition, which lets a genuinely
branded listing rise without an unbranded one being punished for it.
"""
import re
import time

# eBay's own words for "no brand stated". Not a judgement, and not scored.
UNKNOWN_BRANDS = {"unbranded", "not specified", "generic", "no brand",
                  "does not apply", "n/a", "unbranded/generic"}

# Brand vocabularies are per query and stable for a run.
_MARKET_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 600


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def market(query: str, distributions: list = None) -> dict:
    """
    Brands present for this search, with the listing count behind each.

    `distributions` is the aspectDistributions block eBay returns alongside
    the results. Passing it avoids a second call; omitting it returns
    whatever was cached for this query, or nothing.
    """
    key = (query or "").strip().lower()
    now = time.time()

    if distributions is None:
        cached = _MARKET_CACHE.get(key)
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]
        return {}

    found = {}
    for dist in distributions or []:
        if str(dist.get("localizedAspectName") or "").lower() != "brand":
            continue
        for value in dist.get("aspectValueDistributions") or []:
            name = _clean(value.get("localizedAspectValue"))
            count = value.get("matchCount") or 0
            if not name or name.lower() in UNKNOWN_BRANDS:
                continue
            found[name] = max(found.get(name, 0), int(count))

    _MARKET_CACHE[key] = (now, found)
    return found


def identify(product: dict, vocabulary: dict) -> str | None:
    """
    Which of the brands eBay named for this search does this listing carry?

    Matched against the vocabulary rather than invented from the title, so a
    feature word can never be mistaken for a maker. Longest name first, so
    "New Balance" is not read as "Balance", and word-boundary anchored so
    "Bose" does not match inside another word.
    """
    stated = _clean(product.get("brand"))
    if stated and stated.lower() not in UNKNOWN_BRANDS:
        # eBay stated it on the listing itself; nothing to infer.
        for name in vocabulary:
            if name.lower() == stated.lower():
                return name
        return stated

    title = (product.get("name") or "")
    for name in sorted(vocabulary, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", title, re.IGNORECASE):
            return name
    return None


def recognition(brand: str | None, vocabulary: dict) -> dict:
    """
    A 0–1 standing for this brand within this category, and the count it
    came from — so the claim can be checked instead of trusted.

    Scaled against the largest brand in the same result set. Comparing a
    cable brand's few thousand listings against Nike's hundreds of thousands
    across categories would be meaningless; comparing it against the biggest
    cable brand is not.
    """
    if not brand or not vocabulary:
        return {"brand": brand, "score": None, "listings": None}

    count = vocabulary.get(brand)
    if not count:
        return {"brand": brand, "score": None, "listings": None}

    top = max(vocabulary.values()) or 1
    # Log scale: the gap between 50 and 5,000 listings matters far more than
    # the gap between 500,000 and 800,000.
    import math
    score = math.log10(count + 1) / math.log10(top + 1) if top > 1 else 1.0
    return {
        "brand": brand,
        "score": max(0.0, min(1.0, score)),
        "listings": int(count),
    }


def annotate(candidates: list[dict], query: str,
             distributions: list = None) -> list[dict]:
    """Attach brand standing to each listing, in place."""
    vocabulary = market(query, distributions)
    if not vocabulary:
        return candidates
    for product in candidates:
        name = identify(product, vocabulary)
        product["brand_standing"] = recognition(name, vocabulary)
    return candidates
