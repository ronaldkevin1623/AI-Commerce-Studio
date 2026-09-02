"""
THE LEVEL 5 SURFACE.

What is being tracked, what is due, what the agent would do about it, and
what it actually did. Plus the two things a demo needs: a way to run the
cycle now instead of waiting a fortnight, and a way to move the clock.

The clock is a parameter, not a global. `run_for(now=...)` takes the moment
to reason about, so "what would happen in 30 days" is answered by passing a
future timestamp rather than by mutating time for the whole process. That
keeps the simulated run and the real one the same code — a demo mode that
forked the logic would be demonstrating the demo, not the product.
"""
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent import autonomy, replenishment, settings
from app.agent.replenish_runner import run_for
from app.firebase_client import (
    db, get_or_create_customer, list_decisions, list_orders,
    log_decision, save_order,
)

router = APIRouter()

DAY = 86400.0

# The audit-trail rows that are an autonomous agent acting, as opposed to a
# person acting. Kept here so the history endpoint and the interface agree
# about what counts.
AUTONOMOUS_ACTIONS = {
    "autonomous_purchase", "autonomous_blocked",
    "autonomous_needs_confirmation", "autonomous_skipped",
    "autonomous_notification",
}


class RunRequest(BaseModel):
    customer_email: str = "demo@commerce-studio.dev"
    customer_name: str = "Demo User"
    # Days to move the clock forward for this run only. The demo's way of
    # standing three weeks in the future without waiting three weeks.
    days_ahead: int = 0
    dry_run: bool = True
    only_key: str | None = None


def _customer(req: RunRequest):
    return get_or_create_customer(req.customer_name, req.customer_email)


@router.get("/autonomy/status")
def status(customer_email: str = "demo@commerce-studio.dev"):
    """What the agent is allowed to do, and what it is watching."""
    customer = get_or_create_customer("Demo User", customer_email)
    orders = [o for o in list_orders(limit=200)
              if o.get("customer_id") == customer["id"]]
    predictions = replenishment.profile(orders)

    return {
        "enabled": autonomy.enabled(),
        "bounds": {
            "per_order_inr": settings.get("autonomy", "max_order_inr"),
            "monthly_inr": settings.get("autonomy", "monthly_cap_inr"),
            "confidence_floor_pct": settings.get("autonomy", "min_confidence_pct"),
            "lead_days": settings.get("autonomy", "lead_days"),
        },
        "spent_30d_paise": autonomy._spent_recently(customer["id"], time.time()),
        "tracked": [
            {**p, "explanation": replenishment.explain(p)} for p in predictions
        ],
        "paid_orders": sum(1 for o in orders if o.get("status") in
                           ("paid", "simulated_paid")),
        "capture": "simulated",
        "capture_note": (
            "Cards are rejected on this Razorpay account and UPI is disabled, "
            "so the only rail that completes is netbanking — which needs a "
            "person at their bank's login page. Unattended capture is "
            "therefore impossible here, and every autonomous order says so "
            "rather than implying money moved."
        ),
    }


@router.post("/autonomy/run")
def run(req: RunRequest):
    """
    Run the replenishment cycle now.

    Defaults to a dry run. Buying is something a caller asks for explicitly,
    which is the same principle as the kill switch defaulting to off.
    """
    customer = _customer(req)
    now = time.time() + max(0, req.days_ahead) * DAY
    result = run_for(customer["id"], now=now, dry_run=req.dry_run,
                     only_key=req.only_key)
    return {
        **result,
        "days_ahead": req.days_ahead,
        "simulated_clock": req.days_ahead > 0,
        "as_of": now,
    }


@router.get("/autonomy/history")
def history(limit: int = 60):
    """
    Every action the agent took without being asked.

    The autonomy audit trail the trust argument rests on: with consumer
    trust in AI recommendations at under half, the demonstrable record of
    what was done unattended is the differentiator, not the automation.
    """
    rows = [r for r in list_decisions(limit=400)
            if r.get("action_type") in AUTONOMOUS_ACTIONS]
    out = []
    for row in rows[:limit]:
        when = row.get("at") or row.get("created_at")
        stamp = when if isinstance(when, (int, float)) else getattr(
            when, "timestamp", lambda: None)()
        out.append({
            "action": row.get("action_type"),
            "decision": row.get("decision"),
            "reason": row.get("reason"),
            "amount_paise": row.get("amount_paise"),
            "order_id": row.get("order_id"),
            "at": stamp,
        })
    return {"count": len(out), "actions": out}


