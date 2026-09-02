"""
EVERY VENUE, ASKED IN PARALLEL, EACH ALLOWED TO FAIL ALONE.

The registry is the seam. Adding a channel is `register(MyAdapter())` and
nothing else: no edit to the search function, no branch in the pipeline, no
new word for the ranker to learn.

Three properties it has to keep, all of which existed before as hand-rolled
try/except and are now structural:

  One venue failing costs options, not the run. A marketplace being down
  should mean fewer listings, never an error page — and the run only fails
  if every venue fails.

  Venues are asked at the same time. Sequential calls made the slowest
  venue the floor for every search, and there is no reason a retailer
  should wait for a marketplace.

  What each venue returned is reported, not just the merged list. "eBay 22,
  the store 3, the third timed out" is the honest account of a multi-channel
  search; a single list hides which channel was silent.

HOW THE OTHER CHANNELS PLUG IN

The deck's entry points map onto this interface without changing it:

  Retail media    a retailer's sponsored inventory is a `retail_media`
                  adapter returning listings already marked sponsored; the
                  precision filters then apply to them exactly as to
                  organic results, which is Step 6's requirement.
  Brand sites     a `retailer` adapter per brand, same shape as the UCP
                  store — that one already speaks a public protocol, so a
                  real brand implementing UCP needs no code here at all.
  Social          a `social` adapter over a shoppable-post API; the listing
                  shape is the same, only `source` and `kind` differ.
  In store        an `in_store` adapter keyed by location, with
                  `can_fulfil` true and delivery replaced by collection.
  Other GenAI     a `genai_platform` adapter reading another assistant's
                  catalogue endpoint. This project already publishes one of
                  those itself, so the traffic runs both ways.

None of those are built. The seam is, and it is the same seam the two real
adapters use — which is the part that can be demonstrated rather than
described.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from app.adapters.base import AdapterResult
from app.adapters.ebay_adapter import EbayAdapter
from app.adapters.merchant_adapter import UcpMerchantAdapter
from app.adapters.sponsored_adapter import SponsoredAdapter

# Order matters only for reporting. Results are merged and then ranked on
# their own merits, so a venue cannot win by being registered first.
_ADAPTERS: list = [EbayAdapter(), UcpMerchantAdapter(), SponsoredAdapter()]


def register(adapter, *, replace: bool = False) -> None:
    """Add a venue. The whole of what integrating a new channel requires."""
    existing = next((a for a in _ADAPTERS if a.name == adapter.name), None)
    if existing:
        if not replace:
            raise ValueError(f"A venue named {adapter.name!r} is already registered.")
        _ADAPTERS.remove(existing)
    _ADAPTERS.append(adapter)


def unregister(name: str) -> bool:
    for adapter in list(_ADAPTERS):
        if adapter.name == name:
            _ADAPTERS.remove(adapter)
            return True
    return False


def adapters() -> list:
    return list(_ADAPTERS)


def describe() -> list[dict]:
    """What the agent can currently see, and what each venue can do."""
    out = []
    for adapter in _ADAPTERS:
        try:
            reachable = adapter.available()
        except Exception as exc:
            reachable = False
        out.append({
            "name": adapter.name,
            "label": getattr(adapter, "label", adapter.name),
            "kind": adapter.kind,
            "can_fulfil": adapter.can_fulfil,
            "available": reachable,
        })
    return out


def search_all(query: str, *, max_price_paise: int = 0,
               condition_ids: set | None = None,
               requirements: list | None = None,
               sort: str | None = None,
               timeout: float = 25.0) -> tuple[list[dict], list[AdapterResult]]:
    """
    Ask every reachable venue at once. Returns the merged listings and a
    per-venue account of what happened.
    """
    live = []
    for adapter in _ADAPTERS:
        try:
            if adapter.available():
                live.append(adapter)
        except Exception:
            continue

    def ask(adapter):
        started = time.time()
        try:
            found = adapter.search(
                query, max_price_paise=max_price_paise,
                condition_ids=condition_ids, requirements=requirements,
                sort=sort) or []
            return AdapterResult(adapter.name, adapter.kind, found,
                                 took_ms=int((time.time() - started) * 1000))
        except Exception as exc:
            # Reported, never raised. A venue that fails is a venue with
            # nothing to add today.
            print(f"[venues] {adapter.name} search failed: {exc}", flush=True)
            return AdapterResult(adapter.name, adapter.kind, [],
                                 error=f"{type(exc).__name__}: {exc}",
                                 took_ms=int((time.time() - started) * 1000))

    if not live:
        return [], []

    with ThreadPoolExecutor(max_workers=max(2, len(live))) as pool:
        results = list(pool.map(ask, live))

    merged: list[dict] = []
    for result in results:
        merged.extend(result.listings)
    return merged, results
