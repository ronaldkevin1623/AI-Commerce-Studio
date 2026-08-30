"""
PRE-PURCHASE SAFETY CHECK

Run the checks that guard a purchase, before the money moves, and show a
person the result.

Nothing here is new protection. Every one of these already runs inside
/cart-checkout and already decides whether a charge happens — the price is
re-read from the seller, the gate votes, the mandate chain is verified. What
was missing is that all of it happened after the person committed, where
they could never see it. This runs the same checks first, on demand, and
says what it found.

Two things this deliberately is not:

It is not the red-team suite. That suite fires twenty-two attacks at the
pipeline and takes seventy seconds; it measures the system, not a product.
Running it here would spend a minute proving something that is true of every
purchase and nothing about this one, and a green light captioned "we checked
your item" on the back of it would be a claim nobody had earned. The suite's
last result is reported as what it is: a system-wide figure, with its date.

It is not a scanner that decides. The listing scan reads what a seller
wrote, and a hit means the seller tried something — not that buying is
unsafe. The gates that actually stop a bad charge never read that text, so a
finding is shown and never blocks. Blocking on it would both overstate the
scan and hand any seller a way to get a rival's listing refused.
"""
import time
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent import listing_scan, merchant_client, settings
from app.agent.budget_agent import assess as budget_assess
from app.agent.mandates import issue_intent_mandate, issue_cart_mandate, verify_chain
from app.agent.risk_gate import evaluate as risk_evaluate
from app.firebase_client import get_or_create_customer, log_decision
from app.redteam import runner

router = APIRouter()

# eBay is re-read per item, and a basket of ten would make this crawl. The
# cart is small in practice; this bounds the wait rather than the cart.
MAX_REPRICED_ITEMS = 5


class Preflight(BaseModel):
    items: list[dict]
    customer_email: str = "demo@commerce-studio.dev"
    customer_name: str = "Demo User"


def _check(check_id, label, plain, status, detail, extra=None):
    """
    One check, in the two registers the page needs.

    `label` and `plain` are what a shopper reads; `detail` is the finding
    itself. A check that cannot be performed says so with status "unknown"
    rather than passing quietly, because a check nobody ran is not a check
    that succeeded.
    """
    row = {"id": check_id, "label": label, "plain": plain,
           "status": status, "detail": detail}
    if extra:
        row.update(extra)
    return row


def _total(items):
    return sum(int(i.get("price_paise") or 0) * int(i.get("quantity") or 1)
               for i in items)


