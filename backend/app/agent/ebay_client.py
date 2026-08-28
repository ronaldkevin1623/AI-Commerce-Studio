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
import re
import time
import base64
from datetime import datetime, timezone

import httpx
from concurrent.futures import ThreadPoolExecutor
from app.config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET
from app.agent import settings

_token_cache = {"access_token": None, "expires_at": 0}

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


def _parse_ebay_date(value: str | None):
    """eBay returns ISO-8601 with a trailing Z; fromisoformat wants +00:00."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _shipping(item: dict, usd_to_inr: int) -> dict:
    """
    Real shipping data off the listing: what postage costs, and the window
    the seller estimates for delivery.

    delivery_days used to be hardcoded to 3 for every listing, which quietly
    made "rank by fastest delivery" meaningless — every candidate scored the
    same. eBay does return a real per-listing estimate, so this reads it.
    """
    options = item.get("shippingOptions") or []
    option = options[0] if options else {}

    cost = option.get("shippingCost") or {}
    cost_usd = float(cost.get("value") or 0)

    earliest = _parse_ebay_date(option.get("minEstimatedDeliveryDate"))
    latest = _parse_ebay_date(option.get("maxEstimatedDeliveryDate"))

    days = None
    if earliest:
        days = max((earliest - datetime.now(timezone.utc)).days, 0)

    return {
        "shipping_cost_paise": int(cost_usd * usd_to_inr * 100),
        "shipping_is_free": cost_usd == 0 and bool(options),
        "delivery_estimate_from": earliest.isoformat() if earliest else None,
        "delivery_estimate_to": latest.isoformat() if latest else None,
        # Falls back to None rather than a made-up number — an absent
        # estimate should read as "unknown", not as "three days".
        "delivery_days": days,
    }


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


ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/"


def _percent(value) -> int | None:
    """
    eBay is inconsistent about this field: item_summary/search returns
    discountPercentage as "60", the single-item endpoint returns "60.0".
    int("60.0") raises, so go through float.
    """
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def get_item(item_id: str, category: str = "") -> dict | None:
    """
    Fetch one listing by its eBay item id, normalised like search results.

    Re-running a search to find a previously seen listing is unreliable —
    live results reorder between calls and an item can drop out entirely.
    More importantly, this is the authoritative price: an external agent
    proposing a purchase names only an id, and the amount is read from eBay
    here rather than taken on the caller's word.
    """
    from urllib.parse import quote

    usd_to_inr = settings.get("ebay", "usd_to_inr")
    token = _get_access_token()

    response = httpx.get(
        f"{ITEM_URL}{quote(item_id, safe='')}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        },
        timeout=15,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    item = response.json()

    price_usd = float((item.get("price") or {}).get("value") or 0)
    if not price_usd:
        return None

    seller = item.get("seller") or {}
    feedback = seller.get("feedbackPercentage")
    marketing = item.get("marketingPrice") or {}
    original_raw = (marketing.get("originalPrice") or {}).get("value")
    discount_raw = marketing.get("discountPercentage")

    return {
        "id": item.get("itemId"),
        "name": item.get("title"),
        "category": category,
        # Present when eBay says this listing is a group of variants. The
        # price above is one representative of that group, not necessarily
        # the one being asked for.
        "item_group_id": (
            (item.get("itemGroupHref") or "").split("item_group_id=")[-1]
            if item.get("itemGroupType") == "SELLER_DEFINED_VARIATIONS" else None
        ),
        "price_paise": int(price_usd * usd_to_inr * 100),
        "original_price_paise": (
            int(float(original_raw) * usd_to_inr * 100) if original_raw else None
        ),
        "discount_percent": _percent(discount_raw),
        "rating": round(float(feedback) / 20, 1) if feedback else 4.0,
        "seller_feedback": float(feedback) if feedback else None,
        **_shipping(item, usd_to_inr),
        "stock": item.get("estimatedAvailabilities", [{}])[0].get("estimatedAvailableQuantity", 1)
        if item.get("estimatedAvailabilities") else 1,
        "url": item.get("itemWebUrl"),
        "image": (item.get("image") or {}).get("imageUrl"),
        # The gallery strip and the description come only from this endpoint —
        # item_summary/search returns a single image and no prose, which is
        # why the product drawer fetches full detail on open rather than
        # reusing the search payload.
        "images": [
            img["imageUrl"]
            for img in ([item.get("image")] + (item.get("additionalImages") or []))
            if img and img.get("imageUrl")
        ],
        "description": item.get("shortDescription"),
        "brand": (item.get("brand") or (item.get("seller") or {}).get("username")),
        "seller_username": (item.get("seller") or {}).get("username"),
        "item_location": (item.get("itemLocation") or {}).get("country"),
        "condition": item.get("condition"),
        "price_is_converted": True,
    }


def search_live_catalog(query: str, max_price_paise: int, limit: int = None,
                        sort: str = None) -> list[dict]:
    """
    Searches real, live eBay listings and normalizes them into the same
    shape your risk gate / agent pipeline already expects:
    id, name, category, price_paise, rating, delivery_days, stock, url

    `limit` and the USD→INR rate are tunable from the Scout and eBay nodes
    on the hive canvas. The rate is a financial control — it decides what
    a USD listing actually costs in rupees — so changing it is audited.
    """
    usd_to_inr = settings.get("ebay", "usd_to_inr")
    if limit is None:
        limit = settings.get("scout", "result_limit")

    token = _get_access_token()
    max_price_inr = max_price_paise / 100
    max_price_usd = round(max_price_inr / usd_to_inr, 2)

    response = httpx.get(
        SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        },
        params={
            "q": query,
            # conditionIds excludes 7000 ("For parts or not working") at the
            # API, so broken handsets never enter the pool at all — cheaper
            # and more reliable than filtering them out downstream. The ids
            # kept are New, New other, New with defects, Certified/Seller
            # refurbished, and the Used grades.
            "filter": (
                f"price:[..{max_price_usd}],priceCurrency:USD,"
                "conditionIds:{1000|1500|1750|2000|2010|2020|2030|2500|3000|4000|5000|6000}"
            ),
            "limit": limit,
            # eBay's default Best Match optimises for cheap and popular,
            # which is the opposite of what "the best X under N" means: a
            # search for a good camera phone under Rs20,000 came back full of
            # Rs3,000 handsets from 2016. Sorting price-descending inside the
            # same ceiling surfaces the most capable thing the budget buys.
            **({"sort": sort} if sort else {}),
        },
        timeout=10,
    )
    response.raise_for_status()
    items = response.json().get("itemSummaries", [])

    results = []
    for item in items:
        price = item.get("price", {})
        price_usd = float(price.get("value", 0))
        price_inr_paise = int(price_usd * usd_to_inr * 100)

        seller = item.get("seller", {})
        feedback_pct = seller.get("feedbackPercentage")
        rating = round(float(feedback_pct) / 20, 1) if feedback_pct else 4.0
        # Kept raw as well — the trust agent thresholds on the real
        # percentage rather than the 0-5 display value.
        seller_feedback = float(feedback_pct) if feedback_pct else None

        image = item.get("image", {}).get("imageUrl")

        marketing_price = item.get("marketingPrice", {})
        original_price_usd_raw = marketing_price.get("originalPrice", {}).get("value")
        discount_pct_raw = marketing_price.get("discountPercentage")

        original_price_paise = (
            int(float(original_price_usd_raw) * usd_to_inr * 100)
            if original_price_usd_raw else None
        )
        discount_percent = _percent(discount_pct_raw)

        shipping = _shipping(item, usd_to_inr)

        results.append({
            "id": item.get("itemId"),
            "name": item.get("title"),
            "category": query,
            # A variation group's search price is one representative of the
            # set, not the option being asked for. Carried through so the
            # resolver can replace it with the real one.
            "item_group_id": (
                (item.get("itemGroupHref") or "").split("item_group_id=")[-1]
                if item.get("itemGroupType") == "SELLER_DEFINED_VARIATIONS" else None
            ),
            "price_paise": price_inr_paise,
            "original_price_paise": original_price_paise,
            "discount_percent": discount_percent,
            "rating": rating,
            **shipping,
            "stock": 1,
            "url": item.get("itemWebUrl"),
            "image": image,
            "condition": item.get("condition"),
            "seller_feedback": seller_feedback,
            # Flag so the frontend/pitch can honestly disclose this is a
            # converted price, not a native INR listing
            "price_is_converted": True,
        })

    return results


# ── Multi-variant listings ───────────────────────────────────────────────

GROUP_URL = "https://api.ebay.com/buy/browse/v1/item/get_items_by_item_group"

# Aspects that change what you are actually buying, in the order they matter.
_SIZE_ASPECTS = ("Storage Capacity", "Capacity", "Size", "Total Capacity")
_PACK_ASPECTS = ("Pack of", "Number in Pack", "Bundle Listing", "Units per Pack")


def _norm_spec(text: str) -> str:
    """'128 GB' and '128gb' are the same spec written two ways."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _wanted_specs(*texts) -> set:
    """Spec tokens the person used — 128gb, 1tb, 512mb."""
    found = set()
    for text in texts:
        for match in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(gb|tb|mb|kb)\b",
                                 (text or "").lower()):
            found.add(f"{match.group(1)}{match.group(2)}")
    return found


