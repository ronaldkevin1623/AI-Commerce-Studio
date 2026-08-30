"""
IS THIS THE CURRENT MODEL — answered from the result set, not from belief.

"Samsung mobile with good camera under 30000" returned a Galaxy S6 among its
results. The S6 is from 2015 and has not been made for years, and no amount
of seller reputation makes it a good answer to a request for a good camera.

The obvious fix is to ask the internet whether a model is still in
production. This project has no web-search integration, and adding one means
a paid API or scraping a search engine — so that check would either cost
money or be unreliable, and either way it would be a claim resting on
something outside the data.

There is a better answer available in the data already. Product lines are
numbered, and the numbering is ordered: a Galaxy S22 is later than a Galaxy
S7 because 22 is greater than 7. That is arithmetic, not knowledge, and it
holds for every brand that numbers its lines — Galaxy S, Note, Z Flip,
iPhone, Pixel, OnePlus, Redmi.

So the claim this module makes is deliberately narrow and provable: *within
this result set*, a Galaxy S7 is several generations behind the newest
Galaxy S on offer. It never asserts a release year, never asserts a product
is discontinued, and compares only within one line — an S22 and a Note20 are
different families and their numbers say nothing about each other.

What it cannot do is tell you a model is out of production. Nothing here
knows that, and the run says so rather than implying otherwise.
"""
import re

# Lines whose numbering runs forward. The prefix is the family; the number
# after it is the generation. Ordered longest-first so "galaxy z flip" is
# matched before "galaxy z", and "galaxy note" before "galaxy".
_LINES = [
    "galaxy z flip", "galaxy z fold", "galaxy note", "galaxy tab",
    "galaxy watch", "galaxy s", "galaxy a", "galaxy m", "galaxy f",
    "iphone", "ipad", "pixel", "oneplus", "redmi note", "redmi",
    "poco", "moto g", "nord", "mi ",
]

_LINE_RE = re.compile(
    r"\b(" + "|".join(re.escape(l).replace(r"\ ", r"\s*") for l in _LINES) +
    r")\s*(\d{1,3})\b",
    re.IGNORECASE,
)

# How far behind the newest of its own line a model may be before it stops
# being a reasonable answer to "the best". Two generations is roughly two
# years in phones — an S22 against an S25 is a fair suggestion, an S7 is not.
MAX_GENERATIONS_BEHIND = 3


def identify(title: str) -> tuple | None:
    """
    The product line and generation a title names, if it names one.

    Returns e.g. ("galaxy s", 22) or None. The line is normalised so
    "Galaxy S22", "GALAXY S 22" and "galaxy  s22" agree.
    """
    match = _LINE_RE.search(title or "")
    if not match:
        return None
    line = re.sub(r"\s+", " ", match.group(1).strip().lower())
    try:
        return line, int(match.group(2))
    except ValueError:
        return None


def newest_per_line(candidates: list[dict]) -> dict:
    """The highest generation on offer for each line in this result set."""
    newest = {}
    for product in candidates:
        found = identify(product.get("name"))
        if not found:
            continue
        line, gen = found
        newest[line] = max(newest.get(line, 0), gen)
    return newest


def generations_behind(product: dict, newest: dict):
    """
    How many generations behind the newest of its own line this is.

    None when the title names no numbered model, or when nothing else in the
    result set shares its line — with no sibling to compare against there is
    no claim to make.
    """
    found = identify(product.get("name"))
    if not found:
        return None
    line, gen = found
    latest = newest.get(line)
    if latest is None:
        return None
    return latest - gen


def annotate(candidates: list[dict]) -> list[dict]:
    """Attach line, generation and distance-from-newest to each listing."""
    newest = newest_per_line(candidates)
    for product in candidates:
        found = identify(product.get("name"))
        behind = generations_behind(product, newest)
        product["generation"] = {
            "line": found[0] if found else None,
            "number": found[1] if found else None,
            "behind": behind,
            "newest_seen": newest.get(found[0]) if found else None,
        }
    return candidates


def drop_superseded(candidates: list[dict],
                    max_behind: int = MAX_GENERATIONS_BEHIND) -> dict:
    """
    Set aside models several generations behind a newer one in the same set.

    Only ever applied when the person asked for the best of something — for
    any other request an older model at a lower price is a legitimate answer,
    and this would be deciding for them.

    Stands down if it would empty the field: a result set made entirely of
    older models still describes the market, and returning nothing would be
    a worse answer than returning what exists.
    """
    annotate(candidates)
    keep, superseded = [], []

    for product in candidates:
        behind = (product.get("generation") or {}).get("behind")
        if behind is not None and behind > max_behind:
            superseded.append(product)
        else:
            keep.append(product)

    if not keep:
        return {"candidates": candidates, "dropped": [], "note": None}

    note = None
    if superseded:
        examples = []
        for p in superseded[:2]:
            g = p["generation"]
            examples.append(f"{g['line'].title()}{g['number']} "
                            f"({g['behind']} behind {g['line'].title()}"
                            f"{g['newest_seen']})")
        note = (f"Set aside {len(superseded)} listing"
                f"{'' if len(superseded) == 1 else 's'} several generations "
                f"behind the newest model in these results — "
                + ", ".join(examples)
                + ". This compares model numbers within the same line; it is "
                  "not a check of whether a product is still in production.")

    return {"candidates": keep, "dropped": superseded, "note": note}
