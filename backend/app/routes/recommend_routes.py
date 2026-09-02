"""
WHAT TO SHOW SOMEONE BEFORE THEY HAVE ASKED FOR ANYTHING.

Gathers candidates and behaviour, hands both to the scorer in
app/agent/recommend.py, and returns them in the order it decides. The
scoring argument lives there; this file is about where the inputs come from
and what is honest to say about them.

TWO RULES THAT SHAPE EVERYTHING HERE

  Seeded demo data is not behaviour. `/autonomy/demo/seed` writes synthetic
  purchase history so the replenishment demo has something to predict from,
  and at the time of writing that is 32 of 34 orders in the store. Treating
  it as evidence put a coffee refill at the top of the row for someone who
  had never searched for coffee — a recommendation derived from data the
  project wrote about itself. Seeded orders are excluded from the
  candidates, from the affinity history and from the consumption model
  used here. They are still real rows and the autonomy demo still uses
  them; they are just not a statement about what this person wants.

  A card without a photograph is a worse card. The shop has no product
  images yet, so those entries never make it to the row — instead the
  shortfall is filled with real marketplace listings for the things this
  person has actually searched for, which do have photographs. Showing a
  blank tile when a real picture was available was the wrong trade.

WHAT IT WILL NOT DO

No invented products, prices or reasons. The marketplace lookup is keyed on
searches this person actually ran, cached so opening the console repeatedly
does not re-spend quota, and skipped entirely when the order history alone
can fill the row. Sponsorship is not an input: the retail-media strip is a
separate, labelled thing, and a promoted product cannot buy its way in here.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter
from google.cloud import firestore

from app.agent import preferences, recommend, replenishment
from app.agent.catalog import NO_CEILING, deduplicate, search_catalog
from app.agent.ollama_agent import is_accessory_for
from app.agent.router import classify
from app.firebase_client import db, list_orders
from app.merchant import store

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

MAX_CARDS = 12
HISTORY_RUNS = 40
PAID = ("paid", "simulated_paid", "demo_paid")

# How many past searches get a live marketplace lookup, and how long the
# result is reused. Opening the console is not a reason to spend eBay quota
# every time, and these listings do not change minute to minute.
LOOKUP_TERMS = 4
# At most this many from any one search, so no single term can own
# the row.
PER_TERM = 3
CACHE_TTL = 600.0
_cache: dict = {}


def _seeded(order: dict) -> bool:
    return bool(order.get("demo_seeded")) or order.get("status") == "demo_paid"


def _search_history() -> list[dict]:
    """Product searches actually run, newest first, with a recency weight."""
    seen, out = set(), []
    try:
        # ORDERED. Without order_by, Firestore returns documents in id
        # order, which is arbitrary — so "newest first" was a claim this
        # function did not honour, and since only the first few terms get a
        # marketplace lookup, a search run a minute ago could sit below one
        # from last week and never reach the row. That is what made the
        # recommendations look frozen: they were not hardcoded, they were
        # sorted by nothing.
        rows = [d.to_dict() or {} for d in
                db.collection("runs")
                  .order_by("created_at", direction=firestore.Query.DESCENDING)
                  .limit(HISTORY_RUNS).get()]
    except Exception as exc:
        print(f"[recommend] could not read run history: {exc}", flush=True)
        return []

    for row in rows:
        query = (row.get("query") or "").strip()
        key = query.lower()
        if not query or key in seen:
            continue
        try:
            # has_results=True on purpose. A refinement only reads as one
            # when there is something to refine, so asking with False made
            # "under 5000" classify as a fresh search — and the row then
            # went looking for a product called "under 5000". Every row in
            # `runs` did follow something, so True is also the truth.
            if classify(query, has_results=True).get("route") != "search":
                continue
        except Exception:
            continue
        seen.add(key)
        out.append({"text": query, "weight": 1.0,
                    "label": f"your search for “{query[:32]}”"})
    return out


def _listings_for(term: str) -> list[dict]:
    """Live listings for one past search, cached."""
    now = time.time()
    hit = _cache.get(term.lower())
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        # NO_CEILING, not 0. Zero is turned into an eBay price filter of
        # price:[..0.00] — asking for things that cost nothing — and comes
        # back empty, which reads as "this product does not exist". The
        # constant exists in catalog.py precisely because this has bitten
        # before; passing 0 here silently emptied the whole row.
        found = deduplicate(search_catalog(term, NO_CEILING, None, None, {"1000"}))
        # Only what can actually be shown. An imageless listing is exactly
        # what this lookup exists to avoid.
        # Photographs only, and no accessories. A search for a phone that
        # comes back with a phone case is the accessory failure the main
        # pipeline screens for; the same screen belongs here, or the row
        # recommends a case to someone who wanted a handset.
        found = [f for f in found
                 if f.get("image")
                 and not is_accessory_for(f.get("name") or "", term)][:6]
    except Exception as exc:
        print(f"[recommend] lookup for {term!r} failed: {exc}", flush=True)
        found = []
    # An empty result is NOT cached. Caching it meant a single transient
    # marketplace failure blanked the whole row for ten minutes, and the
    # only symptom was a row with one card in it and no error anywhere.
    # Success is stable enough to reuse; failure is worth retrying.
    if found:
        _cache[term.lower()] = (now, found)
    return found


@router.get("")
def recommendations(limit: int = MAX_CARDS, customer_id: str = ""):
    orders = []
    try:
        orders = list_orders(limit=120)
    except Exception as exc:
        print(f"[recommend] could not read orders: {exc}", flush=True)

    paid = [o for o in orders if o.get("status") in PAID]
    real = [o for o in paid if not _seeded(o)]
    seeded_count = len(paid) - len(real)

    if not customer_id:
        customer_id = next((o.get("customer_id") for o in real
                            if o.get("customer_id")), "")

    profile = {}
    try:
        profile = preferences.build(customer_id) if customer_id else {}
    except Exception as exc:
        print(f"[recommend] could not build the profile: {exc}", flush=True)

    # The consumption model, over genuine purchases only. Seeded history is
    # what the autonomy demo predicts from; it is not what this person buys.
    due_items = []
    try:
        due_items = replenishment.profile(real)
    except Exception as exc:
        print(f"[recommend] consumption model unavailable: {exc}", flush=True)

    history = _search_history()
    for order in real[:20]:
        for item in (order.get("items") or []):
            if item.get("name"):
                history.append({"text": item["name"], "weight": 1.6,
                                "label": "something you bought"})

    candidates, seen_names = [], set()

    def add(product: dict, buyable: bool, why_source: str = "") -> None:
        name = (product.get("name") or "").strip()
        # No photograph, no card. The whole point of the marketplace lookup
        # below is that a real picture was available and we were showing a
        # blank instead.
        if not name or not product.get("price_paise") or not product.get("image"):
            return
        key = name.lower()[:60]
        if key in seen_names:
            return
        seen_names.add(key)
        candidates.append({
            "id": product.get("id"),
            "name": name,
            "price_paise": product.get("price_paise"),
            "image": product.get("image"),
            "category": product.get("category"),
            "condition": product.get("condition"),
            "source": product.get("source") or ("merchant" if buyable else "ebay"),
            "buyable": buyable,
            "url": product.get("url"),
            "seller_feedback": product.get("seller_feedback"),
            "why_source": why_source,
        })

    for order in real:
        for item in (order.get("items") or []):
            add(item, False, "bought")

    # The shop, if any of it can be shown. None of it has photographs at the
    # time of writing, so in practice this adds nothing — deliberately, and
    # it starts working the day the merchant uploads an image.
    try:
        for product in store.search("", 0):
            add({**product, "source": "merchant"}, True, "shop")
    except Exception as exc:
        print(f"[recommend] could not read the store: {exc}", flush=True)

    # Fill the shortfall with real listings for what was actually searched.
    looked_up = []
    if len(candidates) < limit:
        # Round-robin across the searches rather than draining one at a
        # time. Taking the first term's results in order filled the row
        # with five near-identical cables and six near-identical boots,
        # which is a search result, not a recommendation. Breadth across
        # what someone has looked for is the point of the row.
        # In parallel. Four sequential marketplace calls put ten seconds in
        # front of someone opening the console, which is ten seconds of
        # empty screen before the row they are meant to be reading appears.
        terms = [e["text"] for e in history[:LOOKUP_TERMS]]
        buckets = []
        if terms:
            with ThreadPoolExecutor(max_workers=len(terms)) as pool:
                for term, found in zip(terms, pool.map(_listings_for, terms)):
                    if found:
                        looked_up.append(term)
                        buckets.append((term, found))

        for depth in range(PER_TERM):
            if len(candidates) >= limit:
                break
            for term, found in buckets:
                if len(candidates) >= limit:
                    break
                if depth < len(found):
                    add(found[depth], False, f"searched:{term}")

    ranked = recommend.rank(candidates=candidates, profile=profile,
                            due_items=due_items, history=history)

    cards = []
    for card in ranked[:limit]:
        why = card.get("why")
        source = card.get("why_source") or ""
        if not why:
            if source.startswith("searched:"):
                why = f"Because you searched for “{source.split(':', 1)[1][:32]}”"
            elif source == "bought":
                why = "You bought this before"
            elif source == "shop":
                why = "In the shop the agent can actually pay"
        cards.append({**card, "why": why or "From your history"})

    personalised = sum(1 for c in ranked[:limit] if c["score"] > 0)
    return {
        "cards": cards,
        "count": len(cards),
        "personalised": personalised,
        "basis": {
            "real_orders": len(real),
            "seeded_orders_ignored": seeded_count,
            "tracked_for_replenishment": len(due_items),
            "searches_considered": len(history),
            "looked_up_live": looked_up,
            "price_band_paise": profile.get("median_paise"),
        },
        "note": (
            f"Ranked against {len(real)} real orders and {len(history)} things "
            f"you searched for or bought"
            + (f", topped up with live listings for {', '.join(looked_up)}"
               if looked_up else "")
            + f". {seeded_count} seeded demo orders were ignored."
            if (real or looked_up) else
            "Nothing to personalise from yet — no real orders and no searches."
        ),
    }
