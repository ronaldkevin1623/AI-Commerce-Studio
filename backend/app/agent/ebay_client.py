"""
Real, live product search via eBay's Browse API.
Uses OAuth2 client-credentials flow (the standard "app-level" auth
eBay requires for public search). Token is cached in memory and
refreshed automatically when it expires.

NOTE ON MARKETPLACE: eBay's Browse API returned a 409 Conflict
(error 12019) when targeting EBAY_IN — India isn't in the Browse
API's supported marketplace list. EBAY_US is used instead, which
means real listings come priced in USD. Since Razorpay checkout in
this project runs in INR, prices are converted using an approximate
fixed rate below — this is a simplification, not a live exchange
rate lookup, and is disclosed as such rather than presented as exact.
"""
import time
import base64
import httpx
from app.config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET

_token_cache = {"access_token": None, "expires_at": 0}

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

# Approximate, hardcoded — not a live forex rate. Good enough for
# demo-scale budget filtering, not for real financial accuracy.
APPROX_USD_TO_INR = 83


def _get_access_token() -> str:
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    credentials = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()

    response = httpx.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data["expires_in"] - 60
    return _token_cache["access_token"]


def search_live_catalog(query: str, max_price_paise: int, limit: int = 10) -> list[dict]:
    """
    Searches real, live eBay listings and normalizes them into the same
    shape your risk gate / agent pipeline already expects:
    id, name, category, price_paise, rating, delivery_days, stock, url
    """
    token = _get_access_token()
    max_price_inr = max_price_paise / 100
    max_price_usd = round(max_price_inr / APPROX_USD_TO_INR, 2)

    response = httpx.get(
        SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        },
        params={
            "q": query,
            "filter": f"price:[..{max_price_usd}],priceCurrency:USD",
            "limit": limit,
        },
        timeout=10,
    )
    response.raise_for_status()
    items = response.json().get("itemSummaries", [])

    results = []
    for item in items:
        price = item.get("price", {})
        price_usd = float(price.get("value", 0))
        price_inr_paise = int(price_usd * APPROX_USD_TO_INR * 100)

        seller = item.get("seller", {})
        feedback_pct = seller.get("feedbackPercentage")
        rating = round(float(feedback_pct) / 20, 1) if feedback_pct else 4.0

        image = item.get("image", {}).get("imageUrl")

        marketing_price = item.get("marketingPrice", {})
        original_price_usd_raw = marketing_price.get("originalPrice", {}).get("value")
        discount_pct_raw = marketing_price.get("discountPercentage")

        original_price_paise = (
            int(float(original_price_usd_raw) * APPROX_USD_TO_INR * 100)
            if original_price_usd_raw else None
        )
        discount_percent = int(discount_pct_raw) if discount_pct_raw else None

        results.append({
            "id": item.get("itemId"),
            "name": item.get("title"),
            "category": query,
            "price_paise": price_inr_paise,
            "original_price_paise": original_price_paise,
            "discount_percent": discount_percent,
            "rating": rating,
            "delivery_days": 3,
            "stock": 1,
            "url": item.get("itemWebUrl"),
            "image": image,
            "condition": item.get("condition"),
            # Flag so the frontend/pitch can honestly disclose this is a
            # converted price, not a native INR listing
            "price_is_converted": True,
        })

    return results