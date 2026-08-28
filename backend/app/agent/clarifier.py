"""
CLARIFYING QUESTIONS, BUILT FROM THE RESULTS THEMSELVES.

The agent used to read one sentence, guess what it meant, and spend money on
the guess. "A mechanical keyboard under 6000" says nothing about whether a
used board is acceptable, which brands are wanted, or how many. Those are
exactly the things a person would be asked in a shop, and asking them before
the mandate is signed is cheaper than getting them wrong afterwards.

THE RULE THAT SHAPES ALL OF THIS:
Every option offered is read off the listings actually retrieved. If the
result set contains three conditions, the condition question offers those
three, with counts. If no brand can be identified from the titles, the brand
question is not asked at all. A hardcoded "What colour?" with a colour list
nobody has would be fabricating the answer options — the same offence as
fabricating a price, and it would send the agent filtering on a field the
listings do not carry.

A question that would offer fewer than two real choices is dropped, because
it is not a question.
"""
import re
from collections import Counter

# Tokens that lead an eBay title often enough to be mistaken for a brand.
# Everything here is a descriptor, not a maker.
# Capacities, sizes and speeds lead a title as often as a maker does.
# "512GB" was being offered as a brand because it recurred across listings
# and is not a word in anybody's stopword list.
_MEASUREMENT_RE = re.compile(
    r"[0-9]+(?:\.[0-9]+)?(?:gb|tb|mb|kb|gh?z|mah|wh|w|v|mm|cm|inch|in|"
    r"ml|l|kg|g|hz|fps|mp|pcs?|k)?"
)

_NOT_A_BRAND = {
    "new", "used", "genuine", "original", "authentic", "premium", "pro", "max",
    "mini", "wireless", "wired", "bluetooth", "portable", "gaming", "smart",
    "usb", "type", "rgb", "led", "hd", "4k", "the", "for", "and", "with",
    "black", "white", "blue", "red", "grey", "gray", "green", "silver", "gold",
    "1pc", "2pcs", "set", "lot", "pack", "pair", "high", "super", "ultra",
    "best", "hot", "top", "big", "small", "large", "mens", "womens", "kids",
    "custom", "universal", "professional", "digital", "electric", "mechanical",
}


def _brand_options(candidates: list[dict], query: str = "") -> list[dict]:
    """
    Brands, inferred from the first meaningful token of each title.

    Marketplace titles overwhelmingly lead with the maker, so the leading
    token is a decent signal — but only when it recurs. A name appearing in
    one listing out of twenty-four is far more likely to be a stray adjective
    than a brand worth filtering on, so singletons are dropped rather than
    offered as a choice that would narrow the results to one item.

    Words from the search itself are excluded, which is the rule that stops
    the generic product noun leaking in: a search for "mechanical keyboard"
    was offering "Keyboard" as a brand, because plenty of titles lead with
    it. A token you searched for cannot be the thing that distinguishes one
    result from another, and this generalises where a longer stopword list
    would just lose the next round of whack-a-mole.
    """
    searched = {w for w in re.split(r"[^a-z0-9]+", (query or "").lower()) if w}
    leads = []
    for item in candidates:
        for raw in re.split(r"[\s,\-/|]+", (item.get("name") or "").strip()):
            token = re.sub(r"[^A-Za-z0-9]", "", raw)
            lowered = token.lower()
            if (len(token) < 2 or lowered in _NOT_A_BRAND or lowered in searched
                    or token.isdigit() or _MEASUREMENT_RE.fullmatch(lowered)):
                continue
            leads.append(token[:18])
            break

    counts = Counter(leads)
    frequent = [(name, n) for name, n in counts.most_common(4) if n >= 2]
    if len(frequent) < 2:
        return []

    return [{"value": name, "label": name, "count": n} for name, n in frequent]


def _condition_options(candidates: list[dict]) -> list[dict]:
    counts = Counter(
        (item.get("condition") or "").strip()
        for item in candidates
        if (item.get("condition") or "").strip()
    )
    if len(counts) < 2:
        return []
    return [
        {"value": name, "label": name, "count": n}
        for name, n in counts.most_common(4)
    ]


