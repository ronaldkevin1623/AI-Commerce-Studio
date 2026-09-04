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
                "agents": sorted({o.get("agent") or "" for o in by_session[session_id]}),
                "why": ("An offer was applied to this specific checkout "
                        "session, and this specific session then paid."),
            })
    except Exception as exc:
        print(f"[attribution] could not read checkouts: {exc}", flush=True)

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
                    f"₹{spent_paise / 100:,.2f} of margin given away.")

    return {
        "window_days": days,
        "actions_applied": len(offers),
        "margin_spent_paise": spent_paise,
        "attributed_revenue_paise": attributed_paise,
        "conversions": converted,
        "headline": headline,
        # Said in the payload rather than only in the UI, because whichever
        # client renders this, the number is misleading without it.
        "caveat": (
            "Attributed, not incremental. Some of these customers would have "
            "paid without the offer, and separating them needs a holdout "
            "group this build has no traffic for. Margin spent is shown "
            "beside the revenue for that reason: the difference is not "
            "profit, and no conversion rate is claimed from "
            f"{len(converted)} conversion{'' if len(converted) == 1 else 's'}."
        ),
    }
