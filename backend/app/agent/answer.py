"""
ANSWERING A QUESTION ABOUT THE RESULTS ON SCREEN

Every sentence this produces is built from a field of a real listing. The
model is not asked, and could not be: it has never seen these listings, so
anything it said about them would be invention dressed as an answer — and an
invented answer about a product someone is about to buy is the worst failure
this project could ship.

Which means the honest answer is often "the listing does not say". eBay
sellers write their own titles, and a title that does not mention water
resistance is not evidence of a product that lacks it; it is evidence of a
seller who did not mention it. Those two are different, and the wording here
keeps them different — it reports what the listing says, never what the
product is.

The question is matched to a field by what it asks about; when it matches
none, the listing's own text is searched for the words of the question, and
the excerpt is quoted back so a person can judge it themselves rather than
trusting a paraphrase.
"""
import re

# Question shapes, in the order they are tried. Each maps to a field this
# code can read; anything not here falls through to the text search.
_ASKS_PRICE = re.compile(r"\b(price|cost|costs|how\s+much|expensive|cheap)\b", re.I)
_ASKS_WHY = re.compile(r"\b(why|reason|how\s+come)\b", re.I)
_ASKS_COMPARE = re.compile(
    r"\b(difference|differences|differ|compare|versus|vs|better|best|worse"
    r"|which\s+(one|is|should))\b", re.I)
_ASKS_DELIVERY = re.compile(
    r"\b(deliver|delivery|arrive|arrives|arrival|ship|shipping|shipped"
    r"|postage|dispatch|how\s+long|when)\b", re.I)
_ASKS_SELLER = re.compile(r"\b(seller|sold\s+by|who\s+is|feedback|trustworthy|reliable)\b", re.I)
_ASKS_CONDITION = re.compile(r"\b(condition|new|used|refurbished|second\s?hand|open\s?box)\b", re.I)
_ASKS_REVIEWS = re.compile(r"\b(review|reviews|rating|ratings|stars|rated)\b", re.I)

# Which listing the question is about.
_ORDINALS = [
    (re.compile(r"\b(first|1st|top|cheapest)\b", re.I), 0),
    (re.compile(r"\b(second|2nd)\b", re.I), 1),
    (re.compile(r"\b(third|3rd)\b", re.I), 2),
    (re.compile(r"\b(fourth|4th)\b", re.I), 3),
    (re.compile(r"\b(fifth|5th)\b", re.I), 4),
]

# Words that carry no subject, so searching a listing for them proves nothing.
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "does", "do", "did", "it",
    "its", "this", "that", "these", "those", "them", "they", "there", "has",
    "have", "had", "can", "could", "will", "would", "should", "shall", "any",
    "and", "or", "but", "if", "of", "in", "on", "at", "to", "for", "with",
    "about", "from", "by", "be", "been", "being", "what", "which", "who",
    "how", "why", "when", "where", "one", "ones", "you", "your", "me", "my",
    "i", "tell", "more", "much", "many", "also", "too", "very", "really",
    "please", "thanks", "product", "listing", "item", "get", "got",
}


def _inr(paise):
    return f"₹{(paise or 0) / 100:,.0f}"


def _subject(candidates, text):
    """Which listing is being asked about — an ordinal, or the first."""
    for pattern, index in _ORDINALS:
        if pattern.search(text) and index < len(candidates):
            return candidates[index], index
    return candidates[0], 0


def _name(item, limit=52):
    title = item.get("name") or "this listing"
    return title[:limit] + ("…" if len(title) > limit else "")


def _terms(text):
    words = re.findall(r"[a-z0-9][a-z0-9\-]{1,}", (text or "").lower())
    return [w for w in words if w not in _STOPWORDS]


def _quote(item, term):
    """
    Where a word appears in the seller's own text, with a little context.

    A long word is also tried as its stem, because "waterproof" and the
    seller's "Water resistant IP52" are the same question and a literal
    match would report the listing as silent on it. The excerpt is quoted
    rather than summarised, so the person reads the seller's words and
    decides whether they answer what was asked.
    """
    needles = [term]
    if len(term) >= 7:
        needles.append(term[:5])

    for field, label in (("name", "the title"), ("description", "the description")):
        text = item.get(field) or ""
        for needle in needles:
            match = re.search(rf"\b\w*{re.escape(needle)}\w*\b", text, re.I)
            if match:
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 30)
                return label, (("…" if start else "")
                               + text[start:end].strip()
                               + ("…" if end < len(text) else ""))
    return None, None


