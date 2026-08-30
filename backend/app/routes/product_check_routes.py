"""
ONE LISTING, CHECKED.

The red-team suite attacks the pipeline. This examines a single listing —
a different question, asked of the thing somebody is about to pay for.

Every check reads live data. The listing is re-fetched from eBay, its price
is compared against what comparable listings actually cost right now, the
seller's record is read from eBay's own numbers, and the text is scanned
with the same detector the red team is built from. Nothing is cached, and
nothing has a fixed answer: run it twice on a listing whose price moved and
the two runs disagree, which is the point.

What it deliberately does NOT say is that a product is genuine, or that a
seller is honest. It cannot know either. A listing can pass every check here
and still be a bad purchase, and the wording throughout says so — a verdict
of "clear" means these checks found nothing, not that there is nothing to
find. The alternative is a green tick that means "we did not look hard
enough", which is worse than no tick at all.
"""
import statistics
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent import ebay_client, listing_scan
from app.agent.ollama_agent import (
    condition_conflict, is_accessory_for, matches_request, query_terms,
)
from app.redteam import runner

router = APIRouter()

# A seller with very few ratings is not a bad seller; they are an unknown
# one, and the difference matters when the decision is whether to hand over
# money. Chosen to match the shrinkage prior used in quality scoring.
THIN_HISTORY = 50

# eBay sellers cluster very high — the median is above 99% — so a figure
# down here is not a slightly worse seller, it is an unusual one. Kept
# separate from THIN_HISTORY because "nobody has rated them" and "people
# rated them badly" are opposite findings that a single rule would blur.
POOR_FEEDBACK = 90.0

# How far below the going rate before a price stops looking like a bargain
# and starts looking like a different product — or no product at all.
SUSPICIOUS_DISCOUNT = 0.45

# Comparable listings needed before a median means anything.
MIN_COMPARABLES = 4

# Where the buyer is. This agent prices in rupees and settles through an
# Indian Razorpay account, so everything it buys is delivered here.
DESTINATION = "IN"

# Names for the country codes eBay actually returns, so the panel can say
# "United States" rather than "US". Anything unlisted falls back to its code
# rather than being guessed at.
COUNTRY_NAMES = {
    "IN": "India", "US": "United States", "CN": "China", "HK": "Hong Kong",
    "GB": "United Kingdom", "DE": "Germany", "JP": "Japan", "CA": "Canada",
    "AU": "Australia", "SG": "Singapore", "AE": "United Arab Emirates",
    "KR": "South Korea", "FR": "France", "IT": "Italy", "ES": "Spain",
    "NL": "Netherlands", "PL": "Poland", "VN": "Vietnam", "TH": "Thailand",
    "MY": "Malaysia", "TW": "Taiwan", "MX": "Mexico", "BR": "Brazil",
    "ZA": "South Africa", "IL": "Israel", "TR": "Turkey", "CH": "Switzerland",
    "SE": "Sweden", "IE": "Ireland", "NZ": "New Zealand", "PH": "Philippines",
    "ID": "Indonesia", "PT": "Portugal", "AT": "Austria", "BE": "Belgium",
    "CZ": "Czechia", "DK": "Denmark", "FI": "Finland", "NO": "Norway",
    "RO": "Romania", "HU": "Hungary", "GR": "Greece", "LT": "Lithuania",
    "EE": "Estonia", "LV": "Latvia", "PK": "Pakistan", "BD": "Bangladesh",
    "LK": "Sri Lanka", "RU": "Russia", "UA": "Ukraine",
}


class ProductCheck(BaseModel):
    product: dict


def _check(check_id, label, status, detail, evidence=None):
    return {"id": check_id, "label": label, "status": status,
            "detail": detail, "evidence": evidence or {}}


def _inr(paise):
    return f"₹{(paise or 0) / 100:,.0f}"


def _live_listing(product):
    """The listing as eBay reports it right now, or None."""
    item_id = product.get("id") or ""
    if not item_id or product.get("source") == "merchant":
        return None
    try:
        return ebay_client.get_item(item_id)
    except Exception:
        return None


