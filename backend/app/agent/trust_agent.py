"""
TRUST AGENT

Flags listings that look unsafe to buy, using signals eBay actually
returns — no LLM involved, because these are statistical and
categorical checks that a model would only make less reliable.

Three real signals:
  1. Price outlier — a listing far below the median for its own result
     set is usually an accessory, a "box only" listing, or a scam.
     Your own screenshots showed exactly this: an "Adidas Men's Shoes"
     at a third the price of every comparable result.
  2. Seller feedback — eBay reports feedbackPercentage per seller.
  3. Condition — "For parts or not working" and similar are legitimate
     listings but almost never what an agent should auto-buy.
"""
import statistics

from app.agent import settings

# Thresholds are tunable from the Trust node on the hive canvas; these are
# the defaults the spec falls back to.
RISKY_CONDITIONS = {
    "for parts or not working",
    "parts only",
    "seller refurbished",
}


def _median_price(candidates: list[dict]) -> float:
    prices = [c["price_paise"] for c in candidates if c.get("price_paise")]
    return statistics.median(prices) if prices else 0


def _medians_by_source(candidates: list[dict]) -> dict:
    """
    One median per venue, not one across all of them.

    The outlier check asks "is this listing suspiciously cheap for what it
    sits beside?" That question only means something within a single
    marketplace. Once a first-party store's results are merged in with
    eBay's, a global median compares a Rs790 laptop sleeve against a set of
    phones and calls it a 95%-below-median scam — flagging an item whose
    price the merchant states outright. Grouping by source keeps the signal
    pointed at what it was built to catch.
    """
    grouped = {}
    for item in candidates:
        grouped.setdefault(item.get("source") or "ebay", []).append(item)
    return {source: _median_price(rows) for source, rows in grouped.items()}


def assess(candidates: list[dict]) -> dict:
    """
    Returns the candidate list with a `trust` block attached to each
    item, plus a summary of what was flagged.
    """
    outlier_floor_ratio = settings.get("trust", "outlier_floor_pct") / 100
    min_seller_feedback = float(settings.get("trust", "min_seller_feedback"))

    medians = _medians_by_source(candidates)
    flagged = 0

    for item in candidates:
        reasons = []

        median = medians.get(item.get("source") or "ebay", 0)
        price = item.get("price_paise") or 0
        if median and price < median * outlier_floor_ratio:
            pct = round((1 - price / median) * 100)
            reasons.append(f"{pct}% below the median for these results")

        feedback = item.get("seller_feedback")
        if feedback is not None and feedback < min_seller_feedback:
            reasons.append(f"seller feedback {feedback}%")

        condition = (item.get("condition") or "").strip().lower()
        if condition in RISKY_CONDITIONS:
            reasons.append(f"condition: {item['condition']}")

        item["trust"] = {
            "ok": not reasons,
            "reasons": reasons,
        }
        if reasons:
            flagged += 1

    if flagged == 0:
        summary = f"All {len(candidates)} listings passed trust checks"
    else:
        summary = f"Flagged {flagged} of {len(candidates)} listings as suspect"

    return {"candidates": candidates, "flagged": flagged, "summary": summary}