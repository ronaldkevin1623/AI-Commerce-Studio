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
        # Genuine product reviews, when this listing is matched to an eBay
        # catalogue product. Filled by enrich_reviews() for the shortlist;
        # None here means "not looked up yet or none exist", never "bad".
        "review_stars": None,
        "review_count": None,
        # Deliberately not a star score. A per-seller reputation cannot be
        # converted into a per-product rating, and pretending otherwise put
        # an invented 4.0 on every listing that had no feedback at all.
        "rating": None,
        "seller_feedback": float(feedback) if feedback else None,
        # How much that percentage is worth: 100% across 72 sales is a
        # weaker claim than 99.8% across 400,000.
        "seller_feedback_count": seller.get("feedbackScore"),
        # eBay's own badge, awarded against their service criteria.
        "top_rated_seller": bool(item.get("topRatedBuyingExperience")),
        "condition_id": item.get("conditionId"),
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


# Everything except 7000, "For parts or not working" — never something an
# agent should buy on someone's behalf. Used when no preference is given to
# a call that has no opinion; the shopper-facing default is new only, and it
# lives in ollama_agent.condition_preference.
_ALL_SELLABLE_CONDITIONS = {"1000", "1500", "1750", "2000", "2010", "2020",
                            "2030", "2500", "3000", "4000", "5000", "6000"}


def _normalise_summary(item: dict, usd_to_inr: int, category: str) -> dict:
    """
    One eBay item summary, in the shape the rest of the pipeline expects.

    Lifted out of search_live_catalog so image-search results are identical
    in shape to typed-search results. A second copy of this mapping would
    drift, and the trust, quality and ranking stages all read these keys —
    an image result that quietly lacked seller_feedback would be scored as
    an unrated seller rather than as a field nobody filled in.
    """
    price_usd = float((item.get("price") or {}).get("value", 0))

    seller = item.get("seller") or {}
    feedback_pct = seller.get("feedbackPercentage")
    # No star score is derived here. A seller's reputation percentage is not
    # a product rating, and the old conversion also handed 4.0 to every
    # listing that had no feedback at all.
    seller_feedback = float(feedback_pct) if feedback_pct else None

    marketing_price = item.get("marketingPrice") or {}
    original_price_usd_raw = (marketing_price.get("originalPrice") or {}).get("value")
    original_price_paise = (
        int(float(original_price_usd_raw) * usd_to_inr * 100)
        if original_price_usd_raw else None
    )

    return {
        "id": item.get("itemId"),
        "name": item.get("title"),
        "category": category,
        # A variation group's search price is one representative of the set,
        # not the option being asked for. Carried through so the resolver
        # can replace it with the real one.
        "item_group_id": (
            (item.get("itemGroupHref") or "").split("item_group_id=")[-1]
            if item.get("itemGroupType") == "SELLER_DEFINED_VARIATIONS" else None
        ),
        "price_paise": int(price_usd * usd_to_inr * 100),
        "original_price_paise": original_price_paise,
        "discount_percent": _percent(marketing_price.get("discountPercentage")),
        "rating": None,
        "review_stars": None,
        "review_count": None,
        **_shipping(item, usd_to_inr),
        "stock": 1,
        "url": item.get("itemWebUrl"),
        "image": (item.get("image") or {}).get("imageUrl"),
        "condition": item.get("condition"),
        "seller_feedback": seller_feedback,
        "seller_feedback_count": seller.get("feedbackScore"),
        "top_rated_seller": bool(item.get("topRatedBuyingExperience")),
        "condition_id": item.get("conditionId"),
        # Where the thing physically is. eBay returns it on every search
        # result and it was being dropped here — it decides whether a
        # purchase crosses a border, which decides customs, duties and how
        # far a return has to travel.
        "item_location": (item.get("itemLocation") or {}).get("country"),
        # Flag so the interface can honestly disclose this is a converted
        # price, not a native INR listing.
        "price_is_converted": True,
    }


