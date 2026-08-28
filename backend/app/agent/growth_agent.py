"""
GROWTH AGENT

The merchant half of the track. Reads what is already in Firestore and
turns it into numbers a merchant could act on — no new data collection,
no estimates, no projections, no invented baselines.

TWO RULES THIS MODULE KEEPS:

1. Every figure traces to logged rows. Where there isn't enough data to
   support a claim, the payload says so via `sample` counts and the UI
   refuses to draw the chart rather than drawing a convincing-looking one
   over three points.

2. Config changes are not commerce. There are more `agent_setting_changed`
   rows in this database than purchase attempts, mostly from tuning the
   hive. Folding those into a funnel would inflate every activity chart
   and flatter the project, so they are counted separately and kept out.
"""
from collections import Counter, defaultdict

from app.firebase_client import (
    list_decisions,
    list_orders,
    list_market_scans,
    db,
)

# Action types that represent a real commerce event, as opposed to someone
# adjusting the agent's configuration.
COMMERCE_ACTIONS = {
    "purchase_attempt",
    "repick_attempt",
    "run_abandoned",
    "payment_confirmed",
    "payment_failed",
    "refund_issued",
}
CONFIG_ACTIONS = {"agent_setting_changed", "financial_bound_changed"}

# Below this many samples a distribution is noise, not a finding.
MIN_SAMPLE = 5


def _day(value):
    return value.date().isoformat() if hasattr(value, "date") else None


def _percentiles(values: list[int]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)

    def at(fraction):
        return ordered[min(int(len(ordered) * fraction), len(ordered) - 1)]

    return {
        "min": ordered[0],
        "p25": at(0.25),
        "median": at(0.5),
        "p75": at(0.75),
        "max": ordered[-1],
    }


def _histogram(values: list[int], edges: list[int]) -> list[dict]:
    """
    Bucket counts against explicit edges, so the axis never lies.

    The first bucket is open-ended downwards and the last open-ended upwards,
    which matters more than it sounds: eBay genuinely reports the occasional
    negative discount — a listing priced above its own reference price — and
    an earlier version dropped those on the floor, so the bars summed to one
    less than the stated sample. A chart whose bars don't add up to its own
    sample size is worse than no chart.
    """
    buckets = []
    for i, low in enumerate(edges):
        high = edges[i + 1] if i + 1 < len(edges) else None
        first, last = i == 0, high is None

        count = sum(
            1
            for v in values
            if (first or v >= low) and (last or v < high)
        )

        if first and last:
            label = "all"
        elif first:
            label = f"<{high}"
        elif last:
            label = f"{low}+"
        else:
            label = f"{low}–{high}"

        buckets.append({
            "label": label,
            "low": None if first else low,
            "high": high,
            "count": count,
        })
    return buckets


def _refunds() -> list[dict]:
    return [d.to_dict() for d in db.collection("refunds").get()]