def _price_check(items, from_merchant):
    """
    Ask whoever sells it what it costs, and compare with the cart.

    This is the check with teeth: a mismatch is the one finding here that
    stops a purchase outright, because the alternative is charging an amount
    the seller does not agree to.
    """
    shown = _total(items)

    if from_merchant:
        priced = merchant_client.price_basket(items)
        if not priced.get("ok"):
            return _check(
                "price", "The price is still what you were shown",
                "We ask the shop what it charges, rather than trusting the page.",
                "fail", priced.get("error") or "The shop could not price this basket.")
        actual = priced["total_paise"]
        if actual != shown:
            return _check(
                "price", "The price is still what you were shown",
                "We ask the shop what it charges, rather than trusting the page.",
                "fail",
                f"The shop now charges ₹{actual / 100:,.2f}, not the "
                f"₹{shown / 100:,.2f} in your cart.")
        return _check(
            "price", "The price is still what you were shown",
            "We ask the shop what it charges, rather than trusting the page.",
            "pass", f"The shop confirms ₹{actual / 100:,.2f}.")

    # eBay: re-read each listing from eBay itself. The cart's figure came
    # from a search that may be minutes old.
    from app.agent import ebay_client

    if len(items) > MAX_REPRICED_ITEMS:
        return _check(
            "price", "The price is still what you were shown",
            "We re-read each listing from eBay rather than trusting the page.",
            "unknown",
            f"Not re-checked: this cart has {len(items)} items and this check "
            f"re-reads at most {MAX_REPRICED_ITEMS}.")

    moved, missing, checked = [], [], 0
    for item in items:
        try:
            live = ebay_client.get_item(item.get("id") or "")
        except Exception as exc:
            return _check(
                "price", "The price is still what you were shown",
                "We re-read each listing from eBay rather than trusting the page.",
                "unknown", f"eBay could not be reached: {type(exc).__name__}.")
        if live is None:
            missing.append(item.get("name") or item.get("id"))
            continue
        checked += 1
        was = int(item.get("price_paise") or 0)
        now = int(live.get("price_paise") or 0)
        if was and now and was != now:
            moved.append((item.get("name") or item.get("id"), was, now))

    if missing:
        return _check(
            "price", "The price is still what you were shown",
            "We re-read each listing from eBay rather than trusting the page.",
            "fail",
            f"{len(missing)} listing{'s' if len(missing) > 1 else ''} no longer "
            f"exists on eBay: {', '.join(str(m)[:48] for m in missing)}.")

    if moved:
        lines = "; ".join(f"{n[:40]} is now ₹{now / 100:,.2f}, was ₹{was / 100:,.2f}"
                          for n, was, now in moved)
        return _check(
            "price", "The price is still what you were shown",
            "We re-read each listing from eBay rather than trusting the page.",
            "fail", f"The price changed since you searched — {lines}.")

    # eBay quotes dollars; the rupee figure is a conversion, and calling that
    # "confirmed" would be claiming a precision the rate does not have.
    rate = settings.get("ebay", "usd_to_inr")
    return _check(
        "price", "The price is still what you were shown",
        "We re-read each listing from eBay rather than trusting the page.",
        "pass",
        f"{checked} listing{'s' if checked != 1 else ''} re-read from eBay, "
        f"price unchanged. eBay quotes US dollars; the rupee figure is "
        f"converted at ₹{rate} to the dollar.")


def _scan_check(items):
    scan = listing_scan.scan_basket(items)
    flagged = [row for row in scan["items"] if row["findings"]]

    # A title-only scan is a weaker statement than a scan that also read a
    # description, and saying "nothing found" without that caveat would
    # imply more than the text supports.
    no_desc = scan["items_scanned"] - scan["descriptions_available"]
    caveat = ""
    if no_desc:
        caveat = (f" {no_desc} of {scan['items_scanned']} "
                  f"{'listings have' if no_desc > 1 else 'listing has'} no "
                  f"description text on file, so only the title was read.")

    if not flagged:
        return _check(
            "listing_text", "Nothing in the listing is talking to the agent",
            "Sellers write the product page. We read it for instructions aimed "
            "at the agent instead of at you.",
            "pass",
            f"No hidden instructions found in {scan['items_scanned']} "
            f"listing{'s' if scan['items_scanned'] != 1 else ''}.{caveat}",
            {"scan": scan})

    markers = sorted({f["marker"] for row in flagged for f in row["findings"]})
    return _check(
        "listing_text", "Something in the listing is talking to the agent",
        "Sellers write the product page. We read it for instructions aimed "
        "at the agent instead of at you.",
        "warn",
        f"Found {', '.join(markers).lower()} in "
        f"{len(flagged)} listing{'s' if len(flagged) > 1 else ''}. This does not "
        f"change what you are charged — price, stock, your budget and your "
        f"approval are decided by code that never reads this text.{caveat}",
        {"scan": scan})