class RateLimited(Exception):
    """
    eBay refused the call because too many have been made, not because the
    search was wrong.

    It has its own type because the two failures need different sentences.
    A search that genuinely found nothing should be told "check the spelling
    or widen it"; a search that was never run should not, and for an hour
    this project told people to re-check spellings while the API was
    answering 429 to everything. Advice that cannot possibly help is worse
    than no advice, because it sends somebody off to fix their own query.
    """


# ── The search cache ─────────────────────────────────────────────────────
#
# eBay's Browse API has a daily call ceiling, and this project burns through
# it: every suite run is dozens of searches, and a demo re-running the same
# query is dozens more. Nothing here was cached, so an afternoon of testing
# exhausted the quota and the agent's whole discovery capability went with
# it.
#
# Short TTL on purpose. This is quota protection and a cushion against a
# burst, not a store: five minutes is long enough to cover a repeated demo
# query and a retry, and short enough that a price on screen is one eBay
# was serving a moment ago. Prices and stock are the two things that must
# not go stale, which is why this is not an hour.
_SEARCH_CACHE: dict = {}
_SEARCH_TTL_SECONDS = 300
_SEARCH_CACHE_MAX = 128

# Retry only helps a burst limit, never an exhausted daily quota, so it is
# deliberately short: two quick attempts and then an honest failure. Sitting
# in a long backoff would leave somebody watching a spinner while the answer
# ("the quota is gone until it resets") was already known.
_RETRY_DELAYS = (0.5, 1.5)

# ── The breaker ──────────────────────────────────────────────────────────
#
# The retry above is right for a burst and wrong for an exhausted daily
# quota, and the second is the case this project actually hits. With the
# quota gone, every search paid three HTTP calls and two seconds of sleep to
# be told the same thing, so the console sat for four seconds before saying
# "eBay is rate limiting this key" — an answer that was already known after
# the first call.
#
# It also made the parallelism the adapter registry exists for unmeasurable:
# two 0.6-second venues took 3.2 seconds together, because one of them was
# asleep in a backoff.
#
# So a 429 opens a breaker for a minute. Inside that window the call is
# refused locally, instantly, and no further quota is spent finding out what
# is already known. A minute is short enough that a burst limit clearing is
# noticed almost at once, and long enough that a demo does not spend its
# time re-asking an API that is saying no.
_BREAKER_SECONDS = 60
_rate_limited_until = 0.0


def rate_limited_now() -> bool:
    """Whether the breaker is open, without making a call to find out."""
    return time.time() < _rate_limited_until


def _open_breaker() -> None:
    global _rate_limited_until
    _rate_limited_until = time.time() + _BREAKER_SECONDS


def _cache_key(query, max_price_paise, limit, sort, condition_ids, usd_to_inr):
    # THE RATE IS PART OF THE KEY, BECAUSE IT IS PART OF THE ANSWER.
    #
    # eBay quotes USD and every price in the returned listings has already
    # been converted, so two searches at two different rates are two
    # different results for the same words. Leaving the rate out made the
    # cache serve the first conversion forever: the dial audit moved
    # usd_to_inr from 83 to 166 and got the same Rs580 back, which is a
    # tunable financial control silently doing nothing.
    return (str(query).strip().lower(), int(max_price_paise or 0),
            int(limit or 0), str(sort or ""),
            tuple(sorted(condition_ids or ())), int(usd_to_inr or 0))


def _cached(key):
    hit = _SEARCH_CACHE.get(key)
    if not hit:
        return None
    stored_at, results, aspects = hit
    if time.time() - stored_at > _SEARCH_TTL_SECONDS:
        _SEARCH_CACHE.pop(key, None)
        return None
    # The aspects ride along: they are read off the function afterwards, so
    # a cache hit that did not restore them would silently drop brand
    # standing for every repeated search.
    search_live_catalog.last_aspects = aspects
    return list(results)


def _remember_search(key, results, aspects):
    if len(_SEARCH_CACHE) >= _SEARCH_CACHE_MAX:
        oldest = min(_SEARCH_CACHE, key=lambda k: _SEARCH_CACHE[k][0])
        _SEARCH_CACHE.pop(oldest, None)
    _SEARCH_CACHE[key] = (time.time(), list(results), aspects)


