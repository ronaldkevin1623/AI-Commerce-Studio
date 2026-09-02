"""
eBay — the marketplace adapter.

Many sellers, one catalogue, no fulfilment relationship with this project.
Searchable and payable through Razorpay; nobody will ship it. That is what
`can_fulfil = False` says, and the interface carries it so no downstream
stage has to know the word "eBay" to know that.

The broadening and variant resolution stay here rather than moving to the
registry: both are specific to how eBay answers, and a retailer's own API
has neither problem.
"""
from app.adapters.base import VenueAdapter
from app.config import EBAY_CLIENT_ID, EBAY_CLIENT_SECRET


class EbayAdapter:
    name = "ebay"
    kind = "marketplace"
    can_fulfil = False
    label = "eBay"

    def available(self) -> bool:
        return bool(EBAY_CLIENT_ID and EBAY_CLIENT_SECRET)

    def search(self, query, *, max_price_paise=0, condition_ids=None,
               requirements=None, sort=None):
        # Imported here so the module loads without credentials — an
        # adapter that cannot run should report unavailable, not explode on
        # import and take the registry with it.
        from app.agent.catalog import _search_ebay
        from app.agent.ebay_client import resolve_variants

        listings = _search_ebay(query, max_price_paise, sort, condition_ids)
        for item in listings:
            item.setdefault("source", self.name)

        # A variation group's search price is one representative of the set.
        # Resolved before anything ranks, so every later stage reasons about
        # the price that would really be charged.
        try:
            listings = resolve_variants(listings, query, requirements)
            if max_price_paise:
                listings = [i for i in listings
                            if (i.get("price_paise") or 0) <= max_price_paise]
        except Exception as exc:
            print(f"[ebay] variant resolution skipped: {exc}", flush=True)

        return listings


assert isinstance(EbayAdapter(), VenueAdapter)
