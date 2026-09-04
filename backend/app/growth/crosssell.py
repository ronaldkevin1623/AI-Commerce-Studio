"""
CROSS-SELL: WHAT ELSE IS WORTH SHOWING, FROM WHAT WAS ACTUALLY BOUGHT.

Pairs are learned from the store's own order history, not from a hand-written
"people who bought X also bought Y" table. If two products have never
appeared in orders together, this proposes nothing about them — which is
why on a small store it will often propose nothing at all. That is the
correct output, not a failure.

Where there is not enough history to learn a pair, it falls back to
CATEGORY ADJACENCY, and labels which of the two it used. The distinction
matters: "bought together twice" and "both filed under cables" are very
different strengths of claim, and a merchant deciding whether to give a
slot to something deserves to know which one they are looking at.

Costs nothing. It rearranges what is already shown rather than giving
anything away, so the gate lets it through on the free path and the
evidence floor does not apply — the floor exists to stop margin being spent
on thin data, and there is no margin here.
"""
import collections

from app.growth.base import Proposal

AGENT_ID = "crosssell"


class CrossSellAgent:
    agent_id = AGENT_ID
    name = "Suggests what goes with it"
    what = ("Learns which products were actually bought together from the "
            "store's own orders, and proposes a complement to show at "
            "checkout. Falls back to category adjacency where there is no "
            "co-purchase history, and says which it used.")
    spends_margin = False

    def detect(self) -> list[dict]:
        """Co-purchase pairs from real orders, plus the live catalogue."""
        try:
            from app.firebase_client import db
            from app.merchant import store
            orders = [d.to_dict() or {} for d in db.collection("orders").stream()]
            products = {p["id"]: p for p in store.list_products()
                        if (p.get("status") or "active") == "active"}
        except Exception as exc:
            print(f"[growth] cross-sell could not read data: {exc}", flush=True)
            return []

        pairs = collections.Counter()
        for order in orders:
            ids = [str(i.get("product_id") or i.get("id") or "")
                   for i in (order.get("items") or [])]
            ids = [i for i in ids if i in products]
            for a in ids:
                for b in ids:
                    if a < b:
                        pairs[(a, b)] += 1

        return [{"pairs": pairs, "products": products}]

    def _already_live(self, anchor_id: str, complement_id: str) -> bool:
        """
        ONE LIVE OFFER PER PAIR.

        Without this the scan re-proposes a pair every time it runs, and each
        approval writes another offer for the same two products — three live
        offers for one desk lamp, which is what a merchant would then see
        surfaced to buyers. Cart recovery already had this guard for carts;
        the same mistake was available here and nobody had made it yet.
        """
        try:
            from app.growth import registry
            for offer in registry.offers_for(anchor_id):
                if (offer.get("params") or {}).get("complement_id") == complement_id:
                    return True
        except Exception:
            # A guard that cannot read the datastore should not block the
            # proposal; the gate is still ahead of it.
            pass
        return False

    def propose(self, signals: list[dict]) -> list[Proposal]:
        if not signals:
            return []
        pairs = signals[0]["pairs"]
        products = signals[0]["products"]
        proposals = []

        # 1. Real co-purchase, where it exists.
        for (a, b), count in pairs.most_common(3):
            if self._already_live(a, b):
                continue
            proposals.append(self._pair_proposal(
                products[a], products[b], count,
                basis="bought together in this store's own orders"))

        # 2. Category adjacency, only to fill what history cannot answer.
        if not proposals:
            by_category = collections.defaultdict(list)
            for product in products.values():
                by_category[(product.get("category") or "").lower()].append(product)
            for category, group in by_category.items():
                if len(group) < 2 or not category:
                    continue
                anchor, complement = group[0], group[1]
                if self._already_live(anchor["id"], complement["id"]):
                    continue
                proposals.append(self._pair_proposal(
                    anchor, complement, 0,
                    basis=f"both filed under “{category}” — no order has "
                          f"contained them together"))
                if len(proposals) >= 2:
                    break
        return proposals

    def _pair_proposal(self, anchor: dict, complement: dict,
                       count: int, basis: str) -> Proposal:
        strong = count > 0
        return Proposal(
            agent=AGENT_ID,
            kind="cross_sell",
            headline=(f"Show “{complement['name'][:34]}” alongside "
                      f"“{anchor['name'][:34]}”"),
            detail=(
                f"{basis.capitalize()}"
                + (f", {count} time{'s' if count != 1 else ''}." if strong else ".")
                + f" Proposes offering {complement['name']} "
                  f"(₹{complement['price_paise'] / 100:,.0f}) at checkout for "
                  f"{anchor['name']}. Costs nothing — it fills a slot that is "
                  f"already on the page, and does not change any price."
                + ("" if strong else
                   " This is adjacency, not evidence: nobody has bought these "
                   "two together, and the suggestion is only as good as the "
                   "category filing.")),
            cost_paise=0,
            target_kind="product",
            target_id=anchor["id"],
            sample_size=count,
            evidence_note=(
                f"{count} co-purchase{'s' if count != 1 else ''} in the "
                f"store's orders." if strong else
                "No co-purchase history — category adjacency only."),
            params={"complement_id": complement["id"],
                    "basis": "co_purchase" if strong else "category"},
        )