def search_live_catalog(query: str, max_price_paise: int, limit: int = None,
                        sort: str = None, condition_ids: set = None) -> list[dict]:
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

    key = _cache_key(query, max_price_paise, limit, sort, condition_ids,
                     usd_to_inr)
    hit = _cached(key)
    # The cache is consulted BEFORE the breaker on purpose: a result served
    # from the last five minutes is still a real result, and refusing it
    # because the quota has since run out would throw away the one thing
    # that keeps working when eBay stops answering.
    if hit is None and rate_limited_now():
        raise RateLimited(
            "eBay is rate limiting this key and the last refusal was less "
            "than a minute ago, so no call was made. Its Browse API quota "
            "resets at midnight US/Pacific.")
    if hit is not None:
        print(f"[ebay] served {len(hit)} listing(s) for {query!r} from the "
              f"{_SEARCH_TTL_SECONDS // 60}-minute cache", flush=True)
        return hit

    token = _get_access_token()
    max_price_inr = max_price_paise / 100
    max_price_usd = round(max_price_inr / usd_to_inr, 2)

    response = _get_with_retry(
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
            # Asking eBay for only the conditions wanted, rather than
            # fetching everything and discarding most of it: a page of
            # twenty-five spent mostly on refurbished stock leaves a handful
            # of new listings to choose between.
            "filter": (
                f"price:[..{max_price_usd}],priceCurrency:USD,"
                "conditionIds:{" + "|".join(sorted(condition_ids or _ALL_SELLABLE_CONDITIONS)) + "}"
            ),
            "limit": limit,
            # The brand distribution for this result set, in the call that
            # was happening anyway. Brands are read from here rather than
            # guessed out of titles, where the recurring tokens turn out to
            # be feature words rather than makers.
            # MATCHING_ITEMS must be named explicitly: fieldgroups replaces
            # the default rather than adding to it, and asking for the
            # aspects alone returns the refinements with no listings.
            "fieldgroups": "MATCHING_ITEMS,ASPECT_REFINEMENTS",
            # eBay's default Best Match optimises for cheap and popular,
            # which is the opposite of what "the best X under N" means: a
            # search for a good camera phone under Rs20,000 came back full of
            # Rs3,000 handsets from 2016. Sorting price-descending inside the
            # same ceiling surfaces the most capable thing the budget buys.
            **({"sort": sort} if sort else {}),
        },
        timeout=10,
    )
    body = response.json()
    items = body.get("itemSummaries", [])

    results = [_normalise_summary(i, usd_to_inr, query) for i in items]

    # Handed to the brand module by the caller; kept on the function so the
    # return type stays a plain list of listings.
    aspects = (body.get("refinement") or {}).get("aspectDistributions") or []
    search_live_catalog.last_aspects = aspects

    _remember_search(key, results, aspects)
    return results


def _get_with_retry(url, **kwargs):
    """
    One eBay call, retried only for the failures a retry can fix.

    429 and 5xx are worth a second attempt; a 400 means the request was
    wrong and will be wrong again. A 429 that survives the retries is
    raised as `RateLimited` rather than as a generic HTTP error, so the
    caller can tell a person the truth about why there are no listings.
    """
    last = None
    for attempt in range(len(_RETRY_DELAYS) + 1):
        response = httpx.get(url, **kwargs)
        if response.status_code == 429 or response.status_code >= 500:
            last = response
            if attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt])
                continue
            if response.status_code == 429:
                _open_breaker()
                raise RateLimited(
                    "eBay is rate limiting this key. Its Browse API quota "
                    "resets at midnight US/Pacific.")
        response.raise_for_status()
        return response
    last.raise_for_status()
    return last


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


# ── Product reviews ──────────────────────────────────────────────────────
# Reviews and return terms are only on the single-item endpoint, so they
# cost one call per listing. Cached by item id for the life of the process;
# listings do not gain reviews mid-run.
_REVIEW_CACHE: dict[str, dict] = {}


# Bumped whenever the set of fields pulled from the item endpoint changes,
# so a cache filled by the previous shape is not read as the current one.
_ENRICH_SCHEMA = 2