def _price_options(candidates: list[dict]) -> list[dict]:
    """
    Price bands drawn from where the results actually sit.

    Split at the median so both halves hold something. Fixed bands would put
    every result in one bucket as often as not, which tells nobody anything.
    """
    prices = sorted(item["price_paise"] for item in candidates if item.get("price_paise"))
    if len(prices) < 4:
        return []

    midpoint = prices[len(prices) // 2]
    cheaper = [p for p in prices if p < midpoint]
    dearer = [p for p in prices if p >= midpoint]
    if not cheaper or not dearer:
        return []

    rupees = lambda paise: f"₹{paise / 100:,.0f}"
    return [
        {"value": f"under:{midpoint}", "count": len(cheaper),
         "label": f"Under {rupees(midpoint)}"},
        {"value": f"from:{midpoint}", "count": len(dearer),
         "label": f"{rupees(midpoint)} and above"},
    ]


def already_stated(query: str, facet: str) -> bool:
    """
    Did the request already answer this?

    A question whose answer is sitting in the person's own sentence is not
    clarifying anything — it is asking them to repeat themselves, and it
    reads as though the agent did not listen. "sandisk 128gb pendrive"
    names a brand; there is nothing to ask.
    """
    text = (query or "").lower()
    if facet == "brand":
        # A brand is a word that is not a spec and not a generic product
        # noun. If the request has one of those beyond the obvious category
        # words, the maker has been named.
        for word in re.split(r"[^a-z0-9]+", text):
            if (len(word) > 2 and word not in _NOT_A_BRAND
                    and not word.isdigit()
                    and not _MEASUREMENT_RE.fullmatch(word)
                    and word not in _GENERIC_NOUNS):
                return True
        return False
    if facet == "condition":
        return any(w in text for w in
                   ("new", "used", "refurbished", "second hand", "open box", "sealed"))
    if facet == "quantity":
        # A number leading the request is a count — "2 new sandisk pendrives".
        # Requiring a unit word after it missed the most ordinary phrasing
        # there is. Numbers elsewhere in the sentence are left alone, because
        # "128gb" and "mx master 3" are specs, not counts.
        return bool(
            re.match(r"\s*(?:[2-9]|[1-9][0-9])\b", text)
            or re.search(r"\b(?:[2-9]|[1-9][0-9])\s*(?:x|pcs?|pieces?|units?|nos?)\b", text)
            or re.search(r"\b(?:two|three|four|five|six|pair\s+of|couple\s+of)\b", text)
        )
    return False


# Words that name a product type rather than a maker. Present so that
# "mechanical keyboard" is not mistaken for a stated brand.
_GENERIC_NOUNS = {
    "keyboard", "mouse", "phone", "mobile", "smartphone", "laptop", "tablet",
    "earbuds", "earphones", "headphones", "headset", "speaker", "monitor",
    "cable", "charger", "adapter", "hub", "drive", "pendrive", "pen",
    "sleeve", "bag", "case", "stand", "lamp", "watch", "camera", "printer",
    "router", "ssd", "hdd", "card", "battery", "screen", "display",
    "wireless", "bluetooth", "gaming", "mechanical", "portable", "external",
}


def build(candidates: list[dict], query: str = "") -> list[dict]:
    """
    The questions worth asking about this particular result set.

    Anything the request already answered is skipped. The point is to fill
    the gaps in what someone said, not to march them through a form.
    """
    questions = []

    condition = _condition_options(candidates)
    if condition and not already_stated(query, "condition"):
        questions.append({
            "id": "condition",
            "question": "Which condition works for you?",
            "type": "check",
            "options": condition,
            "note": f"From the {len(candidates)} listings found.",
        })

    # Asked as an open question rather than a list.
    #
    # The options were derived from whatever recurred in the listing titles,
    # which is fine when the results are right and actively misleading when
    # they are not — a pendrive search once offered "Lenovo" and "512GB" as
    # brands. A maker is something the person knows and can simply type, and
    # a free answer cannot be wrong in the way a generated list can.
    if not already_stated(query, "brand"):
        questions.append({
            "id": "brand",
            "question": "Any particular brand?",
            "type": "text",
            "options": [],
            "placeholder": "e.g. SanDisk — or leave blank for any",
            "note": "Leave it empty and every maker stays in.",
        })

    price = _price_options(candidates)
    if price:
        questions.append({
            "id": "price_band",
            "question": "Where in the price range?",
            "type": "radio",
            "options": price,
            "note": "Split at the median of these results.",
        })

    # Not a facet of the listings — a genuine input that changes the order
    # total and the stock check, which is why it is asked rather than assumed.
    if already_stated(query, "quantity"):
        return questions

    questions.append({
        "id": "quantity",
        "question": "How many do you need?",
        "type": "radio",
        "options": [
            {"value": "1", "label": "Just one"},
            {"value": "2", "label": "Two"},
            {"value": "3", "label": "Three"},
        ],
        # Three buttons cover the common cases and nothing else. Somebody
        # buying twelve of something should not have to give up and start
        # again, so the field takes a number directly.
        "allow_text": True,
        "placeholder": "or type a number",
        "note": "Checked against the seller's stock before anything is charged.",
    })

    return questions


def apply(candidates: list[dict], answers: dict) -> dict:
    """
    Narrow the results to what was asked for.

    Every filter can empty the list, and an empty list is worse than a loose
    one — so each is applied only if something survives it. A preference is a
    preference, not an instruction to return nothing.
    """
    answers = answers or {}
    applied = []
    rows = list(candidates)

    chosen = [v for v in (answers.get("condition") or []) if v]
    if chosen:
        kept = [c for c in rows if (c.get("condition") or "") in chosen]
        if kept:
            rows = kept
            applied.append(f"condition: {', '.join(chosen)}")

    brands = [v.lower() for v in (answers.get("brand") or []) if v]
    if brands:
        kept = [c for c in rows if any(b in (c.get("name") or "").lower() for b in brands)]
        if kept:
            rows = kept
            applied.append(f"brand: {', '.join(answers['brand'])}")

    band = answers.get("price_band")
    if isinstance(band, list):
        band = band[0] if band else None
    if band and ":" in str(band):
        edge, value = str(band).split(":", 1)
        try:
            cut = int(value)
        except ValueError:
            cut = None
        if cut is not None:
            kept = [c for c in rows
                    if (c["price_paise"] < cut if edge == "under" else c["price_paise"] >= cut)]
            if kept:
                rows = kept
                applied.append(
                    f"price {'under' if edge == 'under' else 'from'} ₹{cut / 100:,.0f}")

    quantity = answers.get("quantity")
    if isinstance(quantity, list):
        quantity = quantity[0] if quantity else None
    try:
        # A typed answer arrives as free text, so "3", " 3 " and "3 pcs" all
        # have to land on the same number, and anything unreadable falls back
        # to one rather than to zero.
        digits = re.sub(r"[^0-9]", "", str(quantity or ""))
        quantity = max(1, min(int(digits), 99))
    except (TypeError, ValueError):
        quantity = 1

    if applied:
        summary = f"Narrowed to {len(rows)} on {'; '.join(applied)}"
    else:
        summary = f"No narrowing applied — keeping all {len(rows)} listings"

    return {"candidates": rows, "quantity": quantity, "summary": summary,
            "applied": applied}
