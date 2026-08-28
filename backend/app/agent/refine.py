"""
FOLLOW-UP TURNS: NARROWING WHAT WAS ALREADY FOUND.

Every message used to start a fresh search. Saying "cheaper" after a result
set came back parsed "cheaper" as a whole new shopping request — no memory of
the twenty listings just retrieved, no idea what it was meant to be cheaper
than. So the only way to steer the agent was to retype the entire request
with one word changed, which is not how anyone talks to an assistant.

This keeps the last result set and applies the follow-up to it. "cheaper",
"only Sony", "under 3000", "not refurbished" all operate on listings already
in hand, which means they are instant, they cost no API calls, and — the
part that matters — they cannot introduce a product the agent never screened.

WHAT DECIDES BETWEEN REFINING AND SEARCHING AGAIN:
A follow-up refines only when it is made *entirely* of refinement operators.
"cheaper" refines; "cheaper laptop" is a new search, because it names a
product. That rule is strict on purpose: quietly filtering when someone meant
to start over is worse than searching when they meant to filter, since the
second is obvious on screen and the first looks like the agent ignoring them.
Either way the transcript says which one happened.

NOTHING HERE IS MODEL-JUDGED. Each operator is a pattern and a comparison
against a real field, so a refinement can be read off the code and predicted.
"""
import re
import statistics

from app.agent.ollama_agent import budget_ceiling_paise

# Phrases that only make sense against results already on screen.
_CHEAPER = re.compile(
    r"\b(cheap(er|est)?|less\s+expensive|lower\s+price|budget|affordable|"
    r"save\s+money|too\s+expensive|too\s+costly|lower)\b", re.IGNORECASE)
_PRICIER = re.compile(
    r"\b(dearer|pricier|more\s+expensive|higher\s+(end|price)|premium|"
    r"better\s+quality|nicer|upgrade)\b", re.IGNORECASE)
_NEWER = re.compile(r"\b(new|brand\s*new|unused|sealed)\b", re.IGNORECASE)
_NOT_USED = re.compile(r"\b(no|not|avoid|exclude|without)\s+(used|refurb\w*|second[\s-]?hand)\b",
                       re.IGNORECASE)
_MORE = re.compile(r"\b(more\s+(options|results|choices)|show\s+more|others?|"
                   r"alternatives?|anything\s+else)\b", re.IGNORECASE)
_EXCLUDE = re.compile(r"\b(?:not|no|exclude|without|avoid|except)\s+([a-z0-9][\w\- ]{1,24})",
                      re.IGNORECASE)
_ONLY = re.compile(r"\b(?:only|just|prefer)\s+([a-z0-9][\w\- ]{1,24})", re.IGNORECASE)

# Words that carry no product meaning, so their presence does not make a
# follow-up into a new search.
_FILLER = {
    "i", "want", "need", "show", "me", "the", "a", "an", "some", "something",
    "please", "can", "you", "give", "get", "find", "one", "ones", "it", "them",
    "is", "are", "be", "with", "for", "of", "and", "or", "but", "to", "in",
    "this", "that", "these", "those", "any", "make", "made", "under", "below",
    "over", "above", "than", "then", "rs", "inr", "rupees", "price", "priced",
    "cost", "costs", "option", "options", "result", "results", "listing",
    "listings", "product", "products", "item", "items", "thing", "things",
    "instead", "rather", "bit", "little", "much", "more", "less", "quality",
    # Meta-words that introduce an attribute without being one.
    "size", "sized", "fit", "shade", "variant", "version", "type", "kind",
    # The operator words themselves, so "new only" does not filter on "only".
    "only", "just", "prefer", "exclude", "without", "avoid", "except",
    "not", "no", "other", "another", "else",
}


# Words that describe a product rather than name one. A follow-up made only
# of these is narrowing what is already on screen: "red" after a shoe search
# means red shoes, not a fresh hunt for something called red.
#
# Curated deliberately. A colour missing from this list reads as a new
# product, which is the safe direction to be wrong in — the person sees a new
# search happen and can say so, rather than a filter silently swallowing the
# word.
_ATTRIBUTES = {
    # colour
    "red", "blue", "green", "black", "white", "grey", "gray", "silver",
    "gold", "pink", "purple", "yellow", "orange", "brown", "beige", "navy",
    "cream", "tan", "maroon", "teal", "olive", "rose", "bronze", "copper",
    "transparent", "multicolour", "multicolor", "colour", "color", "coloured",
    "colored",
    # material and finish
    "leather", "suede", "canvas", "mesh", "cotton", "wool", "denim", "nylon",
    "plastic", "metal", "steel", "aluminium", "aluminum", "wooden", "bamboo",
    "matte", "glossy", "rgb", "backlit",
    # size and fit
    "small", "medium", "large", "xl", "xxl", "mini", "compact", "slim",
    "lightweight", "portable", "tall", "wide", "narrow",
    # common qualifiers
    "wireless", "wired", "bluetooth", "waterproof", "rechargeable", "foldable",
    "adjustable", "gaming", "mechanical", "noise", "cancelling", "canceling",
}


