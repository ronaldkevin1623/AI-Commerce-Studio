"""
WHERE A GROWTH OFFER STOPS BEING A ROW AND STARTS BEING MONEY OFF.

THE GAP THIS CLOSES

The recovery agent proposed a time-boxed discount on an abandoned cart. The
gate priced it, the daily budget reserved it, the decision log recorded it
as applied, and the merchant console counted it under "margin committed".
Then nothing read it. `params.discount_pct` was written by three agents and
read by exactly two places — the gate, to enforce a ceiling, and the
experiment agent, to group past offers into arms. No checkout, cart, order
or price path touched it.

So a merchant could approve 12% off to win a cart back, watch the margin
leave their daily budget, and the buyer coming back to that cart would pay
the full price. The docstring on the recovery agent said the discount was
"honoured when the buyer comes back to it". It was not. In a project whose
first principle is that nothing is faked, that was the one place the claim
outran the code.

This module is the missing half.

    claim()    a new basket matches an abandoned one that carries a live
               offer -> the discount is applied to the session total, so it
               flows into the Razorpay order and the buyer really pays less
    redeem()   that session paid -> the offer is spent, and can never be
               claimed again

HOW A CART IS RECOGNISED AS THE ONE THAT WAS ABANDONED

By its contents, not by a cookie or a link. The offer names a session; that
session has line items; a new session whose product ids are the same set is
the same cart being reconsidered. Quantities are deliberately not compared —
somebody who comes back and buys two instead of one has still come back —
but the discount is computed on the NEW total, so buying more does not
multiply the offer beyond its percentage.

WHAT IS DELIBERATELY NOT DONE

No stacking. One offer per session, the largest one that applies, because
two agents proposing against the same cart is a real possibility and a cart
that quietly took both would spend margin nobody approved as a single
figure.

No resurrection. An offer whose state is anything but `live` is ignored —
`redeemed` most of all. The whole risk with a discount held against a cart
is that it becomes a coupon that works forever.
"""
import time


def _epoch(value) -> float:
    from app.growth.recovery import _epoch as parse
    return parse(value)


def _basket_key(line_items: list) -> frozenset:
    """What identifies a cart for this purpose: which products are in it."""
    return frozenset(
        str(line.get("id") or line.get("product_id") or "")
        for line in (line_items or [])
        if (line.get("id") or line.get("product_id"))
    )


def _expired(offer: dict, now: float) -> bool:
    hours = float((offer.get("params") or {}).get("expires_in_hours") or 0)
    if not hours:
        return False
    return (now - _epoch(offer.get("created_at"))) > hours * 3600


def _discountable_offers(now: float) -> list[dict]:
    """Live, unexpired offers that carry a percentage off."""
    try:
        from app.firebase_client import db
        rows = [d.to_dict() or {} for d in db.collection("growth_offers").stream()]
    except Exception as exc:
        print(f"[redemption] could not read offers: {exc}", flush=True)
        return []
    out = []
    for offer in rows:
        if (offer.get("state") or "") != "live":
            continue
        if int((offer.get("params") or {}).get("discount_pct") or 0) <= 0:
            continue
        if _expired(offer, now):
            continue
        out.append(offer)
    return out


def find_for_basket(line_items: list, buyer: dict | None = None) -> dict | None:
    """
    The offer this basket is entitled to, if any.

    Matched three ways, in the order a claim is strongest:

      1. the same cart — an offer against a checkout session whose products
         are the set now being bought again
      2. this customer — a win-back offer aimed at whoever is checking out
      3. nothing

    Returns the offer plus the reason it applies, so the session, the
    receipt and the audit entry can all say the same true sentence.
    """
    now = time.time()
    offers = _discountable_offers(now)
    if not offers:
        return None

    basket = _basket_key(line_items)
    if not basket:
        return None

    matched = []

    # 1 — the abandoned cart, by contents.
    sessions = {}
    try:
        from app.merchant import store
        for doc in store.db.collection(store.SESSIONS).stream():
            row = doc.to_dict() or {}
            sessions[str(row.get("id") or doc.id)] = row
    except Exception as exc:
        print(f"[redemption] could not read checkouts: {exc}", flush=True)

    for offer in offers:
        if (offer.get("target_kind") or "") != "checkout_session":
            continue
        source = sessions.get(str(offer.get("target_id") or ""))
        if not source:
            continue
        # An offer against a cart that already paid is not a returning
        # buyer, it is a second discount on a settled sale.
        if (source.get("status") or "") == "paid":
            continue
        if _basket_key(source.get("line_items")) != basket:
            continue
        matched.append((offer, (
            f"the same basket was left unpaid as checkout "
            f"{offer.get('target_id')}, and an approved recovery offer is "
            f"still live against it")))

    # 2 — the customer, for win-back offers aimed at a person.
    customer_id = str((buyer or {}).get("customer_id") or (buyer or {}).get("id") or "")
    if customer_id:
        for offer in offers:
            if (offer.get("target_kind") or "") != "customer":
                continue
            if str(offer.get("target_id") or "") != customer_id:
                continue
            matched.append((offer, (
                "an approved win-back offer is live for this customer")))

    if not matched:
        return None

    # The largest single offer, never the sum. See the module docstring.
    offer, why = max(
        matched,
        key=lambda pair: int((pair[0].get("params") or {}).get("discount_pct") or 0))
    return {"offer": offer, "why": why,
            "discount_pct": int((offer.get("params") or {}).get("discount_pct") or 0)}


