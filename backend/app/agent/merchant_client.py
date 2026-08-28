"""
The buyer's side of the UCP handshake.

AI Commerce Studio searches eBay, which is a marketplace it has no relationship with:
it can read listings and it can hand you a link, but it cannot transact
there. This module talks to a merchant that AI Commerce Studio *can* transact with —
by discovering it the way the protocol intends, rather than by calling a
function it happens to share a process with.

WHY THIS GOES OVER HTTP TO ITSELF:
The demo store lives in the same FastAPI app. Importing `app.merchant.store`
directly would be one line and would work. It would also prove nothing —
the whole claim of UCP is that a buyer can find a seller it was never built
against, read what that seller offers, and use the endpoints the seller
names. Short-circuiting that leaves a demo that only works because both
halves were written by the same person. So: real HTTP, a real discovery
document, and the catalogue URL is read out of the manifest rather than
hardcoded here. Point MERCHANT_BASE_URL at somebody else's UCP store and
this code does not change.

WHAT IS NOT PROVEN:
Both parties still share one Razorpay test account, so money does not move
between strangers. That limitation belongs to the account, not the protocol,
and it is stated in the merchant's own discovery document.
"""
import time

import httpx

from app.config import MERCHANT_BASE_URL

UCP_VERSION = "2026-04-08"
SEARCH_CAPABILITY = "dev.ucp.shopping.catalog.search"
CHECKOUT_CAPABILITY = "dev.ucp.shopping.checkout"

# Discovery is cached briefly, not forever — a manifest is a live document
# and a merchant may withdraw a capability.
_cache = {"manifest": None, "at": 0.0}
_TTL_SECONDS = 60.0


def _headers(request_id: str = None) -> dict:
    """
    UCP names four request headers. `request-signature` is absent here
    because this deployment has no agent key registered with the merchant,
    and sending a header we do not actually compute would be worse than
    leaving it out.
    """
    headers = {
        "UCP-Agent": "AICommerceStudio/1.0 (+https://github.com/commerce-studio)",
        "Accept": "application/json",
    }
    if request_id:
        headers["request-id"] = request_id
    return headers


def discover(force: bool = False) -> dict | None:
    """
    Fetch and cache the merchant's discovery document.

    Returns None if the merchant is unreachable or serves something that
    isn't a UCP manifest. A buyer that cannot find a seller carries on
    shopping elsewhere; it does not fall over.
    """
    if not force and _cache["manifest"] and (time.time() - _cache["at"]) < _TTL_SECONDS:
        return _cache["manifest"]

    url = f"{MERCHANT_BASE_URL.rstrip('/')}/merchant/.well-known/ucp"
    try:
        response = httpx.get(url, headers=_headers(), timeout=5.0)
        response.raise_for_status()
        manifest = (response.json() or {}).get("ucp")
        if not manifest or not manifest.get("capabilities"):
            print(f"[merchant] {url} did not return a UCP manifest", flush=True)
            return None
    except Exception as exc:
        print(f"[merchant] discovery failed at {url}: {exc}", flush=True)
        return None

    _cache["manifest"] = manifest
    _cache["at"] = time.time()
    return manifest


def _endpoint(manifest: dict, capability: str) -> str | None:
    """Read the endpoint the merchant declares for a capability."""
    for entry in (manifest.get("capabilities") or {}).get(capability) or []:
        if entry.get("endpoint"):
            return entry["endpoint"]
    return None


def describe() -> dict:
    """
    What the buyer knows about the merchant right now — surfaced in the UI so
    a person can see whether a second venue was actually reachable, rather
    than inferring it from the absence of results.
    """
    manifest = discover()
    if not manifest:
        return {
            "available": False,
            "reason": f"No UCP merchant responded at {MERCHANT_BASE_URL}",
        }

    merchant = manifest.get("merchant") or {}
    return {
        "available": True,
        "id": merchant.get("id"),
        "name": merchant.get("name"),
        "disclosure": merchant.get("disclosure"),
        "version": manifest.get("version"),
        "capabilities": sorted((manifest.get("capabilities") or {}).keys()),
        "payment_handlers": sorted((manifest.get("payment_handlers") or {}).keys()),
        "can_checkout": bool(_endpoint(manifest, CHECKOUT_CAPABILITY)),
    }


