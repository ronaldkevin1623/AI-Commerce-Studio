"""
BUNDLES: A SET WORTH BUYING TOGETHER, PRICED BELOW THE SUM.

Cross-sell suggests a second item and costs nothing. A bundle discounts the
set to make buying all of it worth more than buying one — so it gives away
margin, and lands on the paying side of the same gate.

WHY A BUNDLE NEEDS STRONGER EVIDENCE THAN A SUGGESTION

Showing someone a suggestion they ignore costs the merchant a slot. Pricing
a bundle wrong costs the merchant the difference on every sale that would
have happened anyway — including the ones where the customer was going to
buy the whole set at full price. That is the trap: a bundle's worst case is
not "nobody takes it", it is "everybody takes it and each sale earns less".

So this proposes only from OBSERVED co-purchase — never from category
adjacency, which cross-sell is allowed to fall back on. Two products filed
under the same heading is enough to justify a free suggestion and nowhere
near enough to justify discounting them together.

The evidence floor in the gate then applies on top, as it does to any costed
proposal: a bundle learned from one order is a proposal from a sample of
one, and the gate escalates it to a person rather than acting on it.
"""
import collections

from app.growth import graph
from app.growth.base import Proposal

AGENT_ID = "bundles"

# What the set comes down by. Deliberately modest: the whole argument for a
# bundle is that it converts customers who would have bought one item, and
# a large cut mostly subsidises the ones who were buying everything anyway.
BUNDLE_DISCOUNT_PCT = 7

# A bundle is at least this many items, or it is just a cross-sell.
MIN_ITEMS = 2


class BundleAgent:
    agent_id = AGENT_ID
    name = "Prices sets that sell together"
    what = ("Finds groups of products that have actually appeared in the "
            "same orders and proposes pricing the set below the sum of its "
            "parts. Uses observed co-purchase only — never category "
            "adjacency, which is enough for a free suggestion but not for "
            "giving away margin.")
    spends_margin = True

    def detect(self) -> list[dict]:
        """
        Observed clusters, grown from the co-purchase graph.

        A cluster starts from the strongest observed pair and admits a third
        product only if it has been bought with BOTH members — not merely
        with one of them. Chaining on a single link would let A-B and B-C
        become a three-item bundle nobody has ever bought as a set.
        """
        try:
            picture = graph.build()
        except Exception as exc:
            print(f"[growth] bundles could not build the graph: {exc}", flush=True)
            return []

        observed = [e for e in picture["edges"] if e["basis"] == "co_purchase"]
        if not observed:
            return []

        by_id = {n["id"]: n for n in picture["nodes"]}
        support = {tuple(sorted((e["source"], e["target"]))): e["support"]
                   for e in observed}
        neighbours = collections.defaultdict(set)
        for a, b in support:
            neighbours[a].add(b)
            neighbours[b].add(a)

        seen = set()
        clusters = []
        for (a, b), pair_support in sorted(support.items(),
                                           key=lambda kv: -kv[1]):
            members = [a, b]
            # Only a product bought with every existing member joins.
            for candidate in sorted(neighbours[a] & neighbours[b]):
                if all(tuple(sorted((candidate, m))) in support
                       for m in members):
                    members.append(candidate)
            members = tuple(sorted(members))
            if members in seen or len(members) < MIN_ITEMS:
                continue
            seen.add(members)

            products = [by_id[m] for m in members if m in by_id]
            if len(products) != len(members):
                continue
            # The weakest link is the honest support for the whole set: a set
            # is only as observed as its least-observed pair.
            weakest = min(support[tuple(sorted((x, y)))]
                          for i, x in enumerate(members)
                          for y in members[i + 1:]
                          if tuple(sorted((x, y))) in support)
            clusters.append({
                "members": products,
                "pair_support": pair_support,
                "weakest_support": weakest,
                "full_price_paise": sum(int(p.get("price_paise") or 0)
                                        for p in products),
            })

        clusters.sort(key=lambda c: (-c["weakest_support"],
                                     -len(c["members"])))
        return clusters

    def propose(self, signals: list[dict]) -> list[Proposal]:
        proposals = []
        for cluster in signals:
            full = cluster["full_price_paise"]
            if full <= 0:
                continue
            cost = int(full * BUNDLE_DISCOUNT_PCT / 100)
            names = [p["name"] for p in cluster["members"]]
            listed = " + ".join(names)
            support = cluster["weakest_support"]

            proposals.append(Proposal(
                agent=AGENT_ID,
                kind="offer_bundle",
                headline=(f"{BUNDLE_DISCOUNT_PCT}% off {listed} bought "
                          f"together — costs ₹{cost / 100:,.2f} of margin"),
                detail=(
                    f"These {len(names)} products have appeared in the same "
                    f"order {support} time{'' if support == 1 else 's'}. "
                    f"Priced separately the set is ₹{full / 100:,.2f}; as a "
                    f"bundle it would be ₹{(full - cost) / 100:,.2f}, giving "
                    f"away ₹{cost / 100:,.2f}. Every member has been bought "
                    f"with every other member — the set was not chained "
                    f"together from separate pairs. Worth knowing before "
                    f"approving: a bundle also discounts the customers who "
                    f"would have bought the whole set anyway."
                ),
                cost_paise=cost,
                target_kind="product_set",
                target_id="+".join(p["id"] for p in cluster["members"]),
                sample_size=support,
                evidence_note=(
                    f"Observed co-purchase only. The weakest pair in this set "
                    f"was seen {support} time{'' if support == 1 else 's'}, "
                    f"and that is the support for the whole bundle — a set is "
                    f"no better evidenced than its least-observed pair."
                ),
                params={
                    "discount_pct": BUNDLE_DISCOUNT_PCT,
                    "product_ids": [p["id"] for p in cluster["members"]],
                    "product_names": names,
                    "full_price_paise": full,
                    "bundle_price_paise": full - cost,
                    "basis": "co_purchase",
                },
            ))
        return proposals