def claim(session_id: str, subtotal_paise: int, line_items: list,
          buyer: dict | None = None) -> dict | None:
    """
    Apply a live offer to a new checkout, and attach the claim to it.

    Returns the discount to subtract, or None. The caller subtracts it
    BEFORE the Razorpay order is created, so the order, the mandate and the
    money all describe the discounted total — a discount applied after the
    order exists is a discount the buyer never actually gets.
    """
    found = find_for_basket(line_items, buyer)
    if not found:
        return None

    offer = found["offer"]
    pct = found["discount_pct"]
    discount = int(int(subtotal_paise or 0) * pct / 100)
    if discount <= 0:
        return None

    offer_id = str(offer.get("offer_id") or "")
    try:
        from app.firebase_client import db
        # `claimed_by` is a pointer, not a lock. The state stays `live`
        # until the money arrives, so a buyer who abandons a second time
        # has not burned the offer — but the pointer means the offer and
        # the checkout can be joined from either end afterwards.
        db.collection("growth_offers").document(offer_id).update({
            "claimed_by": session_id,
            "claimed_at": time.time(),
            "claimed_discount_paise": discount,
        })
    except Exception as exc:
        # A discount that cannot be recorded is not applied. Giving money
        # off without the row that explains why is the same class of
        # untraceable spending the gate exists to prevent.
        print(f"[redemption] could not attach offer {offer_id}: {exc}", flush=True)
        return None

    note = (f"{pct}% off, because {found['why']}. Offer {offer_id}, "
            f"approved by {offer.get('approved_by') or 'the gate'}.")

    try:
        from app.firebase_client import log_decision
        log_decision(
            action_type="growth_offer_claimed",
            amount_paise=discount,
            decision="allowed",
            reason=(f"[{offer.get('agent')}] {note} Checkout {session_id} was "
                    f"priced at ₹{int(subtotal_paise) / 100:,.2f} and is "
                    f"charged ₹{(int(subtotal_paise) - discount) / 100:,.2f}. "
                    f"The margin was already reserved when the offer was "
                    f"applied; this is where it is actually given up."),
        )
    except Exception as exc:
        print(f"[redemption] claim not logged: {exc}", flush=True)

    return {"offer_id": offer_id, "agent": offer.get("agent"),
            "discount_pct": pct, "discount_paise": discount, "note": note}


def redeem(session_id: str, offer_id: str, payment_id: str = "") -> None:
    """
    The discounted checkout paid, so the offer is spent.

    Terminal on purpose: `redeemed` is never claimable again, which is what
    stops a cart-recovery discount turning into a permanent coupon.
    """
    if not offer_id:
        return
    try:
        from app.firebase_client import db
        db.collection("growth_offers").document(offer_id).update({
            "state": "redeemed",
            "redeemed_by": session_id,
            "redeemed_at": time.time(),
            "razorpay_payment_id": payment_id,
        })
    except Exception as exc:
        print(f"[redemption] could not mark {offer_id} redeemed: {exc}", flush=True)
        return

    try:
        from app.firebase_client import log_decision
        log_decision(
            action_type="growth_offer_redeemed",
            amount_paise=0,
            decision="allowed",
            reason=(f"Offer {offer_id} was redeemed on checkout {session_id}, "
                    f"which has now paid. The margin committed to it has "
                    f"been given up for a sale that happened — this is the "
                    f"one case where a growth action can be said to have "
                    f"worked, and it is why redeemed is reported separately "
                    f"from committed."),
        )
    except Exception as exc:
        print(f"[redemption] redemption not logged: {exc}", flush=True)
