"""
IF SOMEONE SAYS "ALUMINIUM", THEY MEAN ALUMINIUM.

The benchmark got the right category twenty times out of twenty and the right
*product* seventeen times. All three misses were the same shape: a stated
attribute treated as a preference rather than a condition.

  "braided usb-c cable 2 metre" -> a cable that is neither braided nor 2m
  "laptop stand aluminium"      -> "360° Rotating Metal Laptop Stand"

Both picks scored well on quality and won, because attributes only nudged the
ranking. An attribute someone bothered to type is not a nudge — it is part of
what they asked for, and a listing that does not have it is not a better
answer for having a nicer seller.

Two things make this harder than substring matching.

  Units are written every way. "2 metre" appears as 2m, 2 m, 2M, 2 Meter,
  6.5ft. Matching the literal words would enforce the attribute only against
  sellers who happen to spell it the same way as the buyer.

  Enforcing an attribute nobody satisfies empties the page. So it stands down
  when too few listings carry it: a market where nothing is aluminium is a
  fact about the market, not a reason to return nothing.
"""
import re

# Attributes worth holding a listing to. Deliberately concrete — things a
# title states or does not. Vague qualities ("good", "premium") are not here
# because no title can be checked against them.
MATERIALS = {
    "cotton", "leather", "suede", "canvas", "mesh", "wool", "denim", "nylon",
    "silk", "linen", "polyester", "rubber", "silicone", "plastic", "metal",
    "steel", "stainless", "aluminium", "aluminum", "brass", "copper",
    "bamboo", "wooden", "wood", "glass", "ceramic", "porcelain", "titanium",
    "carbon",
}

COLOURS = {
    "black", "white", "red", "blue", "green", "yellow", "orange", "purple",
    "pink", "brown", "grey", "gray", "silver", "gold", "beige", "navy",
    "cream", "maroon", "teal", "olive", "bronze", "transparent",
}

# Construction and capability words that a title either claims or does not.
QUALIFIERS = {
    "braided", "polarized", "polarised", "insulated", "waterproof",
    "水proof", "wireless", "wired", "mechanical", "rechargeable", "dimmable",
    "foldable", "adjustable", "reversible", "stitched", "hot", "swappable",
    "unlocked", "refurbished", "magnetic", "shockproof", "backlit",
    "noise", "cancelling", "canceling", "bluetooth", "portable", "slim",
    "heavy", "duty", "non", "slip", "anti", "glare", "matte", "glossy",
}
QUALIFIERS.discard("水proof")

# Spellings of the same unit. A buyer writing "2 metre" and a seller writing
# "2m" mean the same cable.
_UNIT_ALIASES = [
    {"m", "metre", "metres", "meter", "meters"},
    {"cm", "centimetre", "centimetres", "centimeter", "centimeters"},
    {"mm", "millimetre", "millimetres", "millimeter", "millimeters"},
    {"inch", "inches", "in", '"'},
    {"ft", "foot", "feet"},
    {"gb", "gigabyte", "gigabytes"},
    {"tb", "terabyte", "terabytes"},
    {"mb", "megabyte", "megabytes"},
    {"kg", "kilo", "kilos", "kilogram", "kilograms"},
    {"g", "gram", "grams"},
    {"l", "litre", "litres", "liter", "liters", "ltr"},
    {"qt", "quart", "quarts"},
    {"ml", "millilitre", "millilitres", "milliliter", "milliliters"},
    {"w", "watt", "watts"},
    {"oz", "ounce", "ounces"},
]

# Longest spellings first: the alternation is ordered so "litre" wins over
# "l" and "metre" over "m". Left the other way round, "1.5 litre" matches
# just the "l" and the rest of the word is discarded.
_MEASURE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*"
    r"(millilitres|millilitres|milliliters|milliliter|millilitre|"
    r"centimetres|centimeters|centimetre|centimeter|"
    r"millimetres|millimeters|millimetre|millimeter|"
    r"kilograms|kilogram|gigabytes|gigabyte|terabytes|terabyte|"
    r"megabytes|megabyte|litres|liters|litre|liter|"
    r"metres|meters|metre|meter|inches|inch|quarts|quart|"
    r"ounces|ounce|grams|gram|watts|watt|feet|foot|"
    r"cm|mm|gb|tb|mb|kg|ml|qt|oz|ft|in|m|g|l|w)\b",
    re.IGNORECASE,
)

# How many listings must carry an attribute before it is enforced. Below
# this, the market simply does not offer it and refusing everything would
# answer a question nobody asked.
# 2G/3G/4G/5G. Matched before weights, which they are shaped exactly like.
#
# No space is the discriminator: nobody writes the network as "5 g" and
# nobody writes five grams as "5g". Not airtight — "gold chain 5g" means
# grams — but a spaced "5 g" stays a weight, which covers the cases where
# the unit is what was actually meant.
_NETWORK_RE = re.compile(r"\b([2345]g)\b", re.IGNORECASE)