def _market(product):
    """
    What comparable listings cost, fetched now.

    The comparison set is built from the listing's own title words, so it is
    the market for this product rather than for its category. Too few
    comparables and no claim is made: a median of two is not a going rate.
    """
    terms = query_terms(product.get("name") or "")[:6]
    if len(terms) < 2:
        return None
    try:
        peers = ebay_client.search_live_catalog(" ".join(terms), 100_000_000,
                                                limit=25)
    except Exception:
        return None

    # The comparison set has to be the same product, or the median is
    # meaningless: an unscreened search for an iPhone returns the phone
    # alongside its cases and back glass, and the median of that came out at
    # ₹970 — against which a real phone at ₹1,03,749 looks like a scam and
    # an actual scam would look like a bargain. Screened the way the
    # pipeline screens, so peers are listings of the thing itself.
    comparable = [
        p for p in peers
        if p.get("price_paise")
        and p.get("id") != product.get("id")
        and not is_accessory_for(p.get("name") or "", "")
        and matches_request(p.get("name") or "", terms)[0]
    ]
    prices = [p["price_paise"] for p in comparable]
    if len(prices) < MIN_COMPARABLES:
        return None

    # Where this product is actually sold from, counted off the same
    # comparable set. Real geography, and the only kind on this page: a map
    # of listings that exist, not of threats somebody imagined.
    origins = {}
    for peer in comparable:
        country = (peer.get("item_location") or "").upper()
        if country:
            origins[country] = origins.get(country, 0) + 1

    return {"median": statistics.median(prices), "count": len(prices),
            "low": min(prices), "high": max(prices),
            "phrase": " ".join(terms), "origins": origins}


