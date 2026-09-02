"""
THE RETAIL MEDIA VENUE.

Step 5 left a `retail_media` kind in the adapter contract and a paragraph
saying how one would plug in. This is that adapter, and it needed no change
to the registry, the search function, the ranker or the risk gate to exist —
which was the claim the seam was making.

WHAT IT RETURNS, AND WHAT IT DELIBERATELY DOES NOT:

It returns promoted products the store's own keyword search would have
MISSED. Anything the shop would have surfaced anyway is not a placement:
that product earned its way in, and charging a merchant for a result they
were already getting would be selling them their own organic traffic. So
the organic search runs first and its ids are subtracted.

The broader net is CONTEXTUAL, which is what a retail media network
actually sells: reach against the category a search landed in. A promotion
on the USB-C hub can be considered for "mechanical keyboard" — a phrase
that returns a keyboard, in the hub's own category, which the store's
identity-weighted keyword search would never have matched the hub against.
When the store returns nothing at all, the promotion can still reach a
query whose own words overlap its category.

What it cannot reach is a category the search never touched. "Coffee pods"
returns nothing from this shop and shares no word with any category here,
so no promotion enters it. Sponsorship buys reach across a category, never
across the catalogue.

Everything returned is stamped `sponsored` before it leaves this file, and
nothing downstream removes that mark. It then goes through the identical
pipeline: accessory, relevance, condition, trust, precision, quality, rank.
The sort key does not read the mark. A promoted product that is out of
stock, overpriced against its peers, or simply not what was asked for is
dropped by the same screens that drop an organic listing, and the drop is
counted against the promotion.

IN PRODUCTION this would be the retailer's ad endpoint over HTTP rather than
the store module in this process. That changes where `eligible()` reads
from; it does not change the shape of what comes back or a line of anything
downstream, which is the part worth demonstrating.
"""
from app.agent import precision
from app.agent.merchant_client import _normalise
from app.agent.trust_agent import assess as trust_assess
from app.merchant import promotions, store


def _category_words(product: dict) -> set:
    """The words a promotion is allowed to reach across."""
    text = f"{product.get('category') or ''}".lower()
    return {w for w in text.replace("/", " ").replace("-", " ").split()
            if len(w) > 2}


def _query_words(query: str) -> set:
    return {w for w in (query or "").lower().replace("-", " ").split()
            if len(w) > 2}


def _context_words(organic: list[dict]) -> set:
    """
    The categories the search actually landed in.

    This is the reach a promotion buys. Matching the query's own words
    against the product's category — the obvious first version of this rule
    — bought nothing at all, because the store's keyword search already
    weighs category words as identity: every query that overlapped a
    category was returning those products organically anyway.
    """
    words = set()
    for item in organic:
        words |= _category_words(item)
    return words


class SponsoredAdapter:
    """Promoted inventory from the demo store, labelled and screened."""

    name = "sponsored"
    kind = "retail_media"
    # The products are the store's own, so a sponsored placement that gets
    # bought is a real order the store really ships. Sponsorship changes how
    # a product is found, never whether it exists.
    can_fulfil = True
    label = "Promoted placements"

    def available(self) -> bool:
        """
        Only when a promotion could actually run.

        Reporting this venue as available while every promotion is paused or
        out of budget would put a channel on screen that cannot contribute,
        which is the sort of decoration this project keeps out of the UI.
        """
        try:
            return bool(promotions.eligible())
        except Exception:
            return False

    def search(self, query: str, *, max_price_paise: int = 0,
               condition_ids: set | None = None,
               requirements: list | None = None,
               sort: str | None = None) -> list[dict]:
        try:
            eligible = promotions.eligible()
        except Exception as exc:
            print(f"[sponsored] could not read promotions: {exc}", flush=True)
            return []
        if not eligible:
            return []

        # What the shop returns on its own merit. Subtracted below, so a
        # promotion is never charged for reach it already had.
        try:
            found = store.search(query, max_price_paise)
        except Exception:
            found = []
        organic = {p["id"] for p in found}

        # Where a promotion is allowed to appear: the categories this search
        # landed in, plus — only when the shop returned nothing — the query's
        # own words, so a promotion can still reach a search the store missed
        # entirely rather than being locked out by its own irrelevance.
        reach = _context_words(found) or _query_words(query)
        merchant = {"id": store.MERCHANT_ID, "name": store.MERCHANT_NAME}

        placements = []
        for promo in eligible:
            if len(placements) >= promotions.MAX_PLACEMENTS:
                break
            product = promo.get("product") or {}
            product_id = product.get("id")
            if not product_id or product_id in organic:
                continue
            if max_price_paise and int(product.get("price_paise") or 0) > max_price_paise:
                continue
            # Condition is the shopper's constraint, not the merchant's to
            # buy past. Store stock is new, which is condition id 1000.
            if condition_ids and "1000" not in condition_ids:
                continue
            if reach and not (reach & _category_words(product)):
                continue

            item = _normalise(product, merchant)
            item.update({
                # `source` stays "merchant", which _normalise already set.
                # The project defines that field as "who checkout talks to",
                # and a placement is fulfilled by the shop — retail media is
                # a way of being FOUND, not a seller. Overwriting it with
                # "sponsored" would have routed checkout at a venue with no
                # checkout, and quietly excused the item from the condition
                # rule that keys on merchant stock being new.
                "sponsored": True,
                "sponsored_via": self.name,
                "sponsored_by": store.MERCHANT_NAME,
                # Carried so the audit trail can show what the placement
                # cost without going back to Firestore to find out.
                "sponsored_bid_paise": int(promo.get("bid_paise") or 0),
                "sponsored_note": (
                    "Promoted by the merchant. It was considered for this "
                    "search because of that; its position here is not — it "
                    "was ranked on stock, price, condition and approval "
                    "against everything else, and paid nothing for rank."
                ),
                "merchant_id": store.MERCHANT_ID,
            })
            placements.append(item)

        if placements:
            promotions.note_considered([p["id"] for p in placements])
            print(f"[sponsored] {len(placements)} promoted candidate(s) "
                  f"entered the pool for {query!r}", flush=True)
        return placements