def _normalise(product: dict, merchant: dict) -> dict:
    """
    Reshape a merchant product into the candidate shape the rest of the
    pipeline already speaks, so trust, ranking and the risk gate treat it
    identically to an eBay listing.

    Fields the merchant does not report are left absent rather than filled
    in. A first-party store has no seller-feedback percentage and no list
    price to discount from; inventing 4.0 stars and a 20% markdown to make
    the card look populated would be fabricating exactly the kind of number
    this project refuses to fabricate.
    """
    return {
        "id": product["id"],
        "name": product["name"],
        "category": product.get("category"),
        "price_paise": product["price_paise"],
        "original_price_paise": None,
        "discount_percent": None,
        "rating": None,
        "seller_feedback": None,
        # The store ships free and quotes no date, so the honest answer to
        # "when does it arrive" is that it hasn't said.
        "shipping_cost_paise": 0,
        "shipping_is_free": True,
        "delivery_estimate_from": None,
        "delivery_estimate_to": None,
        "delivery_days": None,
        "stock": product.get("stock"),
        "condition": product.get("condition"),
        "description": product.get("description"),
        "attributes": product.get("attributes") or {},
        "url": None,
        # Uploaded on the merchant's own product form and stored inline, so
        # there is a real picture to show whenever the operator added one.
        "image": product.get("image"),
        "images": [product["image"]] if product.get("image") else [],
        # What the rest of the app routes on.
        "source": "merchant",
        "merchant_id": merchant.get("id"),
        "merchant_name": merchant.get("name"),
    }


def search(query: str, max_price_paise: int) -> list[dict]:
    """
    Search the discovered merchant's catalogue.

    Returns [] on any failure — an unreachable second venue means fewer
    options, not a broken run.
    """
    manifest = discover()
    if not manifest:
        return []

    endpoint = _endpoint(manifest, SEARCH_CAPABILITY)
    if not endpoint:
        print(f"[merchant] does not declare {SEARCH_CAPABILITY}", flush=True)
        return []

    params = {"q": query or ""}
    if max_price_paise:
        params["max_price_inr"] = int(max_price_paise / 100)

    try:
        response = httpx.get(endpoint, params=params, headers=_headers(), timeout=8.0)
        response.raise_for_status()
        payload = response.json() or {}
    except Exception as exc:
        print(f"[merchant] catalogue search failed: {exc}", flush=True)
        return []

    merchant = payload.get("merchant") or manifest.get("merchant") or {}
    return [_normalise(p, merchant) for p in payload.get("products", [])]


def price_basket(items: list[dict]) -> dict:
    """
    Ask the merchant what a basket costs, before anything is gated.

    The gate has to run against the price that will actually be charged, and
    the only party who knows that is the seller. Reading it here — from a
    free, read-only catalogue call — means a stale or tampered client price
    is caught before an order exists, rather than after one has been created
    and has to be walked back.

    Returns {"ok": False, "error": ...} rather than raising, because "the
    store no longer sells that" is an ordinary answer, not a fault.
    """
    catalogue = {p["id"]: p for p in search("", 0)}
    if not catalogue:
        return {"ok": False, "error": "The merchant's catalogue could not be read."}

    resolved, total = [], 0
    for item in items:
        product = catalogue.get(str(item.get("id")))
        if not product:
            return {"ok": False, "error": f"The merchant no longer lists {item.get('name') or item.get('id')}."}

        quantity = max(1, int(item.get("quantity") or 1))
        stock = product.get("stock")
        if stock is not None and quantity > stock:
            return {"ok": False,
                    "error": f"{product['name']}: only {stock} in stock, {quantity} requested."}

        amount = product["price_paise"] * quantity
        total += amount
        resolved.append({**product, "quantity": quantity, "amount_paise": amount})

    return {"ok": True, "items": resolved, "total_paise": total}


def open_checkout(line_items: list[dict], buyer: dict, idempotency_key: str,
                  request_id: str = None) -> dict:
    """
    Ask the merchant to open a checkout session.

    The buyer sends ids and quantities only. It does not send prices — the
    merchant prices its own goods, and a buyer able to name its own price
    would make the whole gate theatre.
    """
    manifest = discover()
    if not manifest:
        raise RuntimeError(f"No UCP merchant reachable at {MERCHANT_BASE_URL}")

    endpoint = _endpoint(manifest, CHECKOUT_CAPABILITY)
    if not endpoint:
        raise RuntimeError(f"Merchant does not declare {CHECKOUT_CAPABILITY}")

    headers = _headers(request_id)
    headers["idempotency-key"] = idempotency_key

    response = httpx.post(
        endpoint,
        json={
            "line_items": [
                {"id": i["id"], "quantity": int(i.get("quantity") or 1)}
                for i in line_items
            ],
            "buyer": buyer or {},
        },
        headers=headers,
        timeout=20.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Merchant refused checkout: {_detail(response)}")
    return response.json()


def settle(session_id: str, razorpay_payment_id: str) -> dict:
    """Tell the merchant a payment happened. It verifies with Razorpay itself."""
    base = MERCHANT_BASE_URL.rstrip("/")
    response = httpx.post(
        f"{base}/merchant/checkout/{session_id}/settle",
        json={"razorpay_payment_id": razorpay_payment_id},
        headers=_headers(),
        timeout=20.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Merchant did not accept the payment: {_detail(response)}")
    return response.json()


def _detail(response) -> str:
    """A merchant's refusal is worth reading, so pull the reason out of it."""
    try:
        return str((response.json() or {}).get("detail") or response.text)
    except Exception:
        return response.text
