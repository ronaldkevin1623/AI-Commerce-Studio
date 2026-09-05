"""
DID ANY OF IT WORK? — REVENUE ATTRIBUTED TO THE GROWTH AGENTS.

This closes the loop the rest of the merchant stack opens: agents observe,
propose, get gated, and act. Without this last step nobody can say whether
acting was worth the margin it cost, and "AI-generated revenue" stays a
claim rather than a number.

THE RULE THIS MODULE EXISTS TO ENFORCE

Attribution is the easiest place in a commerce system to lie, because the
lie is arithmetic rather than invention. Take every order that happened
after a campaign started, call it "AI-influenced", and you have a large
impressive number that would have been almost identical with no agent
running at all. That is how most dashboards produce their uplift figures.

So the only orders counted here are ones where an agent's action is
attached to the order itself:

    the offer was applied to THAT checkout session, and that session paid;
    the offer was applied to THAT customer, and that customer then ordered;
    the cross-sell recommended THAT product, and that product was then bought.

An order the agents never touched is never counted, however well-timed. And
where a cross-sell converts, only the recommended line is counted rather than
the basket it arrived in — the agent caused the addition, not the purchase.

AND WHAT THIS STILL CANNOT TELL YOU

Counterfactual. Some of these customers would have paid without the offer,
and nothing here can separate them — that needs a holdout group, which
needs traffic this build does not have. So the payload reports margin GIVEN
AWAY beside revenue attributed, and states plainly that the net is not a
profit figure. A merchant reading it should be able to see the cost of the
uncertainty as easily as the size of the number.
"""
import time


def _epoch(value) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except Exception:
            return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _applied_offers() -> list[dict]:
    """Growth actions that were actually applied — the gate let them through."""
    try:
        from app.firebase_client import db
        return [d.to_dict() or {} for d in db.collection("growth_offers").stream()]
    except Exception as exc:
        print(f"[attribution] could not read offers: {exc}", flush=True)
        return []


