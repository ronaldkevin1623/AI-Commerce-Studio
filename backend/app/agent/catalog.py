"""
Live eBay search, plus the UCP merchant store.

There is deliberately no static fallback. A search that finds nothing
returns nothing: inventing plausible products to fill a failed call would
put prices, ratings and stock counts on screen that no one can stand behind.
"""
from app.config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET


def search_catalog(category: str, max_price_paise: int, sort: str = None,
                   requirements: list = None, condition_ids: set = None) -> list[dict]:
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
    listings = _search_ebay(category, max_price_paise, sort, condition_ids)
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


# How few words a search may be reduced to before broadening stops. Below
# two, the query stops describing a product and starts describing a
# category, and the results are no longer an answer to what was asked.
MIN_SEARCH_WORDS = 2


def deduplicate(candidates: list[dict]) -> list[dict]:
    """
    One card per listing.

    A search for an iPhone came back with the same title at the same price
    twice, taking two of the five places on screen and making the shortlist
    a fifth smaller than it looked. eBay does return genuinely distinct item
    ids for what is effectively one offer relisted, so the id alone cannot
    catch this — the pair is identified by being the same seller offering
    the same title at the same price, which no two real listings are.

    The first occurrence wins, so whatever order the caller established is
    preserved.
    """
    seen = set()
    unique = []
    for item in candidates:
        key = (
            (item.get("name") or "").strip().lower(),
            item.get("price_paise"),
            (item.get("seller_username") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique

# Stands in for "any price" when probing whether a phrase has listings
# at all. Rs1 crore is far above anything this agent will be asked for.
NO_CEILING = 100_000_000


def _search_with_broadening(search_fn, phrase: str, max_price_paise: int,
                            sort: str = None):
    """
    The narrowest phrasing that actually returns listings.

    eBay matches all the words, so each extra specific ("8gb", "ram") can
    take the result set to zero. Rather than reporting an empty market, this
    drops trailing words until something comes back — the specifics are then
    enforced downstream by the attribute and relevance rules, which read
    titles properly instead of matching keywords.

    Returns the listings and the phrase that produced them, so the run can
    disclose that it broadened.
    """
    words = (phrase or "").split()
    attempt = list(words)
    _search_with_broadening.diagnosis = None

    while attempt:
        current = " ".join(attempt)
        found = [r for r in search_fn(query=current,
                                      max_price_paise=max_price_paise,
                                      sort=sort)
                 if (r.get("price_paise") or 0) > 0]
        if found:
            return found, current

        # Before assuming the words are wrong, check whether the budget is
        # what emptied the set. Dropping words here would answer a request
        # for a Rockerz 450 with a different pair of headphones.
        if max_price_paise:
            try:
                # A large ceiling, not zero: the client turns the cap into
                # an eBay price filter, so 0 asks for items costing nothing
                # and returns an empty set that looks like "does not exist".
                unbounded = [r for r in search_fn(query=current,
                                                  max_price_paise=NO_CEILING,
                                                  sort=sort)
                             if (r.get("price_paise") or 0) > 0]
            except Exception:
                unbounded = []
            if unbounded:
                cheapest = min(unbounded, key=lambda r: r["price_paise"])
                _search_with_broadening.diagnosis = {
                    "reason": "over_budget",
                    "phrase": current,
                    "cheapest_paise": cheapest["price_paise"],
                    "cheapest_name": cheapest.get("name"),
                    "seen": len(unbounded),
                }
                print(f"[catalog] {current!r} exists but starts at "
                      f"Rs{cheapest['price_paise'] / 100:,.0f}, above the "
                      f"Rs{max_price_paise / 100:,.0f} ceiling", flush=True)
                return [], current

        if len(attempt) <= MIN_SEARCH_WORDS:
            _search_with_broadening.diagnosis = {
                "reason": "not_found", "phrase": current,
            }
            return [], current

        dropped = attempt.pop()
        print(f"[catalog] no listings for {current!r} at any price — "
              f"retrying without {dropped!r}", flush=True)

    _search_with_broadening.diagnosis = {"reason": "not_found", "phrase": phrase}
    return [], phrase


def _search_ebay(category: str, max_price_paise: int, sort: str = None,
                 condition_ids: set = None) -> list[dict]:
    """
    Live listings, or an honest empty list.

    A failure here is reported and returns nothing. The caller still searches
    the merchant store, so the run continues with fewer options rather than
    with invented ones.
    """
    if not (EBAY_CLIENT_ID and EBAY_CLIENT_SECRET):
        print("[catalog] eBay credentials are not configured — no marketplace "
              "listings this run.", flush=True)
        return []

    try:
        from app.agent.ebay_client import search_live_catalog
        import functools
        # The condition filter rides along with every probe the broadening
        # makes, including the unbounded one that diagnoses an over-budget
        # search — otherwise dropping a word would quietly re-admit the
        # conditions the person did not ask for.
        search_fn = functools.partial(search_live_catalog,
                                      condition_ids=condition_ids)
        results, used = _search_with_broadening(
            search_fn, category, max_price_paise, sort)
        _search_ebay.last_phrase = used
        _search_ebay.last_diagnosis = getattr(
            _search_with_broadening, "diagnosis", None)
        # Brand standing, from eBay's own aspect distribution for this
        # search rather than from anything inferred about the titles.
        try:
            from app.agent import brands
            brands.annotate(results, category,
                            getattr(search_live_catalog, "last_aspects", None))
        except Exception as exc:
            print(f"[catalog] brand standing skipped: {exc}", flush=True)
        return results
    except Exception as e:
        print(f"[catalog] eBay search failed: {e} — returning no listings "
              f"rather than substituting any.", flush=True)
        return []