def build_insights() -> dict:
    decisions = list_decisions()
    orders = list_orders(limit=500)
    scans = list_market_scans()
    refunds = _refunds()

    commerce = [d for d in decisions if d.get("action_type") in COMMERCE_ACTIONS]
    config = [d for d in decisions if d.get("action_type") in CONFIG_ACTIONS]

    # ── Funnel ───────────────────────────────────────────────────────────
    attempts = [d for d in commerce if d.get("action_type") in {"purchase_attempt", "repick_attempt"}]
    abandoned = [d for d in commerce if d.get("action_type") == "run_abandoned"]
    blocked = [d for d in attempts if d.get("decision") == "blocked"]
    escalated = [d for d in attempts if d.get("decision") == "escalated"]

    paid_orders = [o for o in orders if o.get("status") == "paid"]
    unpaid_orders = [o for o in orders if o.get("status") != "paid"]

    order_value = sum(o.get("amount_paise") or 0 for o in orders)
    captured = sum(o.get("amount_paise") or 0 for o in paid_orders)
    stranded = sum(o.get("amount_paise") or 0 for o in unpaid_orders)
    refunded = sum(r.get("amount_paise") or 0 for r in refunds)

    funnel = [
        {"stage": "Purchase attempts", "count": len(attempts)},
        {"stage": "Passed the gate", "count": len(attempts) - len(blocked)},
        {"stage": "Orders created", "count": len(orders)},
        {"stage": "Payments captured", "count": len(paid_orders)},
    ]

    # ── Why runs don't convert ───────────────────────────────────────────
    block_reasons = Counter(d.get("reason", "unstated") for d in blocked)
    abandon_stages = Counter(
        (d.get("reason") or "").replace("Person ended the run at stage: ", "") or "unknown"
        for d in abandoned
    )

    # ── Activity by day (commerce only) ──────────────────────────────────
    per_day = defaultdict(lambda: {"attempts": 0, "abandoned": 0, "orders": 0})
    for d in attempts:
        day = _day(d.get("timestamp"))
        if day:
            per_day[day]["attempts"] += 1
    for d in abandoned:
        day = _day(d.get("timestamp"))
        if day:
            per_day[day]["abandoned"] += 1
    for o in orders:
        day = _day(o.get("created_at"))
        if day:
            per_day[day]["orders"] += 1

    daily = [{"day": day, **counts} for day, counts in sorted(per_day.items())]

    # ── Market: real prices and discounts across every search ────────────
    prices, discounts, delivery = [], [], []
    listings_seen = discounted_listings = flagged_listings = 0
    per_query = defaultdict(lambda: {"listings": 0, "discounted": 0, "prices": []})

    for scan in scans:
        scan_prices = scan.get("prices_paise") or []
        prices.extend(scan_prices)
        discounts.extend(scan.get("discount_percents") or [])
        delivery.extend(scan.get("delivery_days") or [])
        listings_seen += scan.get("listing_count") or 0
        discounted_listings += scan.get("discounted_count") or 0
        flagged_listings += scan.get("flagged_count") or 0

        query = (scan.get("query") or "unknown").lower()
        per_query[query]["listings"] += scan.get("listing_count") or 0
        per_query[query]["discounted"] += scan.get("discounted_count") or 0
        per_query[query]["prices"].extend(scan_prices)

    # Ranked by discounted count, because that is what the chart measures —
    # sorting by total listings put every search at 30 and made the order
    # look arbitrary.
    by_query = sorted(
        (
            {
                "query": query,
                "listings": data["listings"],
                "discounted": data["discounted"],
                "median_price_paise": _percentiles(data["prices"]).get("median"),
            }
            for query, data in per_query.items()
        ),
        key=lambda r: (-r["discounted"], -r["listings"]),
    )[:8]

    market = {
        "scans": len(scans),
        "listings_seen": listings_seen,
        "sample": len(prices),
        "price_paise": _percentiles(prices),
        "price_buckets": _histogram(
            [p // 100 for p in prices], [0, 500, 1000, 2500, 5000, 10000]
        ),
        "discount_sample": len(discounts),
        "discount_buckets": _histogram(discounts, [0, 10, 25, 50, 70]),
        "discount_percentiles": _percentiles(discounts),
        "discounted_share": (
            round(discounted_listings / listings_seen * 100, 1) if listings_seen else None
        ),
        "flagged_share": (
            round(flagged_listings / listings_seen * 100, 1) if listings_seen else None
        ),
        "delivery_days": _percentiles(delivery),
        "by_query": by_query,
        "enough_data": len(prices) >= MIN_SAMPLE,
    }

    # Orders written before receipts became unique UUIDs used a receipt built
    # from product + customer, so a repeat purchase of the same item silently
    # overwrote the earlier record. Those rows make the order count understate
    # attempts, and the funnel has to say so rather than imply a drop-off that
    # never happened.
    legacy_orders = [o for o in orders if not str(o.get("id", "")).startswith("cp-")]

    # ── Headline numbers ─────────────────────────────────────────────────
    started = len(attempts) + len(abandoned)
    summary = {
        "order_value_paise": order_value,
        "captured_paise": captured,
        "stranded_paise": stranded,
        "refunded_paise": refunded,
        "orders": len(orders),
        "orders_paid": len(paid_orders),
        "attempts": len(attempts),
        "abandoned": len(abandoned),
        "blocked": len(blocked),
        "escalated": len(escalated),
        "config_changes": len(config),
        "legacy_orders": len(legacy_orders),
        "abandonment_rate": round(len(abandoned) / started * 100, 1) if started else None,
        "block_rate": round(len(blocked) / len(attempts) * 100, 1) if attempts else None,
        "conversion_rate": round(len(paid_orders) / len(orders) * 100, 1) if orders else None,
    }

    return {
        "summary": summary,
        "funnel": funnel,
        "daily": daily,
        "block_reasons": [{"reason": r, "count": c} for r, c in block_reasons.most_common(6)],
        "abandon_stages": [{"stage": s, "count": c} for s, c in abandon_stages.most_common(6)],
        "market": market,
        "notes": _notes(summary, market),
        "min_sample": MIN_SAMPLE,
    }


def _notes(summary: dict, market: dict) -> list[dict]:
    """
    Prose written from the numbers immediately above it. Each note names the
    figure it rests on, so nothing here is a claim you can't check.
    """
    notes = []

    if summary["orders"] and not summary["orders_paid"]:
        notes.append({
            "tone": "blocked",
            "text": (
                f"None of the {summary['orders']} orders created has been paid. "
                f"₹{summary['stranded_paise'] / 100:,.0f} of real Razorpay orders exist "
                "with no capture behind them — every one stops at checkout, which points "
                "at the test-mode card rejection rather than at anything upstream."
            ),
        })
    elif summary["conversion_rate"] is not None:
        notes.append({
            "tone": "ok",
            "text": (
                f"{summary['conversion_rate']}% of created orders were captured "
                f"(₹{summary['captured_paise'] / 100:,.0f})."
            ),
        })

    # Don't let the funnel imply a drop-off that is really a storage artefact.
    #
    # This gap never closes. `log_decision` writes with an auto-id, so the
    # attempt count keeps its full history, while the orders the old receipt
    # scheme overwrote are gone for good. So the explanation has to outlive the
    # legacy rows themselves: if they are ever migrated to `cp-` ids or deleted,
    # the gap stays and still needs saying. Gating this note on finding them
    # would remove the explanation and leave the drop-off it was explaining.
    unexplained = summary["attempts"] - summary["blocked"] - summary["escalated"] - summary["orders"]
    if unexplained > 0:
        if summary["legacy_orders"]:
            cause = (
                f"{summary['legacy_orders']} stored orders still use the old receipt scheme, which "
                "was derived from product and customer — so buying the same item twice overwrote "
                "the first record."
            )
        else:
            cause = (
                "No rows using the old receipt scheme are left to point at, but the gap is its "
                "residue: that scheme derived the id from product and customer, so buying the "
                "same item twice overwrote the first record."
            )
        notes.append({
            "tone": "warn",
            "text": (
                f"{summary['attempts']} purchase attempts produced only {summary['orders']} order "
                f"records, and blocks and escalations account for none of the gap. {cause} "
                "Receipts are unique UUIDs now, but those earlier orders are gone rather than "
                "merely unlabelled, so the historical count is understated and this funnel step "
                "should not be read as drop-off."
            ),
        })

    if summary["abandonment_rate"] is not None:
        notes.append({
            "tone": "warn" if summary["abandonment_rate"] >= 25 else "ok",
            "text": (
                f"{summary['abandonment_rate']}% of started runs were abandoned by the person "
                f"({summary['abandoned']} of {summary['attempts'] + summary['abandoned']}). "
                "Each one is logged with the stage it stopped at, so a started run never "
                "silently disappears from the trail."
            ),
        })

    if market["enough_data"] and market["discounted_share"] is not None:
        median_discount = market["discount_percentiles"].get("median")
        notes.append({
            "tone": "ok",
            "text": (
                f"{market['discounted_share']}% of the {market['listings_seen']} live listings "
                f"seen across {market['scans']} searches carried a discount"
                + (f", median {median_discount}% off" if median_discount else "")
                + f". Median asking price ₹{(market['price_paise'].get('median') or 0) / 100:,.0f}."
            ),
        })
    else:
        notes.append({
            "tone": "thin",
            "text": (
                f"Price and discount charts need at least {MIN_SAMPLE} observed listings; "
                f"there are {market['sample']}. Run a few searches from the console and they "
                "will fill in — every search records the whole result set, not just the pick."
            ),
        })

    if summary["config_changes"]:
        notes.append({
            "tone": "ok",
            "text": (
                f"{summary['config_changes']} agent configuration changes are logged separately "
                "and deliberately excluded from these funnel figures — tuning the hive is not "
                "commerce, and counting it as activity would flatter every chart here."
            ),
        })

    return notes