def build(days: int = 30) -> dict:
    """
    What the growth agents cost, and what can honestly be traced back to them.
    """
    days = max(1, min(int(days or 30), 365))
    since = time.time() - days * 86400

    offers = [o for o in _applied_offers() if _epoch(o.get("created_at")) >= since]
    spent_paise = sum(int(o.get("cost_paise") or 0) for o in offers)

    # Index the applied actions by what they were aimed at, so an order is
    # matched by identity rather than by having happened afterwards.
    by_session = {}
    by_customer = {}
    by_complement = {}
    for offer in offers:
        target_kind = offer.get("target_kind") or ""
        target_id = str(offer.get("target_id") or "")
        if not target_id:
            continue
        if target_kind == "checkout_session":
            by_session.setdefault(target_id, []).append(offer)
        elif target_kind == "customer":
            by_customer.setdefault(target_id, []).append(offer)
        elif target_kind == "product":
            # A cross-sell is aimed at the ANCHOR product but its result is
            # the COMPLEMENT appearing in a basket, so it is indexed by the
            # thing whose presence would be the evidence.
            complement = (offer.get("params") or {}).get("complement_id")
            if complement:
                by_complement.setdefault(str(complement), []).append(offer)

    converted = []

    # 1. A cart an offer was applied to, which then paid.
    try:
        from app.merchant import store
        for doc in store.db.collection(store.SESSIONS).stream():
            row = doc.to_dict() or {}
            session_id = str(row.get("id") or doc.id)
            if session_id not in by_session:
                continue
            if (row.get("status") or "") != "paid":
                continue
            converted.append({
                "kind": "recovered_cart",
                "target_id": session_id,
                "revenue_paise": int(row.get("total_paise") or 0),
                # What the offer actually cost, now that somebody took it.
                "cost_paise": sum(int(o.get("cost_paise") or 0)
                                  for o in by_session[session_id]),
                # When the discount became real — the moment of the sale, not
                # the moment of the offer. A discount belongs to the period
                # the money moved in.
                "when": _epoch(row.get("paid_at")) or _epoch(row.get("created_at")),
                "agents": sorted({o.get("agent") or "" for o in by_session[session_id]}),
                "why": ("An offer was applied to this specific checkout "
                        "session, and this specific session then paid."),
            })
    except Exception as exc:
        print(f"[attribution] could not read checkouts: {exc}", flush=True)

    # 1b. THE OFFER WAS ACTUALLY SPENT ON THIS CHECKOUT.
    #
    # The rule above matches an offer to the session it was AIMED at. This
    # matches it to the session it was REDEEMED on, which is a different
    # and stronger claim: a returning buyer opens a new checkout, the
    # discount comes off that one, and the offer carries its id. Without
    # this branch the only conversions that could ever be counted were
    # carts that paid on their original session — the one flow a returning
    # buyer does not take.
    by_offer_id = {str(o.get("offer_id") or ""): o for o in offers}
    counted_sessions = {c["target_id"] for c in converted}
    try:
        from app.merchant import store
        for doc in store.db.collection(store.SESSIONS).stream():
            row = doc.to_dict() or {}
            if (row.get("status") or "") != "paid":
                continue
            offer_id = str(row.get("discount_offer_id") or "")
            offer = by_offer_id.get(offer_id)
            if not offer:
                continue
            session_id = str(row.get("id") or doc.id)
            if session_id in counted_sessions:
                continue
            converted.append({
                "kind": "recovered_cart",
                "target_id": session_id,
                "revenue_paise": int(row.get("total_paise") or 0),
                # What the discount REALLY cost, not what it was priced at:
                # the offer was sized against the abandoned basket and spent
                # against this one, and the amount that came off is the
                # amount the merchant gave up.
                "cost_paise": int(row.get("discount_paise")
                                  or offer.get("cost_paise") or 0),
                "when": _epoch(row.get("paid_at")) or _epoch(row.get("created_at")),
                "agents": [offer.get("agent") or ""],
                "why": (f"An approved offer was redeemed on this checkout — "
                        f"₹{int(row.get('discount_paise') or 0) / 100:,.2f} came "
                        f"off the price the buyer actually paid."),
            })
    except Exception as exc:
        print(f"[attribution] could not read redemptions: {exc}", flush=True)

    # 2. A customer an offer was applied to, who then ordered — and only
    #    orders placed AFTER the offer. An earlier order is not a result of
    #    a later action, and the ordering check is what stops this becoming
    #    "everything that customer ever bought".
    try:
        from app.firebase_client import db
        for doc in db.collection("orders").stream():
            row = doc.to_dict() or {}
            customer_id = str(row.get("customer_id") or "")
            if customer_id not in by_customer:
                continue
            if not str(row.get("status") or "").endswith("paid"):
                continue
            placed = _epoch(row.get("created_at"))
            earliest = min(_epoch(o.get("created_at")) for o in by_customer[customer_id])
            if placed < earliest:
                continue
            converted.append({
                "kind": "reactivated_customer",
                "target_id": customer_id,
                "revenue_paise": int(row.get("amount_paise") or 0),
                "cost_paise": sum(int(o.get("cost_paise") or 0)
                                  for o in by_customer[customer_id]),
                "when": placed,
                "agents": sorted({o.get("agent") or "" for o in by_customer[customer_id]}),
                "why": ("A win-back offer was applied to this customer, and "
                        "this order was placed after it."),
            })
    except Exception as exc:
        print(f"[attribution] could not read orders: {exc}", flush=True)

    # 3. A cross-sell the merchant approved, where the complement it
    #    recommended then appeared in a paid basket after the approval.
    #
    #    ONLY THE COMPLEMENT'S LINE IS COUNTED, NOT THE ORDER.
    #
    #    This is the whole difference between attribution and flattery. A
    #    customer who was buying a ₹2,799 pair of shoes anyway, and added
    #    ₹249 of socks because the shop suggested them, generated ₹249 of
    #    agent revenue — not ₹3,048. Counting the basket would make every
    #    cross-sell look transformative and would be the easiest number on
    #    this page to inflate.
    try:
        from app.merchant import store
        for doc in store.db.collection(store.SESSIONS).stream():
            row = doc.to_dict() or {}
            if (row.get("status") or "") != "paid":
                continue
            placed = _epoch(row.get("created_at"))
            for line in (row.get("line_items") or []):
                offers_for_line = by_complement.get(str(line.get("id") or ""))
                if not offers_for_line:
                    continue
                earliest = min(_epoch(o.get("created_at")) for o in offers_for_line)
                # An order placed BEFORE the offer was approved cannot be a
                # result of it, however well the two happen to line up.
                if placed < earliest:
                    continue
                converted.append({
                    "kind": "cross_sell",
                    "target_id": str(line.get("id")),
                    "revenue_paise": int(line.get("amount_paise") or 0),
                    # Cross-sells are free, so this is almost always zero —
                    # carried anyway so every conversion has the same shape
                    # and a costed variant could never be missed.
                    "cost_paise": sum(int(o.get("cost_paise") or 0)
                                      for o in offers_for_line),
                    "when": placed,
                    "agents": sorted({o.get("agent") or "" for o in offers_for_line}),
                    "why": (f"An approved cross-sell recommended "
                            f"{line.get('name') or line.get('id')}, and it was "
                            f"then bought in a paid basket. Only this line is "
                            f"counted, not the order it arrived in."),
                })
    except Exception as exc:
        print(f"[attribution] could not read checkouts for cross-sell: {exc}",
              flush=True)

    attributed_paise = sum(c["revenue_paise"] for c in converted)
    redeemed_paise = sum(int(c.get("cost_paise") or 0) for c in converted)

    if not offers:
        headline = ("No growth action has been applied in this window, so "
                    "there is nothing to attribute. This is zero because "
                    "nothing was tried, not because nothing worked.")
    elif not converted:
        headline = (f"{len(offers)} action{'' if len(offers) == 1 else 's'} "
                    f"applied, costing ₹{spent_paise / 100:,.2f} of margin. "
                    f"None has converted yet. An action that has not converted "
                    f"is not the same as one that failed — most of these are "
                    f"still open.")
    else:
        headline = (f"₹{attributed_paise / 100:,.2f} across "
                    f"{len(converted)} order{'' if len(converted) == 1 else 's'} "
                    f"traceable to a growth action, against "
                    f"₹{spent_paise / 100:,.2f} of margin committed, of "
                    f"which ₹{redeemed_paise / 100:,.2f} was actually taken.")

    return {
        "window_days": days,
        "actions_applied": len(offers),
        "margin_spent_paise": spent_paise,
        # SPENT is what was committed to live offers. REDEEMED is what a
        # customer actually took. They are different numbers and only the
        # second one is a discount on a sale — an offer nobody accepted
        # costs the merchant nothing, which is what the agents promise when
        # they propose one.
        "margin_redeemed_paise": redeemed_paise,
        "attributed_revenue_paise": attributed_paise,
        "conversions": converted,
        "headline": headline,
        # Said in the payload rather than only in the UI, because whichever
        # client renders this, the number is misleading without it.
        "caveat": (
            "Attributed, not incremental. Some of these customers would have "
            "paid without the offer, and separating them needs a holdout "
            "group this build has no traffic for. Margin committed and "
            "margin redeemed are both shown beside the revenue for that "
            "reason — an offer nobody took cost nothing, and the "
            "difference between any of these is not profit. No conversion "
            "rate is claimed from "
            f"{len(converted)} conversion{'' if len(converted) == 1 else 's'}."
        ),
    }


def redeemed_between(start_epoch: float, end_epoch: float,
                     lookback_days: int = 365) -> int:
    """
    Margin actually TAKEN by customers whose sale fell in this window.

    Analytics needs this for its Discounts row, and it needs it per window
    rather than for a fixed "last N days". The offer may have been applied
    long before the sale; what matters here is when the money moved, so
    conversions are filtered on `when` — the paid timestamp — rather than
    on when the offer was created.

    Returns 0 rather than raising: a Discounts row that cannot be computed
    should read as nothing given away, not take the whole dashboard down.
    """
    try:
        picture = build(days=lookback_days)
    except Exception as exc:
        print(f"[attribution] could not compute redeemed margin: {exc}",
              flush=True)
        return 0
    total = 0
    for conversion in picture.get("conversions") or []:
        when = conversion.get("when") or 0
        if start_epoch <= when <= end_epoch:
            total += int(conversion.get("cost_paise") or 0)
    return total
