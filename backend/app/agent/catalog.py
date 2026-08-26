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


def search_catalog(category: str, max_price_paise: int) -> list[dict]:
    if EBAY_CLIENT_ID and EBAY_CLIENT_SECRET:
        try:
            from app.agent.ebay_client import search_live_catalog
            results = search_live_catalog(query=category, max_price_paise=max_price_paise)
            results = [r for r in results if r["price_paise"] > 0]
            if results:
                return results
        except Exception as e:
            print(f"[catalog] eBay search failed, falling back to static catalog: {e}")

    return [
        p for p in FALLBACK_CATALOG
        if p["category"] == category and p["price_paise"] <= max_price_paise
    ]