MIN_SATISFYING = 2


def _aliases(unit: str) -> set:
    unit = unit.lower()
    for group in _UNIT_ALIASES:
        if unit in group:
            return group
    return {unit}


def required(user_text: str) -> list[dict]:
    """
    The attributes this request actually states.

    Each is returned with the forms a seller might write it in, so matching
    is about the attribute rather than the buyer's spelling of it.
    """
    text = (user_text or "").lower()
    found = []
    seen = set()

    # Network generations first. "5g" is identical in form to five grams and
    # would otherwise become a weight requirement on a phone search.
    for gen in _NETWORK_RE.findall(text):
        gen = gen.lower()
        if gen in seen:
            continue
        seen.add(gen)
        # Also claim the bare number so the measurement pass below skips it.
        seen.add(f"{gen[0]}g")
        found.append({
            "text": gen,
            "kind": "feature",
            "patterns": [rf"\b{re.escape(gen)}\b"],
        })

    for number, unit in _MEASURE_RE.findall(text):
        if f"{number}{unit}".lower() in seen:
            continue
        # Trim only a decimal tail: "2.0" -> "2", "1.5" stays. Stripping
        # "0" unconditionally turned 750 into 75 and 1000 into 1.
        if "." in number:
            number = number.rstrip("0").rstrip(".") or number
        key = f"{number}{unit.lower()}"
        if key in seen:
            continue
        seen.add(key)
        patterns = [
            rf"\b{re.escape(number)}\s*{re.escape(alias)}\b"
            for alias in _aliases(unit)
        ]
        found.append({
            "text": f"{number} {unit}",
            "kind": "measurement",
            "patterns": patterns,
        })

    for word in re.findall(r"[a-z]+", text):
        if word in seen:
            continue
        kind = ("material" if word in MATERIALS else
                "colour" if word in COLOURS else
                "feature" if word in QUALIFIERS else None)
        if not kind:
            continue
        seen.add(word)
        variants = {word}
        if word in {"aluminium", "aluminum"}:
            variants = {"aluminium", "aluminum"}
        elif word in {"polarized", "polarised"}:
            variants = {"polarized", "polarised"}
        elif word in {"grey", "gray"}:
            variants = {"grey", "gray"}
        found.append({
            "text": word,
            "kind": kind,
            "patterns": [rf"\b{re.escape(v)}" for v in variants],
        })

    return found


def satisfied(title: str, attribute: dict) -> bool:
    """Does this listing claim the attribute, in any of its spellings?"""
    text = (title or "").lower()
    return any(re.search(p, text, re.IGNORECASE) for p in attribute["patterns"])


def enforce(candidates: list[dict], attributes: list[dict],
            min_satisfying: int = MIN_SATISFYING) -> dict:
    """
    Hold listings to the attributes the request stated.

    Each attribute is applied on its own, and only when enough listings carry
    it. An attribute the market does not offer is skipped and named in the
    note, so the run can say "nothing here is aluminium" rather than quietly
    returning something that is not.
    """
    kept = list(candidates)
    applied, skipped = [], []

    # Viability is judged against the whole result set, not against whatever
    # a previous attribute happened to leave behind. Applied in sequence, the
    # second attribute always sees a smaller pool and can fall under the
    # threshold on that account alone — which is how "braided 2 metre"
    # enforced the length, found only one braided cable left, and quietly
    # stopped requiring braided.
    viable = []
    for attribute in attributes or []:
        count = sum(1 for c in candidates if satisfied(c.get("name"), attribute))
        if count >= min_satisfying:
            viable.append(attribute)
        else:
            skipped.append((attribute["text"], count))

    # Applied together, most widely offered first, and never to the point of
    # emptying the set: an attribute that would leave nothing is reported
    # instead of returning no results at all.
    viable.sort(
        key=lambda a: -sum(1 for c in candidates if satisfied(c.get("name"), a))
    )
    for attribute in viable:
        matching = [c for c in kept if satisfied(c.get("name"), attribute)]
        if not matching:
            skipped.append((attribute["text"], 0))
            continue
        for item in kept:
            if item not in matching:
                item["attribute_miss"] = attribute["text"]
        kept = matching
        applied.append(attribute["text"])

    note = None
    if applied:
        note = "Held to " + ", ".join(f"'{a}'" for a in applied)
    if skipped:
        detail = ", ".join(
            f"'{name}' ({n} listing{'' if n == 1 else 's'})"
            for name, n in skipped
        )
        note = ((note + "; " if note else "")
                + f"too few listings offer {detail} to require it")

    return {
        "candidates": kept,
        "applied": applied,
        "skipped": [s[0] for s in skipped],
        "note": note,
    }
