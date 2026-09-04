"""
THE PRODUCT RELATIONSHIP GRAPH.

Cross-sell already learned co-purchase pairs, but it learned them privately
and threw them away after proposing. That made the strongest claim in the
merchant stack — "these two things are bought together" — impossible to
inspect: you got the recommendation and had to take the basis on trust.

So the graph is built once, here, and everything else reads it: the
cross-sell agent, the bundle agent, and a merchant looking at the picture.

EVERY EDGE CARRIES ITS BASIS, AND THEY ARE NOT THE SAME CLAIM

    co_purchase          these two appeared in the same order, N times
    category_adjacency   these two are filed under the same category

The second is not evidence. It is a guess dressed as a relationship, and on
a store with almost no order history it is the only thing available — which
is exactly when it is most likely to be mistaken for the first. So it is
labelled on the edge, drawn differently, and never counted in `support`.

WHY THERE IS NO SIMILARITY SCORE

The obvious next move is to normalise support into a 0-1 "affinity" and rank
by it. With three orders that produces numbers like 0.67 that look like
statistics and are nothing of the kind. The graph reports the count it
actually observed and lets the reader see how small it is.
"""
import collections


def _co_purchase_pairs(orders: list, product_ids: set) -> collections.Counter:
    """How many times each unordered pair appeared in the same order."""
    pairs = collections.Counter()
    for order in orders:
        ids = {str(item.get("product_id") or item.get("id") or "")
               for item in (order.get("items") or order.get("line_items") or [])}
        ids = sorted(i for i in ids if i in product_ids)
        for a_index, a in enumerate(ids):
            for b in ids[a_index + 1:]:
                pairs[(a, b)] += 1
    return pairs


def _orders() -> list:
    """
    Both halves of the shop's history.

    `orders` holds the buyer-side record and `merchant_checkouts` the store's
    own sessions. A pair bought through the store's UCP endpoint is as real
    as one bought through the console, and reading only one collection would
    silently drop half the evidence.
    """
    from app.firebase_client import db
    rows = []
    for collection in ("orders", "merchant_checkouts"):
        try:
            rows.extend(d.to_dict() or {} for d in db.collection(collection).stream())
        except Exception as exc:
            print(f"[graph] could not read {collection}: {exc}", flush=True)
    return rows


def build() -> dict:
    """
    Nodes are the store's live products; edges are relationships between
    them, each labelled with what it is based on.
    """
    try:
        from app.merchant import store
        products = {p["id"]: p for p in store.list_products()
                    if (p.get("status") or "active") == "active"}
    except Exception as exc:
        print(f"[graph] could not read the catalogue: {exc}", flush=True)
        return {"nodes": [], "edges": [], "basis_counts": {},
                "note": f"The catalogue could not be read: {exc}"}

    orders = _orders()
    pairs = _co_purchase_pairs(orders, set(products))

    edges = []
    for (a, b), support in pairs.items():
        edges.append({
            "source": a, "target": b,
            "basis": "co_purchase",
            "support": support,
            "label": (f"bought together {support} time"
                      f"{'' if support == 1 else 's'}"),
        })

    # Category adjacency fills the picture in where history does not reach.
    # Only between products that have no observed pair — an adjacency edge
    # drawn over real evidence would hide the evidence.
    observed = {tuple(sorted((e["source"], e["target"]))) for e in edges}
    by_category = collections.defaultdict(list)
    for product in products.values():
        category = (product.get("category") or "").strip().lower()
        if category:
            by_category[category].append(product["id"])

    for category, ids in by_category.items():
        ids = sorted(ids)
        for a_index, a in enumerate(ids):
            for b in ids[a_index + 1:]:
                if (a, b) in observed:
                    continue
                edges.append({
                    "source": a, "target": b,
                    "basis": "category_adjacency",
                    # Zero, not one. Nothing was observed. Writing 1 here
                    # would make an assumption indistinguishable from a sale.
                    "support": 0,
                    "label": f"both filed under {category}",
                })

    nodes = [{
        "id": product["id"],
        "name": product["name"],
        "category": product.get("category"),
        "price_paise": product.get("price_paise"),
        "stock": product.get("stock"),
        "degree": sum(1 for e in edges
                      if product["id"] in (e["source"], e["target"])),
        "observed_degree": sum(1 for e in edges
                               if e["basis"] == "co_purchase"
                               and product["id"] in (e["source"], e["target"])),
    } for product in products.values()]
    nodes.sort(key=lambda n: (-n["observed_degree"], -n["degree"], n["name"]))

    observed_edges = sum(1 for e in edges if e["basis"] == "co_purchase")
    return {
        "nodes": nodes,
        "edges": edges,
        "orders_read": len(orders),
        "basis_counts": {
            "co_purchase": observed_edges,
            "category_adjacency": len(edges) - observed_edges,
        },
        # Said in the payload, so a client that only renders the graph still
        # has the sentence that stops it being over-read.
        "note": (
            f"{observed_edges} edge{'' if observed_edges == 1 else 's'} learned "
            f"from {len(orders)} order record{'' if len(orders) == 1 else 's'}. "
            f"The rest are category adjacency — not evidence that anyone bought "
            f"the two together, and drawn differently for that reason."
            if observed_edges else
            f"No two products have yet appeared in the same order across "
            f"{len(orders)} order record{'' if len(orders) == 1 else 's'}. Every "
            f"edge shown is category adjacency: a guess about what goes with "
            f"what, not an observation."
        ),
    }


def complements(product_id: str, limit: int = 3) -> list[dict]:
    """
    What goes with this product, strongest evidence first.

    Observed pairs outrank adjacency absolutely rather than by score — one
    real co-purchase beats any number of things filed in the same folder,
    and a weighting that let adjacency outrank evidence would defeat the
    point of tracking the distinction.
    """
    graph = build()
    by_id = {n["id"]: n for n in graph["nodes"]}
    out = []
    for edge in graph["edges"]:
        if product_id not in (edge["source"], edge["target"]):
            continue
        other = edge["target"] if edge["source"] == product_id else edge["source"]
        node = by_id.get(other)
        if not node:
            continue
        out.append({**node, "basis": edge["basis"], "support": edge["support"],
                    "why": edge["label"]})
    out.sort(key=lambda c: (0 if c["basis"] == "co_purchase" else 1,
                            -c["support"], c["name"]))
    return out[:limit]
