"""
WHICH PLACES THE AGENT CAN ACTUALLY SHOP, AND WHICH OF THEM CAN BE PAID.

Exposed because both halves of that sentence are limitations, and this
project's rule is that limitations appear on screen rather than in a
README. eBay carries almost all the selection and can be searched, priced
and reasoned about — but no seller there will ship against this account, so
`can_fulfil` is false and the UI says so. The UCP store is the one venue
where an order becomes a real delivery.

The list is whatever is registered, not a fixed pair, so a channel added
later shows up here without this file changing.
"""
from fastapi import APIRouter

from app.adapters import registry

router = APIRouter(prefix="/venues", tags=["venues"])

# What each kind of entry point is, in the words a shopper would use. The
# adapter declares its kind; the sentence lives here because it is UI copy.
KIND_COPY = {
    "marketplace": "Many sellers under one roof",
    "retailer": "A shop selling its own stock",
    "retail_media": "Sponsored placements inside a shop",
    "social": "Shoppable posts",
    "in_store": "Stock on a shelf near you",
    "genai_platform": "Another assistant's catalogue",
}


@router.get("")
def list_venues():
    """Every registered venue, whether it answered, and whether it can ship."""
    venues = registry.describe()
    for v in venues:
        v["kind_label"] = KIND_COPY.get(v["kind"], v["kind"])
        v["note"] = ("Searchable and payable, and orders here are really "
                     "fulfilled." if v["can_fulfil"] else
                     "Searchable and payable, but no seller here will ship "
                     "to this account — listings are real, fulfilment is not.")
    return {
        "venues": venues,
        "searchable": sum(1 for v in venues if v["available"]),
        "fulfillable": sum(1 for v in venues if v["can_fulfil"] and v["available"]),
        # Named so the UI can state the gap plainly instead of implying that
        # everything on screen is buyable end to end.
        "kinds_supported": sorted(KIND_COPY),
        "kinds_built": sorted({v["kind"] for v in venues}),
    }


@router.get("/last-search")
def last_search():
    """
    What each venue returned on the most recent search.

    Empty until a search has run in this process — reported as such rather
    than as zeroes, because "no venue answered" and "nobody has asked yet"
    are different facts.
    """
    from app.agent.catalog import search_catalog
    reported = getattr(search_catalog, "last_venues", None)
    if reported is None:
        return {"ran": False, "venues": []}
    return {"ran": True, "venues": reported}
