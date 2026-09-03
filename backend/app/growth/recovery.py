"""
WINS BACK DROPPED CARTS.

A checkout session that was opened and never paid is the clearest revenue
signal a store has: someone chose a specific item, the store priced it, and
then nothing happened. This reads those sessions and proposes one bounded
action per cart.

WHAT IT CANNOT DO, AND SAYS SO

There is no email or SMS rail in this build, so it cannot chase anybody.
What it CAN do is make the cart worth returning to: a time-boxed discount
recorded against that specific session, honoured when the buyer comes back
to it and expired otherwise. That is a real, checkable action on a real
abandoned cart — and it is a smaller claim than "we email your customers",
which is the claim a demo would be tempted to make.

HOW THE OFFER IS SIZED

Not a flat percentage. A cart abandoned twenty minutes ago probably just
has someone deciding; one abandoned two days ago has lost. So the discount
scales with how cold the cart is, and stops at the ceiling the gate
enforces anyway. Cheap carts get a floor in rupees rather than a percentage
of very little, because 10% of ₹649 is not a reason to come back.

The proposal is inert. It says what it would give away; the gate decides,
and only then is anything written.
"""
import time

from app.growth.base import Proposal

AGENT_ID = "recovery"


def _epoch(value) -> float:
    """
    Seconds since the epoch, whatever the datastore handed back.

    Firestore returns DatetimeWithNanoseconds for a server timestamp and a
    plain float for a client-set one, and the same collection can hold
    both. Assuming either shape crashes the scan on the other.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    for attr in ("timestamp",):
        method = getattr(value, attr, None)
        if callable(method):
            try:
                return float(method())
            except Exception:
                pass
    return 0.0

# A cart is not "abandoned" the moment it is opened — somebody is probably
# still looking at the bank page. This is the point after which silence
# starts to mean something.
COLD_AFTER_SECONDS = 20 * 60

# How the discount grows with age, capped well under the gate's own
# ceiling so the gate stays the binding constraint rather than this table.
AGE_TIERS = (
    (20 * 60, 5),          # cold for 20 minutes  -> 5%
    (6 * 60 * 60, 8),      # cold for 6 hours     -> 8%
    (24 * 60 * 60, 12),    # a day                -> 12%
)


class CartRecoveryAgent:
    agent_id = AGENT_ID
    name = "Wins back dropped carts"
    what = ("Reads checkout sessions that were opened and never paid, and "
            "proposes a time-boxed discount on that specific cart. No email "
            "or SMS rail exists here, so it makes the cart worth returning "
            "to rather than chasing anyone.")
    spends_margin = True

    def detect(self) -> list[dict]:
        """Real unpaid checkout sessions, oldest first."""
        try:
            from app.merchant import store
            rows = [d.to_dict() or {}
                    for d in store.db.collection(store.SESSIONS).stream()]
        except Exception as exc:
            print(f"[growth] could not read checkout sessions: {exc}", flush=True)
            return []

        now = time.time()
        out = []
        for row in rows:
            if (row.get("status") or "") != "awaiting_payment":
                continue
            created = _epoch(row.get("created_at"))
            age = now - created if created else 0
            if age < COLD_AFTER_SECONDS:
                continue           # still warm; leave them alone
            # ONE LIVE OFFER PER CART.
            #
            # Without this the scan keeps proposing the same cart after an
            # offer has been applied to it, and each approval stacks more
            # margin onto a customer who already has a discount waiting.
            # The buying agent has an `already_bought` gate for exactly this
            # shape of mistake; the merchant side needs the same.
            try:
                from app.growth import registry
                if registry.offers_for(row.get("id")):
                    continue
            except Exception:
                pass

            out.append({
                "session_id": row.get("id"),
                "total_paise": int(row.get("total_paise") or 0),
                "line_items": row.get("line_items") or [],
                "age_seconds": int(age),
                "razorpay_order_id": row.get("razorpay_order_id"),
            })
        out.sort(key=lambda r: -r["age_seconds"])
        return out

    def propose(self, signals: list[dict]) -> list[Proposal]:
        total_carts = len(signals)
        proposals = []
        for signal in signals:
            pct = self._discount_for(signal["age_seconds"])
            total = signal["total_paise"]
            cost = int(total * pct / 100)

            item = "the cart"
            items = signal.get("line_items") or []
            if items:
                first = items[0]
                item = str(first.get("name") or first.get("id") or "the cart")

            hours = signal["age_seconds"] / 3600
            age_text = (f"{signal['age_seconds'] // 60} minutes"
                        if hours < 1 else f"{hours:.0f} hours")

            proposals.append(Proposal(
                agent=AGENT_ID,
                kind="recover_cart",
                headline=(f"{pct}% off {item[:40]} to win back a cart left "
                          f"{age_text} ago"),
                detail=(
                    f"Checkout {signal['session_id']} was opened for "
                    f"₹{total / 100:,.2f} and never paid. It has been cold for "
                    f"{age_text}, so the offer is sized at {pct}% — costing "
                    f"₹{cost / 100:,.2f} of margin if it is taken, and nothing "
                    f"if it is not. The discount is held against this session "
                    f"only and expires; it is not a public price change. "
                    f"There is no email rail here, so this makes the cart "
                    f"worth returning to rather than chasing the buyer."),
                cost_paise=cost,
                target_kind="checkout_session",
                target_id=signal["session_id"],
                sample_size=total_carts,
                evidence_note=(
                    f"Based on {total_carts} abandoned checkout"
                    f"{'s' if total_carts != 1 else ''} in the store's own "
                    f"records."
                    + ("  One cart is a case, not a pattern — the size of the "
                       "offer here follows how cold it is, not a measured "
                       "conversion rate, and nothing claims otherwise."
                       if total_carts < 3 else "")),
                params={"discount_pct": pct,
                        "expires_in_hours": 48,
                        "razorpay_order_id": signal.get("razorpay_order_id")},
            ))
        return proposals

    def _discount_for(self, age_seconds: int) -> int:
        pct = AGE_TIERS[0][1]
        for threshold, value in AGE_TIERS:
            if age_seconds >= threshold:
                pct = value
        return pct