def _singular(word: str) -> str:
    """Crudely, so "shoe" and "shoes" count as the same subject."""
    # 'boxes' -> 'box', 'dishes' -> 'dish'. Deliberately excludes a preceding
    # 'o': 'shoes' is 'shoe' plus an s, and stripping 'es' gave 'sho', which
    # matched nothing and made "red shoe" look like a new product.
    if len(word) > 4 and word.endswith("es") and word[-3] in "shxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _residue(text: str) -> set:
    """
    What is left of a follow-up once every operator is taken out.

    If anything meaningful survives, the person named something the previous
    search did not cover, and that is a new request rather than a filter.
    """
    stripped = text or ""
    for pattern in (_CHEAPER, _PRICIER, _NEWER, _NOT_USED, _MORE, _EXCLUDE, _ONLY):
        stripped = pattern.sub(" ", stripped)
    # Budget phrases are operators too.
    stripped = re.sub(
        r"\b(?:under|below|less\s+than|within|upto|up\s+to|max(?:imum)?|budget(?:\s+of)?)\s*"
        r"(?:rs\.?|inr|₹)?\s*[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:k|thousand|lakh)?",
        " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"[^a-zA-Z0-9\s]", " ", stripped)
    return {w for w in stripped.lower().split() if w and w not in _FILLER and len(w) > 1}


def parse(text: str, previous_query: str = "") -> dict:
    """
    Read a follow-up as a set of operations on the last result set.

    Returns {"refine": False} when the message names something new — the
    caller should run a fresh search rather than filtering.
    """
    text = (text or "").strip()
    if not text:
        return {"refine": False, "reason": "empty"}

    ops = {}
    if _CHEAPER.search(text):
        ops["direction"] = "cheaper"
    if _PRICIER.search(text):
        ops["direction"] = "pricier"
    if _MORE.search(text):
        ops["widen"] = True
    if _NOT_USED.search(text):
        ops["condition_exclude"] = ["used", "refurbished", "seller refurbished",
                                    "certified - refurbished", "excellent - refurbished"]
    elif _NEWER.search(text):
        ops["condition_only"] = ["new"]

    ceiling = budget_ceiling_paise(text)
    if ceiling:
        ops["max_price_paise"] = ceiling

    only = _ONLY.search(text)
    if only:
        ops["only"] = only.group(1).strip()

    exclude = _EXCLUDE.search(text)
    if exclude and not _NOT_USED.search(text):
        ops["exclude"] = exclude.group(1).strip()

    # Anything the follow-up names that the previous search did not is a new
    # request; anything it repeats is the person saying what they are still
    # shopping for. "cheaper laptop" after a laptop search narrows; the same
    # words after a headphone search start over.
    residue = _residue(text)
    known = {_singular(w) for w in re.split(r"[^a-z0-9]+", (previous_query or "").lower()) if w}

    # An attribute narrows; a word already in the last search is the person
    # restating their subject; anything else is a new request.
    attributes = sorted(w for w in residue if w in _ATTRIBUTES)
    novel = {w for w in residue
             if w not in _ATTRIBUTES and _singular(w) not in known}

    if novel:
        return {"refine": False, "reason": "names something new",
                "residue": sorted(novel)}

    if attributes:
        # Matched against listing titles, which is where colours and materials
        # actually appear. Words like "colour" itself carry no filter value.
        terms = [a for a in attributes if a not in
                 {"colour", "color", "coloured", "colored"}]
        if terms:
            ops["attributes"] = terms

    return {"refine": True, "ops": ops} if ops else {"refine": False, "reason": "no operators"}


def apply(candidates: list[dict], ops: dict, anchor_paise: int = None) -> dict:
    """
    Narrow the previous results.

    Each filter is applied only if something survives it. A follow-up is a
    preference, and answering "cheaper" with an empty screen helps nobody —
    better to say the request could not be met and leave the results standing.
    """
    rows = list(candidates or [])
    applied = []
    skipped = []

    def keep(subset, description):
        nonlocal rows
        if subset:
            rows = subset
            applied.append(description)
        else:
            skipped.append(description)

    ceiling = ops.get("max_price_paise")
    if ceiling:
        keep([c for c in rows if (c.get("price_paise") or 0) <= ceiling],
             f"under ₹{ceiling / 100:,.0f}")

    if ops.get("condition_only"):
        wanted = {w.lower() for w in ops["condition_only"]}
        keep([c for c in rows if (c.get("condition") or "").lower() in wanted],
             "new only")

    if ops.get("condition_exclude"):
        banned = {w.lower() for w in ops["condition_exclude"]}
        keep([c for c in rows if (c.get("condition") or "").lower() not in banned],
             "excluding used and refurbished")

    for term in ops.get("attributes") or []:
        keep([c for c in rows if term in (c.get("name") or "").lower()],
             f"'{term}' in the listing")

    if ops.get("only"):
        needle = ops["only"].lower()
        keep([c for c in rows if needle in (c.get("name") or "").lower()],
             f"matching '{ops['only']}'")

    if ops.get("exclude"):
        needle = ops["exclude"].lower()
        keep([c for c in rows if needle not in (c.get("name") or "").lower()],
             f"without '{ops['exclude']}'")

    direction = ops.get("direction")
    if direction and rows:
        prices = sorted(c["price_paise"] for c in rows if c.get("price_paise"))
        pivot = anchor_paise or (statistics.median(prices) if prices else 0)
        if direction == "cheaper":
            keep([c for c in rows if (c.get("price_paise") or 0) < pivot],
                 f"cheaper than ₹{pivot / 100:,.0f}")
        else:
            keep([c for c in rows if (c.get("price_paise") or 0) > pivot],
                 f"dearer than ₹{pivot / 100:,.0f}")

    if direction == "cheaper":
        rows = sorted(rows, key=lambda c: c.get("price_paise") or 0)
    elif direction == "pricier":
        rows = sorted(rows, key=lambda c: -(c.get("price_paise") or 0))

    if applied:
        summary = f"Narrowed to {len(rows)} — {'; '.join(applied)}"
    elif ops.get("widen"):
        summary = f"Showing more of the {len(rows)} already found"
    else:
        summary = f"Nothing to narrow on — keeping all {len(rows)}"

    if skipped:
        summary += f". Couldn't apply {'; '.join(skipped)} without emptying the list."

    return {"candidates": rows, "summary": summary, "applied": applied, "skipped": skipped}