assert isinstance(SponsoredAdapter(), __import__(
    "app.adapters.base", fromlist=["VenueAdapter"]).VenueAdapter)


# ── The complement slot ──────────────────────────────────────────────────

def complements(pool: list[dict], shown: list[dict]) -> list[dict]:
    """
    Promoted products offered BESIDE the answer, never inside it.

    This exists because of a measured result, not a hunch. Promoted items do
    enter the main candidate pool and compete there — and across five
    products and twelve queries, not one survived. The reason is structural:
    the relevance screen reads the product name, and so does the store's own
    keyword search, so anything whose name answers the query was already
    returned organically and anything reached contextually has a name that
    does not. The two gates read the same signal, which makes that channel
    provably empty rather than merely quiet.

    What is left is the thing retail media actually sells: the complement.
    Bought a keyboard, here is a hub. So a promoted product that shares the
    category the search landed in is offered in its own strip, under a label
    that says outright it is not an answer to the search — because it isn't,
    and a slot that implied otherwise would be the paid-placement-degrades-
    the-answer failure the rest of this project exists to prevent.

    It is exempt from relevance and from NOTHING else. Stock and buyability
    are checked with the same precision screen, trust with the same trust
    agent, and the ranked results above it are not touched: this reads the
    pool, and returns a separate list.
    """
    shown_ids = {str(s.get("id")) for s in shown or []}
    offers = [c for c in pool or []
              if c.get("sponsored") and str(c.get("id")) not in shown_ids]
    if not offers:
        return []

    # Precision, in its strict form. `precision.screen` deliberately stands
    # down rather than empty a result set — right for the answer to a
    # search, wrong here, where an empty complement strip is the correct
    # outcome and showing an unbuyable one is not.
    buyable = []
    for item in offers:
        availability = (item.get("availability") or "").upper()
        if availability and availability in precision.UNBUYABLE:
            continue
        if int(item.get("stock") or 0) <= 0:
            continue
        buyable.append(item)
    if not buyable:
        return []

    assessed = trust_assess(buyable)
    kept = [c for c in assessed["candidates"] if (c.get("trust") or {}).get("ok", True)]
    kept = kept[:promotions.MAX_PLACEMENTS]

    # Which slot this ended up in, so the disclosure can be accurate rather
    # than generic. A promoted product that survives into the ranked answer
    # and one offered beside it were treated differently, and telling a
    # shopper the wrong one would be worse than telling them nothing.
    for item in kept:
        item["sponsored_slot"] = "complement"
        item["sponsored_note"] = (
            "Promoted by the merchant and shown beside your results, not "
            "among them. It was not ranked against them and does not claim "
            "to answer your search — it is in the same category as what you "
            "found. It still had to be in stock and pass the same trust "
            "checks, and it changed nothing about the results above."
        )
    return kept
