"""
REACTIVATION: THE CUSTOMERS WHO STOPPED COMING BACK.

Cart recovery catches someone mid-checkout. This catches the slower loss —
a customer who bought once and never returned. It is the same shape of
action (spend a little margin to move someone), aimed at a different moment,
so it gets the same gate and the same evidence floor.

WHY "LAPSED" IS DEFINED FROM THE DATA AND NOT PICKED

A fixed 90-day rule is meaningless on a shop that is four days old:
everybody is inside it, the agent finds nobody, and the merchant concludes
the feature is broken. A fixed 2-day rule on a real shop would call half its
customers lapsed and hand out margin to people who were coming back anyway.

So the threshold is derived: a customer is lapsed once they have gone
noticeably longer than their own normal gap between orders. With one order
there is no gap to compare against — no repeat purchase means no interval,
and no interval means no evidence of a rhythm being broken. Those customers
are counted and reported separately as `single_purchase`, never proposed
against. "They bought once and haven't come back" is a description of most
customers of most shops, not a signal.

WHAT THIS AGENT CANNOT DO

Contact anybody. There is no email or SMS rail in this project and inventing
one would be the fakery this build refuses. Like cart recovery, it makes
returning worth more — a standing offer against that customer's next order —
and says plainly that the customer will only see it if they come back on
their own.
"""
import statistics
import time

from app.growth.base import Proposal

AGENT_ID = "reactivation"

# A customer is lapsed once the silence is this multiple of their own median
# gap. 1.5 rather than 2 because at 2 the offer arrives long after the
# customer has already gone somewhere else; rather than 1.2 because ordinary
# variation in when people shop should not read as churn.
LAPSE_MULTIPLE = 1.5

# Below this the silence is too short to mean anything regardless of what the
# customer's own rhythm suggests — it stops a customer who buys twice in one
# afternoon being called lapsed by the evening.
FLOOR_SECONDS = 24 * 60 * 60

# What the win-back is worth. Held well under the growth gate's ceiling so
# the gate stays the binding constraint rather than this constant.
WIN_BACK_PCT = 10


def _epoch(value) -> float:
    """Firestore hands back several time shapes depending on the writer."""
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