class Seed(BaseModel):
    customer_email: str = "demo@commerce-studio.dev"
    customer_name: str = "Demo User"
    product: str = "Nescafe Gold Instant Coffee Refill 200g"
    cycle_days: int = 30
    purchases: int = 4
    price_paise: int = 49900


@router.post("/autonomy/demo/seed")
def seed(body: Seed):
    """
    Purchase history for a product nobody actually bought.

    This is synthetic, and it is the only synthetic thing in the Level 5
    path. Predicting a reorder cycle needs a history of reorders, and this
    project has three real captures across three different products — no
    repeat purchases at all, so nothing to learn a cycle from.

    Every row it writes is stamped `demo_seeded: True` and dated backwards
    from now on the requested cycle, so the model reads them exactly as it
    would read real ones. The flag is what keeps it honest: the status
    endpoint counts them separately, and /autonomy/demo/clear removes them.
    Nothing downstream treats a seeded order as evidence of anything except
    that a demo was set up.
    """
    customer = get_or_create_customer(body.customer_name, body.customer_email)
    if body.purchases < 2:
        raise HTTPException(
            status_code=400,
            detail="Two purchases is the minimum that produces an interval.")

    created = []
    for index in range(body.purchases):
        # Newest last, spaced by the cycle, with the most recent one placed
        # a full cycle back so the item reads as due right now.
        days_ago = body.cycle_days * (body.purchases - 1 - index) + body.cycle_days
        order_id = f"demo-{uuid.uuid4().hex[:10]}"
        save_order(
            order_id=order_id,
            razorpay_order_id=f"demo_{order_id}",
            amount_paise=body.price_paise,
            product_name=body.product,
            customer_id=customer["id"],
            # Not "paid". A seeded order has no Razorpay payment behind it,
            # and the integrity audit exists to catch exactly that — an
            # order claiming to be paid with nothing to prove it. Its own
            # status keeps the guarantee intact and keeps demo rows out of
            # revenue.
            status="demo_paid",
            product={"id": f"demo-{index}", "name": body.product,
                     "price_paise": body.price_paise, "source": "demo"},
        )
        _stamp_demo(order_id, time.time() - days_ago * DAY)
        created.append({"order_id": order_id, "days_ago": days_ago})

    log_decision(
        action_type="autonomy_demo_seeded",
        amount_paise=body.price_paise * body.purchases,
        decision="allowed",
        reason=(f"Seeded {body.purchases} synthetic purchases of "
                f"{body.product} on a {body.cycle_days}-day cycle, so the "
                f"replenishment model has a history to read. Not real orders."),
        customer_id=customer["id"],
    )
    return {"seeded": created, "product": body.product,
            "cycle_days": body.cycle_days, "synthetic": True,
            "note": "Marked demo_seeded. Remove with /autonomy/demo/clear."}


@router.post("/autonomy/demo/clear")
def clear_demo(customer_email: str = "demo@commerce-studio.dev"):
    """Remove every seeded order, so the demo leaves nothing behind."""
    customer = get_or_create_customer("Demo User", customer_email)
    removed = 0
    for row in list_orders(limit=400):
        if row.get("demo_seeded") and row.get("customer_id") == customer["id"]:
            db.collection("orders").document(row["id"]).delete()
            removed += 1
    return {"removed": removed}


def _stamp_demo(order_id: str, when: float):
    """
    Backdate a seeded order and flag it.

    save_order stamps created_at server-side, which is right for a real
    order and useless for one that is meant to look three months old.
    """
    db.collection("orders").document(order_id).update({
        "created_at": when,
        "demo_seeded": True,
    })


class Toggle(BaseModel):
    enabled: bool


@router.post("/autonomy/kill-switch")
def kill_switch(body: Toggle):
    """
    Turn autonomous buying on or off.

    Its own endpoint rather than a settings patch, because this is the one
    control somebody reaches for in a hurry, and it is written to the audit
    trail as a financial bound movement like every other.
    """
    changes = settings.apply({"autonomy": {"enabled": bool(body.enabled)}})
    return {"enabled": autonomy.enabled(), "changed": changes}
