"""
Tries live eBay search first (once EBAY_CLIENT_ID/SECRET are set).
Falls back to a small static catalog otherwise, or if the live call
fails — so the pipeline is never blocked by eBay being unavailable.

Every item — live or fallback — includes a real "url" so the frontend
can make each product genuinely clickable.
"""
from urllib.parse import quote
from app.config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET


def _amazon_search_url(name: str) -> str:
    # Fallback items don't have a single canonical product page, so we
    # link to a real, live Amazon India search for that exact product
    # name — clicking it takes you to real, current listings, not a dead link.
    return f"https://www.amazon.in/s?k={quote(name)}"


FALLBACK_CATALOG = [
    {"id": "p1", "name": "BoAt Rockerz 255", "category": "earbuds",
     "price_paise": 149900, "rating": 4.3, "delivery_days": 1, "stock": 12,
     "url": _amazon_search_url("BoAt Rockerz 255")},
    {"id": "p2", "name": "Noise Buds VS104", "category": "earbuds",
     "price_paise": 99900, "rating": 4.0, "delivery_days": 2, "stock": 5,
     "url": _amazon_search_url("Noise Buds VS104")},
    {"id": "p3", "name": "Sony WF-C700N", "category": "earbuds",
     "price_paise": 649900, "rating": 4.5, "delivery_days": 3, "stock": 8,
     "url": _amazon_search_url("Sony WF-C700N")},
    {"id": "p4", "name": "boAt Airdopes 141", "category": "earbuds",
     "price_paise": 129900, "rating": 3.9, "delivery_days": 1, "stock": 20,
     "url": _amazon_search_url("boAt Airdopes 141")},
    {"id": "p5", "name": "OnePlus Nord Buds 2", "category": "earbuds",
     "price_paise": 179900, "rating": 4.2, "delivery_days": 2, "stock": 15,
     "url": _amazon_search_url("OnePlus Nord Buds 2")},
]


def search_catalog(category: str, max_price_paise: int, sort: str = None,
                   requirements: list = None) -> list[dict]:
    """
    Every venue the agent can see, in one list.

    eBay is where the selection is; the UCP merchant is the one venue this
    agent can actually pay. Both are searched, both are returned in the same
    shape, and every downstream stage — trust, ranking, the risk gate,
    the mandate chain — treats them identically. The `source` field is the
    only thing that differs, and it exists so checkout knows who to talk to.

    A merchant that is unreachable costs the run a few options and nothing
    else; eBay being down likewise. The run only fails if neither answers.
    """
    listings = _search_ebay(category, max_price_paise, sort)
    for item in listings:
        item.setdefault("source", "ebay")

    # Resolve variation groups to the option actually requested. Done here,
    # before trust and ranking, so every stage downstream reasons about the
    # price that would really be charged rather than a group representative.
    try:
        from app.agent.ebay_client import resolve_variants
        listings = resolve_variants(listings, category, requirements)
        # A resolved price can land above the ceiling — the ten-pack that was
        # inside budget is not the same purchase as the single unit.
        if max_price_paise:
            listings = [i for i in listings
                        if (i.get("price_paise") or 0) <= max_price_paise]
    except Exception as exc:
        print(f"[catalog] variant resolution skipped: {exc}", flush=True)

    # Searched second and merged rather than replacing anything: the store is
    # six products, and letting it crowd out a real marketplace would be
    # dressing up a demo as a selection.
    try:
        from app.agent import merchant_client
        listings += merchant_client.search(category, max_price_paise)
    except Exception as exc:
        print(f"[catalog] UCP merchant search skipped: {exc}", flush=True)

    return listings


def _search_ebay(category: str, max_price_paise: int, sort: str = None) -> list[dict]:
    if EBAY_CLIENT_ID and EBAY_CLIENT_SECRET:
        try:
            from app.agent.ebay_client import search_live_catalog
            results = search_live_catalog(query=category, max_price_paise=max_price_paise, sort=sort)
            results = [r for r in results if r["price_paise"] > 0]
            if results:
                return results
        except Exception as e:
            print(f"[catalog] eBay search failed, falling back to static catalog: {e}", flush=True)

    # Fallback only covers earbuds. Matching loosely so "wireless earbuds"
    # or "earbud" still hit it, but anything else honestly returns nothing
    # rather than showing unrelated products.
    if "earbud" not in category.lower() and "earphone" not in category.lower():
        return []

    return [p for p in FALLBACK_CATALOG if p["price_paise"] <= max_price_paise]