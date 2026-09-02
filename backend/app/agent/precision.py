"""
THE HARD FILTER, BEFORE ANYTHING GETS TO CHOOSE.

The reference slide's example is a handheld vacuum: a GenAI-only system
recommends one that is out of stock, discontinued, and returned by 80% of
buyers, while a hybrid system returns one that is in stock, well approved
and frequently purchased. The difference is not a better prompt. It is a
stage that removes the unbuyable candidates before anything is asked to
choose between them.

That is what this is, and where it sits is the whole point: it runs on the
candidate list, and only what survives reaches the ranker or the model. A
prompt saying "do not recommend out-of-stock items" is a request. This is
not a request.

WHAT IS REAL HERE, AND WHAT IS NOT

  In stock          real. eBay's estimatedAvailabilities carries
                    estimatedAvailabilityStatus per delivery option.
  Frequently bought real. The same block carries estimatedSoldQuantity.
  Returns accepted  real. returnTerms.returnsAccepted, and the period.
  Approval rating   real. primaryProductReviewRating, already fetched.

  Return RATE       NOT AVAILABLE. eBay's Browse API does not expose how
                    many buyers returned an item, and there is no adjacent
                    field that stands in for it. The slide's "returned by
                    80% of buyers" cannot be reproduced here, so it is not
                    claimed, not estimated, and not quietly substituted
                    with something that looks similar. What can be said is
                    whether the seller accepts returns at all — which is a
                    statement about the seller's confidence, not about
                    other buyers' regret, and is labelled as such.

  Discontinued      NOT AVAILABLE as a field. The nearest real signal is
                    the generation filter, which drops a phone two model
                    numbers behind one that is on sale beside it; that
                    already runs earlier in the pipeline and is not
                    re-litigated here.

These signals only exist on eBay's item detail endpoint, not on search
results, so `screen` works on the enriched shortlist. Anything unenriched
has `availability` of None, and unknown is not treated as failure — a
listing nobody looked up is not evidence of a listing that is sold out.
"""

# eBay's availability vocabulary. OUT_OF_STOCK is the only one that means
# "cannot be bought"; LIMITED_STOCK is a reason to hurry, not to refuse.
BUYABLE = {"IN_STOCK", "LIMITED_STOCK"}
UNBUYABLE = {"OUT_OF_STOCK", "SOLD_OUT"}

# Enough buyers to make "frequently purchased" mean something. Below it the
# figure is reported but not leaned on.
POPULAR_SOLD = 10


def signals(item: dict) -> dict:
    """
    What is known about whether this can be bought and whether it is good.

    Separated from the filtering so the same reading can be shown to a
    person, stored on an order, and used to decide — three jobs that must
    not be allowed to disagree about the facts.
    """
    availability = item.get("availability")
    sold = item.get("sold_quantity")
    stars = item.get("review_stars")
    reviews = item.get("review_count") or 0

    return {
        "availability": availability,
        "in_stock": (availability in BUYABLE) if availability else None,
        "sold_quantity": sold,
        "frequently_bought": (sold or 0) >= POPULAR_SOLD if sold is not None else None,
        "returns_accepted": item.get("returns_accepted"),
        "return_days": item.get("return_days"),
        "approval_stars": stars,
        "approval_reviews": reviews,
        # Named so nobody reads the absence as a low rate.
        "return_rate": None,
        "return_rate_note": "eBay does not publish per-item return rates.",
    }


def screen(items: list[dict]) -> dict:
    """
    Remove what cannot be bought. Keep the rest, with its signals attached.

    Only one rule drops a listing, and it is the one the data supports
    without inference: eBay says it is out of stock. Everything else here
    is a preference, and preferences belong to the ranker — a filter that
    quietly enforced "must have reviews" would empty a page of perfectly
    buyable listings that nobody has reviewed yet.
    """
    kept, dropped = [], []
    for item in items or []:
        found = signals(item)
        item["precision"] = found

        if found["availability"] in UNBUYABLE:
            item["precision"]["dropped_because"] = (
                f"eBay reports this as {found['availability'].lower().replace('_', ' ')}.")
            dropped.append(item)
            continue
        kept.append(item)

    if not kept and dropped:
        # The stand-down every screen in this project has: if the rule
        # would empty the page, the page stands and the fact is reported.
        # A shopper with nothing on screen cannot tell a strict filter from
        # a broken search.
        return {"candidates": items, "dropped": 0, "stood_down": True,
                "summary": (f"All {len(dropped)} listings came back out of "
                            f"stock — showing them anyway rather than an "
                            f"empty page, because that is a fact about the "
                            f"market rather than a reason to say nothing.")}

    return {
        "candidates": kept,
        "dropped": len(dropped),
        "stood_down": False,
        "summary": (f"{len(kept)} of {len(items)} listings can actually be "
                    f"bought"
                    + (f" — set aside {len(dropped)} eBay reports out of stock"
                       if dropped else "")),
    }


def preference_key(item: dict):
    """
    The slide's tie-break, as a sort key: in stock, well approved, most
    purchased — applied after quality, never instead of it.

    Returns a tuple sorted ascending, so every element is negated to put
    "more" first. Unknowns sort last without being punished as zero: a
    listing nobody has looked up should not lose to one measured badly.
    """
    found = item.get("precision") or signals(item)
    return (
        0 if found["in_stock"] is not False else 1,
        -(found["approval_stars"] or 0),
        -(found["sold_quantity"] or 0),
        0 if found["returns_accepted"] else 1,
    )


def explain(item: dict) -> str:
    """One line naming the evidence, for the order record and the screen."""
    found = item.get("precision") or signals(item)
    parts = []
    if found["availability"]:
        parts.append(found["availability"].lower().replace("_", " "))
    if found["sold_quantity"] is not None:
        parts.append(f"{int(found['sold_quantity']):,} sold")
    if found["approval_stars"]:
        parts.append(f"{found['approval_stars']}★ from "
                     f"{int(found['approval_reviews'] or 0):,} reviews")
    if found["returns_accepted"]:
        parts.append(f"returns accepted"
                     + (f" for {int(found['return_days'])} days"
                        if found["return_days"] else ""))
    elif found["returns_accepted"] is False:
        parts.append("no returns")
    return "; ".join(parts) if parts else "no precision signals were available"