def enrich_reviews(items: list[dict], limit: int = 8) -> list[dict]:
    """
    Add real star ratings and return terms to the first `limit` listings.

    Only the shortlist is enriched — the ones that could plausibly be
    recommended. Anything beyond the limit keeps review_stars None, and the
    quality model treats that as unknown rather than assuming the worst.
    """
    token = _get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }

    for item in items[:limit]:
        if item.get("source") != "ebay":
            continue
        item_id = str(item.get("id") or "")
        if not item_id:
            continue

        # Keyed by what is being extracted, not just the item. Adding the
        # availability fields to this function left every already-cached
        # listing returning the old three keys forever — the new signals
        # read as missing on exactly the items the cache had helped with.
        cache_key = (item_id, _ENRICH_SCHEMA)
        if cache_key in _REVIEW_CACHE:
            item.update(_REVIEW_CACHE[cache_key])
            continue

        try:
            response = httpx.get(f"{ITEM_URL}{item_id}",
                                 headers=headers, timeout=8)
            if response.status_code != 200:
                continue
            body = response.json()
        except Exception as exc:
            # One listing failing to enrich must not cost the run its
            # results; it simply stays unrated.
            print(f"[ebay] review lookup skipped for {item_id}: {exc}", flush=True)
            continue

        rating = body.get("primaryProductReviewRating") or {}
        terms = body.get("returnTerms") or {}
        # eBay reports availability per delivery option; the ship-to-home
        # one is the only one that matters to a buyer in India.
        availability = next(
            (a for a in (body.get("estimatedAvailabilities") or [])
             if "SHIP_TO_HOME" in (a.get("deliveryOptions") or [])),
            (body.get("estimatedAvailabilities") or [{}])[0])

        found = {
            "review_stars": _num_or_none(rating.get("averageRating")),
            "review_count": _num_or_none(rating.get("reviewCount")),
            "returns_accepted": bool(terms.get("returnsAccepted")),
            "return_days": _num_or_none(
                (terms.get("returnPeriod") or {}).get("value")),
            # Was being fetched and thrown away. These three are the
            # precision signals the hard filter runs on: whether the thing
            # can actually be bought, how many people have bought it, and
            # how many the seller says are left.
            "availability": availability.get("estimatedAvailabilityStatus"),
            "sold_quantity": _num_or_none(availability.get("estimatedSoldQuantity")),
            "stock_estimate": _num_or_none(availability.get("availabilityThreshold")),
        }
        _REVIEW_CACHE[cache_key] = found
        item.update(found)

    return items


def _num_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── Image search ─────────────────────────────────────────────────────────

IMAGE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search_by_image"


def search_by_image(image_b64: str, max_price_paise: int = 0,
                    limit: int = None) -> list[dict]:
    """
    Find listings that look like a photograph.

    eBay performs the visual match against its own catalogue. That is the
    entire reason this is done here rather than by describing the picture
    with a vision model and searching for the description: a model that
    reads "Galaxy S22" off a picture of an S23 produces a search that is
    confidently wrong, and nothing downstream could tell. Here the only
    claim being made is eBay's own — these are the listings eBay says the
    photo resembles — and the agent never has to name the product at all.

    The price ceiling is applied by eBay through the same filter the typed
    search uses, so an image search and a typed search under the same
    budget are bounded identically.
    """
    usd_to_inr = settings.get("ebay", "usd_to_inr")
    if limit is None:
        limit = settings.get("scout", "result_limit")

    params = {"limit": limit}
    if max_price_paise:
        max_price_usd = round((max_price_paise / 100) / usd_to_inr, 2)
        params["filter"] = (
            f"price:[..{max_price_usd}],priceCurrency:USD,"
            "conditionIds:{1000|1500|1750|2000|2010|2020|2030|2500|3000|4000|5000|6000}"
        )

    response = httpx.post(
        IMAGE_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {_get_access_token()}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "Content-Type": "application/json",
        },
        params=params,
        json={"image": image_b64},
        timeout=40,
    )
    response.raise_for_status()
    items = response.json().get("itemSummaries") or []

    # The category is what a typed search would have put here. There is no
    # query, and inventing one would be the hallucination this whole path
    # exists to avoid, so it says where the match came from instead.
    return [_normalise_summary(i, usd_to_inr, "matched by image") for i in items]