class ReactivationAgent:
    agent_id = AGENT_ID
    name = "Wins back customers who stopped"
    what = ("Finds customers who have gone significantly longer than their "
            "own usual gap without ordering, and proposes a standing "
            "win-back offer on their next order. Customers with only one "
            "order are counted but never proposed against — one purchase is "
            "not a rhythm that can be broken.")
    spends_margin = True

    def detect(self) -> list[dict]:
        """Order history per customer, from both halves of the shop."""
        try:
            from app.firebase_client import db
        except Exception as exc:
            print(f"[growth] reactivation could not reach the datastore: {exc}",
                  flush=True)
            return []

        history: dict = {}

        def note(customer_id, when, amount):
            if not customer_id or not when:
                return
            history.setdefault(str(customer_id), []).append(
                {"at": when, "amount_paise": int(amount or 0)})

        try:
            for doc in db.collection("orders").stream():
                row = doc.to_dict() or {}
                # Only orders that actually completed. An abandoned run is
                # cart recovery's business, and counting it here would treat
                # someone who never bought as a customer who left.
                if not str(row.get("status") or "").endswith("paid"):
                    continue
                note(row.get("customer_id"), _epoch(row.get("created_at")),
                     row.get("amount_paise"))
        except Exception as exc:
            print(f"[growth] reactivation could not read orders: {exc}", flush=True)

        try:
            from app.merchant import store
            for doc in store.db.collection(store.SESSIONS).stream():
                row = doc.to_dict() or {}
                if (row.get("status") or "") != "paid":
                    continue
                buyer = row.get("buyer") or {}
                note(buyer.get("customer_id") or buyer.get("email"),
                     _epoch(row.get("created_at")), row.get("total_paise"))
        except Exception as exc:
            print(f"[growth] reactivation could not read checkouts: {exc}",
                  flush=True)

        now = time.time()
        signals = []
        single_purchase = 0
        for customer_id, orders in history.items():
            orders.sort(key=lambda o: o["at"])
            if len(orders) < 2:
                single_purchase += 1
                continue

            gaps = [b["at"] - a["at"] for a, b in zip(orders, orders[1:])]
            gaps = [g for g in gaps if g > 0]
            if not gaps:
                single_purchase += 1
                continue

            typical = statistics.median(gaps)
            silence = now - orders[-1]["at"]
            threshold = max(typical * LAPSE_MULTIPLE, FLOOR_SECONDS)
            if silence < threshold:
                continue

            signals.append({
                "customer_id": customer_id,
                "orders": len(orders),
                "intervals": len(gaps),
                "typical_gap_seconds": int(typical),
                "silent_seconds": int(silence),
                "threshold_seconds": int(threshold),
                "lifetime_paise": sum(o["amount_paise"] for o in orders),
                "last_order_paise": orders[-1]["amount_paise"],
            })

        signals.sort(key=lambda s: -s["lifetime_paise"])
        # Carried on the first signal so the proposal can report the shape of
        # the whole cohort rather than only the customer it names.
        if signals:
            signals[0]["_cohort"] = {
                "customers_with_history": len(history),
                "single_purchase": single_purchase,
                "lapsed": len(signals),
            }
        elif history:
            print(f"[growth] reactivation: {len(history)} customer(s), "
                  f"{single_purchase} with a single order, none lapsed",
                  flush=True)
        return signals

    def propose(self, signals: list[dict]) -> list[Proposal]:
        proposals = []
        for signal in signals:
            # Sized against what this customer actually spends, so the offer
            # is proportionate to the relationship rather than a flat number
            # that is generous to one customer and insulting to another.
            typical_order = signal["lifetime_paise"] // max(signal["orders"], 1)
            cost = int(typical_order * WIN_BACK_PCT / 100)

            days_silent = signal["silent_seconds"] / 86400
            usual_days = signal["typical_gap_seconds"] / 86400
            # A gap of forty minutes rendered as "0.0 days" reads as a bug
            # and hides the very number the claim rests on. Below a day the
            # unit changes rather than the precision.
            usual_text = (f"{usual_days:.1f} days" if usual_days >= 1
                          else f"{signal['typical_gap_seconds'] / 3600:.1f} hours")
            silent_text = (f"{days_silent:.1f} days" if days_silent >= 1
                           else f"{signal['silent_seconds'] / 3600:.1f} hours")

            # WHICH RULE ACTUALLY DECIDED THIS.
            #
            # The threshold is the customer's own median gap times 1.5, or a
            # 24-hour floor, whichever is larger. When their orders sit close
            # together — a history written in one batch, or three purchases in
            # one afternoon — the median is near zero and the FLOOR is doing
            # all the work. Reporting "usually about 0.0 hours apart" in that
            # case quotes a real number in support of a claim it cannot carry.
            # The proposal says which one bound it instead.
            floor_decided = signal["typical_gap_seconds"] * LAPSE_MULTIPLE < FLOOR_SECONDS
            if floor_decided:
                basis_text = (
                    f"Their orders sit about {usual_text} apart, which is too "
                    f"close together to read as a rhythm — so the "
                    f"{FLOOR_SECONDS // 3600}-hour floor decided this, not "
                    f"their own pattern. Weaker evidence than it looks."
                )
            else:
                basis_text = (
                    f"They usually order about {usual_text} apart, so this "
                    f"silence is past what their own pattern would predict."
                )

            proposals.append(Proposal(
                agent=AGENT_ID,
                kind="reactivate_customer",
                headline=(f"{WIN_BACK_PCT}% off the next order for a customer "
                          f"silent {silent_text}"),
                detail=(
                    f"This customer placed {signal['orders']} orders and has "
                    f"now gone {silent_text} without one, past the "
                    f"{signal['threshold_seconds'] / 86400:.1f}-day mark. "
                    f"{basis_text} Lifetime spend "
                    f"₹{signal['lifetime_paise'] / 100:,.2f}. The offer would "
                    f"cost about ₹{cost / 100:,.2f} of margin against a typical "
                    f"order of ₹{typical_order / 100:,.2f}. Nothing is sent: "
                    f"there is no email or SMS rail here, so this waits on the "
                    f"customer's next visit rather than chasing them."
                ),
                cost_paise=cost,
                target_kind="customer",
                target_id=signal["customer_id"],
                # The intervals, not the orders. Three orders give two gaps,
                # and it is the gaps that carry the claim about a rhythm.
                sample_size=signal["intervals"],
                evidence_note=(
                    f"Based on {signal['intervals']} interval"
                    f"{'' if signal['intervals'] == 1 else 's'} between this "
                    f"customer's own orders. A median from "
                    f"{signal['intervals']} gap"
                    f"{'' if signal['intervals'] == 1 else 's'} is a weak "
                    f"estimate of anyone's shopping rhythm."
                ),
                params={
                    "discount_pct": WIN_BACK_PCT,
                    "customer_id": signal["customer_id"],
                    "silent_days": round(days_silent, 1),
                    "typical_gap_days": round(usual_days, 2),
                    "decided_by": "floor" if floor_decided else "own_rhythm",
                    "orders": signal["orders"],
                    "cohort": signal.get("_cohort"),
                    "delivery": "none — no email or SMS rail exists in this build",
                },
            ))
        return proposals