@router.post("/product-check")
def product_check(req: ProductCheck):
    product = req.product or {}
    if not product.get("id"):
        raise HTTPException(status_code=400, detail="No listing to check.")

    checks = []
    started = time.time()

    # ── 1. Is it still there, at that price? ─────────────────────────────
    live = _live_listing(product)
    shown = int(product.get("price_paise") or 0)
    if product.get("source") == "merchant":
        checks.append(_check(
            "exists", "The listing is live", "pass",
            "Sold by the Commerce Studio demo store, which this agent can "
            "price directly at checkout."))
    elif live is None:
        checks.append(_check(
            "exists", "The listing is live", "unknown",
            "eBay did not return this listing just now. It may have ended, "
            "or the lookup failed — either way the price below was not "
            "confirmed."))
    else:
        now = int(live.get("price_paise") or 0)
        if now and shown and now != shown:
            checks.append(_check(
                "exists", "The price is still what you were shown", "warn",
                f"eBay now reports {_inr(now)}, not the {_inr(shown)} on the "
                f"card. Live prices move; the amount charged is re-read at "
                f"checkout.", {"shown_paise": shown, "live_paise": now}))
        else:
            checks.append(_check(
                "exists", "The price is still what you were shown", "pass",
                f"Re-read from eBay just now: {_inr(now or shown)}."))

    # ── 2. Does the price make sense for this product? ───────────────────
    market = _market(product)
    if not market:
        checks.append(_check(
            "price", "The price sits where the market sits", "unknown",
            f"Fewer than {MIN_COMPARABLES} comparable listings came back, so "
            f"there is no going rate to compare against."))
    else:
        median = market["median"]
        ratio = (shown / median) if median else 1
        evidence = {"median_paise": median, "comparables": market["count"],
                    "low_paise": market["low"], "high_paise": market["high"],
                    "ratio": round(ratio, 3), "phrase": market["phrase"]}
        if ratio <= SUSPICIOUS_DISCOUNT:
            checks.append(_check(
                "price", "The price sits where the market sits", "fail",
                f"{_inr(shown)} is {round((1 - ratio) * 100)}% below the "
                f"{_inr(median)} median of {market['count']} comparable "
                f"listings. A phone at a third of the going rate is usually "
                f"an accessory, a part, or a listing that will not ship.",
                evidence))
        else:
            checks.append(_check(
                "price", "The price sits where the market sits", "pass",
                f"{_inr(shown)} against a {_inr(median)} median across "
                f"{market['count']} comparable listings "
                f"({_inr(market['low'])}–{_inr(market['high'])}).", evidence))

    # ── 3. The seller's record, as eBay reports it ───────────────────────
    feedback = product.get("seller_feedback")
    count = product.get("seller_feedback_count") or 0
    if product.get("source") == "merchant":
        checks.append(_check(
            "seller", "The seller has a record worth reading", "pass",
            "First-party store — the same party that operates this agent."))
    elif feedback is None:
        checks.append(_check(
            "seller", "The seller has a record worth reading", "warn",
            "eBay reports no feedback score for this seller. Not a mark "
            "against them; there is simply nothing to read."))
    elif feedback < POOR_FEEDBACK and count:
        checks.append(_check(
            "seller", "The seller has a record worth reading", "fail",
            f"{feedback}% positive across {count:,} ratings. Below "
            f"{POOR_FEEDBACK}% is a record of buyers who were unhappy, which "
            f"is different from a seller nobody has rated yet.",
            {"feedback": feedback, "count": count}))
    elif count < THIN_HISTORY:
        checks.append(_check(
            "seller", "The seller has a record worth reading", "warn",
            f"{feedback}% positive, but across only {count:,} ratings. Thin "
            f"history — an unknown seller rather than a poor one.",
            {"feedback": feedback, "count": count}))
    else:
        checks.append(_check(
            "seller", "The seller has a record worth reading", "pass",
            f"{feedback}% positive across {count:,} ratings"
            + (", and eBay marks them a top-rated seller."
               if product.get("top_rated_seller") else "."),
            {"feedback": feedback, "count": count,
             "top_rated": bool(product.get("top_rated_seller"))}))

    # ── 4. Does the listing contradict itself? ───────────────────────────
    conflict = condition_conflict(product)
    if conflict:
        checks.append(_check(
            "condition", "The listing agrees with itself", "fail",
            f"The seller selected “{product.get('condition')}” from eBay's "
            f"condition list, then wrote wording meaning “{conflict}” into "
            f"the title. Those cannot both be true."))
    else:
        checks.append(_check(
            "condition", "The listing agrees with itself", "pass",
            f"Declared “{product.get('condition') or 'unstated'}”, with "
            f"nothing in the title contradicting it."))

    # ── 5. Is the text talking to the agent? ─────────────────────────────
    findings = listing_scan.scan_item(product)
    if findings:
        markers = sorted({f["marker"] for f in findings})
        checks.append(_check(
            "text", "Nothing in the text is addressed to the agent", "fail",
            f"Found {', '.join(markers).lower()}. This does not change what "
            f"you are charged — price, stock and approval are decided by code "
            f"that never reads this text — but the seller tried.",
            {"findings": findings}))
    else:
        has_description = bool(product.get("description"))
        checks.append(_check(
            "text", "Nothing in the text is addressed to the agent", "pass",
            "No hidden instructions found in the title"
            + (" or description." if has_description else
               ". This listing has no description on file, so only the "
               "title was read.")))

    # ── 6. Is the price on the card the price of this option? ────────────
    if product.get("item_group_id"):
        checks.append(_check(
            "variant", "The price belongs to this exact option", "warn",
            "This is one option in a multi-variant listing. eBay quotes a "
            "representative price for the group, which may not be the option "
            "shown."))
    else:
        checks.append(_check(
            "variant", "The price belongs to this exact option", "pass",
            "A single listing, not one option inside a variant group."))

    # ── 7. Where it physically is ────────────────────────────────────────
    origin = (product.get("item_location") or "").upper()
    if product.get("source") == "merchant":
        checks.append(_check(
            "origin", "Where it ships from", "pass",
            "Ships within India from the Commerce Studio demo store — no "
            "border, no customs.",
            {"origin": DESTINATION, "destination": DESTINATION,
             "origins": {DESTINATION: 1}}))
    elif not origin:
        checks.append(_check(
            "origin", "Where it ships from", "unknown",
            "eBay did not say where this listing is located.",
            {"origins": (market or {}).get("origins") or {}}))
    else:
        crosses = origin != DESTINATION
        checks.append(_check(
            "origin", "Where it ships from",
            "warn" if crosses else "pass",
            (f"Ships from {COUNTRY_NAMES.get(origin, origin)} to "
             f"{COUNTRY_NAMES[DESTINATION]}. A cross-border purchase: customs "
             f"and duties can be charged on arrival, and a return has to "
             f"travel the same distance back."
             if crosses else
             f"Ships within {COUNTRY_NAMES[DESTINATION]} — no customs, and a "
             f"return stays domestic."),
            {"origin": origin, "destination": DESTINATION,
             "origins": (market or {}).get("origins") or {origin: 1}}))

    # ── 8. The suite's standing — system-wide, and said so ───────────────
    past = runner.history(1)
    if past:
        last = past[0]
        checks.append(_check(
            "suite", "The agent's own defences were tested",
            "pass" if last.get("breached") == 0 else "fail",
            f"{last.get('held')} of {last.get('total')} attacks blocked when "
            f"the red-team suite last ran, on "
            f"{time.strftime('%d %b, %I:%M %p', time.localtime(last.get('ran_at') or 0))}"
            f". That result is about this agent, not about this listing.",
            {"held": last.get("held"), "total": last.get("total")}))

    statuses = [c["status"] for c in checks]
    verdict = ("high_risk" if "fail" in statuses else
               "caution" if ("warn" in statuses or "unknown" in statuses)
               else "clear")

    return {
        "verdict": verdict,
        "checks": checks,
        "passed": statuses.count("pass"),
        "total": len(checks),
        "product": {"id": product.get("id"), "name": product.get("name"),
                    "price_paise": shown},
        "took_ms": int((time.time() - started) * 1000),
        "checked_at": time.time(),
    }