@router.post("/preflight")
def preflight(req: Preflight):
    sources = {(i.get("source") or "ebay") for i in req.items}
    from_merchant = sources == {"merchant"}
    checks = []

    if len(sources) > 1:
        checks.append(_check(
            "sellers", "One seller per order",
            "A payment settles to a single seller, so a mixed basket has no "
            "honest total.",
            "fail",
            f"This cart mixes {', '.join(sorted(sources))}. Check out one "
            f"seller at a time."))

    checks.append(_scan_check(req.items))
    price_row = _price_check(req.items, from_merchant)
    checks.append(price_row)

    # The amount the rest of the checks reason about. If the seller's own
    # figure differs from the cart's, theirs is the real one.
    total = _total(req.items)
    customer = get_or_create_customer(req.customer_name, req.customer_email)

    basket = {
        "id": f"preflight-{uuid.uuid4().hex[:12]}",
        "name": (req.items[0].get("name") if len(req.items) == 1
                 else f"{len(req.items)} items"),
        "price_paise": total,
        "stock": 1,
        "source": "merchant" if from_merchant else "ebay",
    }

    # record=False, or asking "would this pass?" becomes the duplicate that
    # fails it at checkout a moment later.
    risk = risk_evaluate(customer, basket, record=False,
                         allowed_venues={"ebay", "merchant"})
    decision = risk["decision"]
    checks.append(_check(
        "risk_gate", "The purchase is inside the limits you set",
        "Spending limits, repeat-order and velocity checks, decided before "
        "anything is charged.",
        "pass" if decision == "allowed" else
        "fail" if decision == "blocked" else "warn",
        risk["reason"]))

    budget = budget_assess(customer, total)
    over = budget["status"] == "exceeded"
    ceiling = settings.get("budget", "session_ceiling_inr") * 100
    checks.append(_check(
        "budget", "This fits your session budget",
        "The ceiling you set for what the agent may spend without you.",
        "warn" if over else "pass",
        budget["summary"] if over else
        f"₹{total / 100:,.2f} against your ₹{ceiling / 100:,.0f} ceiling.",
        {"over_ceiling": over}))

    # Sign this exact basket and verify the chain. Cheap, and it proves the
    # signature covers what is in the cart right now rather than asserting it.
    try:
        intent_jwt = issue_intent_mandate(
            {"query": basket["name"], "max_price_paise": total, "priority": "price"},
            customer["id"])
        cart = issue_cart_mandate(intent_jwt, basket, customer["id"])
        chain = verify_chain(intent_jwt, cart["cart_jwt"], basket)
        checks.append(_check(
            "mandate", "This basket is signed, and the signature matches",
            "Your instruction and this basket are cryptographically signed, so "
            "an item swapped afterwards fails the check.",
            "pass" if chain["ok"] else "fail",
            "Signature verified over this exact basket."
            if chain["ok"] else
            "; ".join(c["detail"] for c in chain.get("checks", []) if not c.get("ok"))
            or "The signature does not match this basket."))
    except Exception as exc:
        checks.append(_check(
            "mandate", "This basket is signed, and the signature matches",
            "Your instruction and this basket are cryptographically signed, so "
            "an item swapped afterwards fails the check.",
            "unknown", f"Could not be verified: {type(exc).__name__}."))

    # The suite's standing, stated as what it is: about the system, not this
    # product, and dated so nobody reads it as having just run.
    past = runner.history(1)
    if past:
        last = past[0]
        when = time.strftime("%d %b, %I:%M %p",
                             time.localtime(last.get("ran_at") or 0))
        checks.append(_check(
            "suite", "The agent's defences were tested",
            "A separate suite of attacks against the whole system — not "
            "against this product.",
            "pass" if last.get("breached") == 0 else "fail",
            f"{last.get('held')} of {last.get('total')} attacks blocked when the "
            f"suite last ran, on {when}. This is a system-wide result and says "
            f"nothing about this listing."))

    statuses = [c["status"] for c in checks]
    verdict = ("blocked" if "fail" in statuses else
               "attention" if ("warn" in statuses or "unknown" in statuses)
               else "clear")

    # Principle: every financial action is logged, including the ones that
    # do not happen. A clear preflight is noise; anything else is the record
    # of why a purchase paused.
    if verdict != "clear":
        log_decision(
            action_type="preflight_check",
            amount_paise=total,
            decision=verdict,
            reason="; ".join(f"{c['id']}: {c['detail']}"
                             for c in checks if c["status"] != "pass")[:800],
            customer_id=customer["id"],
        )

    return {
        "verdict": verdict,
        "checks": checks,
        "total_paise": total,
        "checked_at": time.time(),
    }
