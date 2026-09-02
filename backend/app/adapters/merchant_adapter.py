"""
The UCP store — the direct-retailer adapter.

One seller, its own stock, and the only venue in this project that can
actually be paid and actually ship. It is reached over the Universal
Commerce Protocol: a discovery document at /.well-known/ucp naming its
capabilities, which is exactly the shape a third-party retailer would
expose. Nothing here knows it happens to be served by the same process.

`can_fulfil = True` is the whole reason this adapter exists beside eBay.
"""
from app.adapters.base import VenueAdapter


class UcpMerchantAdapter:
    name = "merchant"
    kind = "retailer"
    can_fulfil = True
    label = "Commerce Studio Demo Store"

    def available(self) -> bool:
        from app.agent import merchant_client
        try:
            return bool(merchant_client.discover())
        except Exception:
            return False

    def search(self, query, *, max_price_paise=0, condition_ids=None,
               requirements=None, sort=None):
        from app.agent import merchant_client

        listings = merchant_client.search(query, max_price_paise)
        for item in listings:
            item.setdefault("source", self.name)
        # First-party stock is new. The condition filter is expressed in
        # eBay's ids, so the retailer answers in the same vocabulary rather
        # than being exempted from the question.
        if condition_ids and "1000" not in condition_ids:
            return []
        return listings


assert isinstance(UcpMerchantAdapter(), VenueAdapter)