# group_id -> (fetched_at, variants). A listing's set of options is stable
# over the life of a search session; its prices are re-read from the search
# response every time regardless.
_VARIANT_CACHE = {}
_VARIANT_TTL_SECONDS = 600


def fetch_variants(group_id: str, token: str) -> list[dict]:
    """Every variant in a group, with its own price and aspects."""
    cached = _VARIANT_CACHE.get(group_id)
    if cached and (time.time() - cached[0]) < _VARIANT_TTL_SECONDS:
        return cached[1]

    try:
        response = httpx.get(
            GROUP_URL,
            headers={"Authorization": f"Bearer {token}",
                     "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
            params={"item_group_id": group_id},
            timeout=15.0,
        )
        response.raise_for_status()
        variants = response.json().get("items", []) or []
        _VARIANT_CACHE[group_id] = (time.time(), variants)
        return variants
    except Exception as exc:
        # Not cached: a failure now should be retried, not remembered.
        print(f"[ebay] variant group {group_id} unavailable: {exc}", flush=True)
        return []


def _varying_aspects(variants: list[dict]) -> list[str]:
    """
    Aspect names whose value differs across the group.

    These are the dimensions the listing actually varies along. Anything
    identical on every variant describes the listing as a whole and cannot
    tell one option from another.
    """
    seen = {}
    for variant in variants:
        for aspect in variant.get("localizedAspects") or []:
            seen.setdefault(aspect.get("name"), set()).add(aspect.get("value"))
    return [name for name, values in seen.items() if name and len(values) > 1]


def _aspect_matches(value: str, wanted: set) -> bool:
    """True when an aspect value names one of the specs asked for."""
    if not wanted:
        return True
    parts = re.split(r"[,/|]+", value or "")
    return any(_norm_spec(part) in wanted for part in parts)


def _pick_variant(variants: list[dict], wanted: set) -> dict | None:
    """
    The variant the request describes, at its own price.

    Preference order: the spec asked for, then the smallest pack, then the
    cheapest. Nobody asking for "a 128gb pendrive" means a box of ten, and
    quantity is a question the agent asks separately — so a multipack here
    would be answering it on their behalf, with the wrong number.
    """
    varying = _varying_aspects(variants)
    scored = []

    for variant in variants:
        aspects = {a.get("name"): a.get("value")
                   for a in (variant.get("localizedAspects") or [])}

        # Only aspects that actually vary can identify this option; a value
        # repeated across the whole group is listing copy, not a choice.
        size = ""
        for name in varying:
            value = aspects.get(name, "")
            if value and _aspect_matches(value, wanted) and wanted:
                size = value
                break
        if not size:
            size = next((aspects[n] for n in varying if aspects.get(n)), "")

        pack_raw = next((aspects[k] for k in _PACK_ASPECTS if k in aspects), "1")
        try:
            pack = int(re.sub(r"[^0-9]", "", str(pack_raw)) or 1)
        except ValueError:
            pack = 1

        try:
            price = float((variant.get("price") or {}).get("value") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue

        matches = (not wanted) or any(
            _aspect_matches(aspects.get(name, ""), wanted) for name in varying
        )
        scored.append({
            "matches": matches, "pack": pack, "price_usd": price,
            "size": size, "item_id": variant.get("itemId"),
            "title": variant.get("title"),
        })

    if not scored:
        return None

    # A spec was asked for and nothing carries it — the listing does not
    # stock what was requested, so report that rather than substituting.
    if wanted and not any(s["matches"] for s in scored):
        return None

    candidates = [s for s in scored if s["matches"]] or scored
    candidates.sort(key=lambda s: (s["pack"], s["price_usd"]))
    return candidates[0]


def resolve_variants(items: list[dict], query: str = "", requirements=None,
                     max_lookups: int = 40) -> list[dict]:
    """
    Replace group-level prices with the price of the variant requested.

    Only listings eBay actually flags as variation groups are touched. The
    cap exists to bound a pathological result set, not to trim ordinary ones:
    most of a marketplace page turns out to be variation groups — 18 of 21 in
    the search that prompted this — and skipping any of them leaves a price
    on screen for an option nobody asked for. The lookups run concurrently,
    so covering the whole set costs about a second.
    """
    wanted = _wanted_specs(query, " ".join(requirements or []))
    usd_to_inr = settings.get("ebay", "usd_to_inr")

    groups = [i for i in items if i.get("item_group_id")][:max_lookups]
    if not groups:
        return items

    token = _get_access_token()

    def work(item):
        variants = fetch_variants(item["item_group_id"], token)
        return item, _pick_variant(variants, wanted), len(variants)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for item, pick, count in pool.map(work, groups):
            if count <= 1:
                continue
            if pick is None:
                # Flagged, not dropped: the price shown covers a range and we
                # could not tie it to the request.
                item["variant_note"] = (
                    f"One of {count} variants — the listed price may not be "
                    "for the option you asked for."
                )
                continue

            resolved_paise = int(pick["price_usd"] * usd_to_inr * 100)
            if resolved_paise != item.get("price_paise"):
                item["price_before_variant_paise"] = item.get("price_paise")
            item["price_paise"] = resolved_paise
            item["variant_size"] = pick["size"]
            item["variant_pack"] = pick["pack"]
            item["variant_note"] = (
                f"{pick['size']}".strip() + (f", pack of {pick['pack']}" if pick["pack"] > 1 else "")
                + f" — priced from {count} variants in this listing"
            ).lstrip(", ")

    return items