def answer(text: str, candidates: list, pick_reason: str = "") -> str:
    """
    A sentence answering `text` from `candidates`, or an honest refusal.

    Never returns None: a question that reaches here has already been routed
    as being about these results, so silence would be the one response that
    tells the person nothing.
    """
    if not candidates:
        return "There are no results on screen to answer that about yet."

    item, index = _subject(candidates, text)
    position = ("the first", "the second", "the third",
                "the fourth", "the fifth")[index] if index < 5 else f"number {index + 1}"

    if _ASKS_WHY.search(text):
        if pick_reason:
            return f"I put {_name(item)} first because {pick_reason.rstrip('.')}."
        return (f"{_name(item)} came first on the ranking — seller record, "
                f"condition and reviews, in that order. No single reason was recorded "
                f"for this turn.")

    if _ASKS_COMPARE.search(text) and len(candidates) >= 2:
        def described(row):
            parts = [_inr(row.get("price_paise"))]
            if row.get("condition"):
                parts.append(row["condition"].lower())
            if row.get("seller_feedback") is not None:
                parts.append(f"seller {row['seller_feedback']}%")
            if row.get("review_count"):
                parts.append(f"{row['review_count']:,} reviews")
            return f"{_name(row, 40)} — " + ", ".join(parts)

        a, b = candidates[0], candidates[1]
        gap = abs((a.get("price_paise") or 0) - (b.get("price_paise") or 0))
        closer = "They cost the same." if gap == 0 else f"{_inr(gap)} apart."
        return f"The top two: {described(a)}; {described(b)}. {closer}"

    if _ASKS_PRICE.search(text):
        original = item.get("original_price_paise")
        extra = (f", down from {_inr(original)}"
                 if original and original > (item.get("price_paise") or 0) else "")
        return f"{_name(item)} is {_inr(item.get('price_paise'))}{extra}."

    if _ASKS_DELIVERY.search(text):
        days = item.get("delivery_days")
        window = item.get("delivery_estimate_from"), item.get("delivery_estimate_to")
        cost = item.get("shipping_cost_paise")
        if days or any(window):
            when = (f"in about {days} days" if days else
                    f"between {window[0]} and {window[1]}")
            postage = (" with free postage" if item.get("shipping_is_free")
                       else f" plus {_inr(cost)} postage" if cost else "")
            return (f"eBay estimates {_name(item)} arriving {when}{postage}. "
                    f"That is eBay's estimate for the listing, not a tracked shipment.")
        return f"The listing for {_name(item)} gives no delivery estimate."

    if _ASKS_SELLER.search(text):
        feedback = item.get("seller_feedback")
        count = item.get("seller_feedback_count")
        if feedback is None:
            return f"eBay reports no feedback score for the seller of {_name(item)}."
        return (f"The seller of {_name(item)} has {feedback}% positive feedback"
                + (f" across {count:,} ratings." if count else ", with no rating count given."))

    if _ASKS_REVIEWS.search(text):
        stars, count = item.get("review_stars"), item.get("review_count")
        if count:
            return f"{_name(item)} has {count:,} product reviews averaging {stars} stars."
        return (f"{_name(item)} carries no product reviews on eBay, so its quality "
                f"score comes from the seller's record and the item's condition.")

    if _ASKS_CONDITION.search(text):
        condition = item.get("condition")
        return (f"{_name(item)} is listed as “{condition}”." if condition
                else f"The listing for {_name(item)} does not state a condition.")

    # Nothing matched a field, so look for the question's own words in what
    # the seller wrote, and quote rather than paraphrase.
    for term in _terms(text):
        label, excerpt = _quote(item, term)
        if excerpt:
            return (f"{label.capitalize()} of {_name(item)} mentions “{term}”: "
                    f"“{excerpt}”. That is the seller's wording — I have not "
                    f"verified it.")

    asked = ", ".join(f"“{t}”" for t in _terms(text)[:3]) or "that"
    return (f"The listing for {position} result does not mention {asked}. "
            f"eBay sellers write their own titles, so this means it is unstated — "
            f"not that the product lacks it. The product page on eBay will have more.")
