"""
THE AUTONOMOUS RUN.

Prediction to order, with nobody asked. One function, `run_for`, because
the sequence is the point and splitting it across call sites would make it
possible to skip a step:

    what is due  →  find it on the market  →  screen it  →  rank it
                 →  autonomy gates  →  order  →  audit  →  notify

Two things about it are deliberately unlike the interactive path.

The screening is stricter, not looser. An unattended purchase gets the same
hard filters a person's search gets — accessories out, wrong condition out,
suspect listings out — and then the autonomy gates on top. Nothing is
relaxed because nobody is watching; the opposite.

And the capture is simulated, and says so everywhere it appears. Cards are
rejected on this Razorpay account and UPI is disabled, so the only rail
that completes is netbanking, which redirects to a bank login page a human
has to fill in. That makes genuinely unattended capture impossible here —
not hard, impossible. Everything up to the money is real: a real listing, a
real screen, real gates, a real Razorpay order. The capture is marked
`simulated: True`, written to the audit trail as a simulation, and the
notification says so. The alternative was a demo that quietly implies money
moved when it did not, which is the one thing this project will not do.
"""
import time
import uuid

from app.agent import (
    autonomy, ebay_client, precision, quality, replenishment, settings,
)
from app.agent.catalog import NO_CEILING, search_catalog, deduplicate
from app.agent.ollama_agent import query_terms
from app.engines import loop
from app.engines.recsys import SignalRecSys
from app.engines.understanding import PredictedNeed
from app.firebase_client import list_orders, log_decision, save_order

DAY = 86400.0

# How many candidates get the item-detail lookup that carries the
# precision signals. One call each, so this is the shortlist that could
# plausibly win rather than everything the search returned.
PRECISION_SHORTLIST = 8


def _notify(customer_id, title, body, kind, extra=None):
    """
    A notification is a record, not a popup.

    Written to the audit trail because that is the thing this project can
    prove. A push channel would be a second system to trust; the trail is
    already the one everything else is checked against.
    """
    log_decision(
        action_type="autonomous_notification",
        amount_paise=int((extra or {}).get("amount_paise") or 0),
        decision=kind,
        reason=f"{title} — {body}",
        customer_id=customer_id,
    )
    return {"title": title, "body": body, "kind": kind, **(extra or {})}


def _find_candidates(prediction):
    """
    The market, ranked, through the formal two-engine loop.

    This used to inline the screens. It now goes through app.engines, which
    changes nothing about what happens and everything about who is
    responsible for it: the prediction becomes a NeedSpec — a structure with
    no field able to name a product — the RecSys decides from measured
    signals, and the funnel comes back as data.

    The understanding engine here is the predicted one with the model
    switched off. An unattended run has nobody waiting on it, so it gains
    nothing from a slower reading, and fewer moving parts between a
    prediction and a purchase is the right trade when no one is watching.
    """
    phrase = prediction.get("name") or ""
    if not query_terms(phrase):
        return None, "The stored product name gives nothing to search for."

    def fetch(need):
        # NO_CEILING, not 0. Zero becomes an eBay filter of price:[..0.00]
        # and returns nothing, which reads as "this product does not exist"
        # when it means "nothing costs nothing". The real bound on an
        # unattended purchase is the per-order cap, applied by the gates.
        return deduplicate(search_catalog(
            need.category or phrase, NO_CEILING, None,
            need.requirements, need.condition_ids))

    result = loop.run(
        phrase, fetch,
        predicted={"explanation": replenishment.explain(prediction),
                   "cycle_days": prediction.get("cycle_days"),
                   "confidence": prediction.get("confidence")},
        understanding=PredictedNeed(),
        recsys=SignalRecSys(enrich=ebay_client.enrich_reviews,
                            shortlist=PRECISION_SHORTLIST),
    )

    ranked = result["ranked"]
    if not ranked["chosen"]:
        stages = "; ".join(f"{s['stage']} dropped {s['dropped']}"
                           for s in ranked["stages"] if s["dropped"])
        return None, (f"Nothing survived screening for “{phrase[:44]}”"
                      + (f" — {stages}" if stages else "."))
    return result, None


def run_for(customer_id: str, *, now: float = None, dry_run: bool = False,
            only_key: str = None) -> dict:
    """
    One autonomous pass for one customer.

    `dry_run` walks the whole sequence and stops before creating anything,
    which is how the tests and the preview both work — the decision path is
    identical, so a dry run that says "would buy" is evidence about the real
    one rather than a separate code path that might disagree.
    """
    now = now or time.time()
    orders = [o for o in list_orders(limit=200)
              if o.get("customer_id") == customer_id]

    lead = (settings.get("autonomy", "lead_days") or 0) * DAY
    predictions = replenishment.profile(orders, now)
    due = [p for p in predictions
           if p.get("predictable") and (p["due_at"] - lead) <= now
           and (not only_key or p["key"] == only_key)]

    actions = []
    for prediction in due:
        action = {"item": prediction["name"], "key": prediction["key"],
                  "why": replenishment.explain(prediction),
                  "confidence": prediction["confidence"]}

        engine_result, problem = _find_candidates(prediction)
        if problem:
            action.update(outcome="not_found", detail=problem)
            log_decision(
                action_type="autonomous_skipped",
                amount_paise=0, decision="blocked", reason=problem,
                customer_id=customer_id,
            )
            actions.append(action)
            continue

        ranked = engine_result["ranked"]
        candidates = ranked["candidates"]
        pick = ranked["chosen"]
        action["pick"] = {
            "id": pick.get("id"), "name": pick.get("name"),
            "price_paise": pick.get("price_paise"),
            "source": pick.get("source"), "condition": pick.get("condition"),
            "seller_feedback": pick.get("seller_feedback"),
            "quality": (pick.get("quality") or {}).get("score"),
        }
        action["considered"] = len(candidates)
        # Retail media, on the unattended path. Nobody is looking at a list
        # here, so an impression is not a thing that happened — the only
        # placement worth charging for is a promoted product the agent
        # actually settled on, and only after the gates let the purchase
        # through. Charging for the shortlist of a run no human sees would
        # be selling the merchant an audience of one machine.
        action["sponsored"] = bool(pick.get("sponsored"))

        gate = autonomy.check(customer_id=customer_id, product=pick,
                              prediction=prediction, now=now)
        action["gates"] = gate["checks"]

        if gate["verdict"] != autonomy.ALLOWED:
            action.update(outcome=gate["verdict"], detail=gate["reason"])
            log_decision(
                action_type=("autonomous_needs_confirmation"
                             if gate["verdict"] == autonomy.CONFIRM
                             else "autonomous_blocked"),
                amount_paise=gate["amount_paise"], decision="blocked",
                reason=f"{prediction['name']}: {gate['reason']}",
                customer_id=customer_id,
            )
            action["notification"] = _notify(
                customer_id,
                ("Needs your say-so" if gate["verdict"] == autonomy.CONFIRM
                 else "Did not buy"),
                gate["reason"], gate["verdict"],
                {"amount_paise": gate["amount_paise"]})
            actions.append(action)
            continue

        if dry_run:
            action.update(outcome="would_buy",
                          detail="Dry run — every gate passed and nothing was created.")
            actions.append(action)
            continue

        # ── The purchase ────────────────────────────────────────────────
        #
        # The order record is real and the reasoning is stored with it. The
        # capture is not, and every field here says so.
        order_id = f"auto-{uuid.uuid4().hex[:12]}"
        reasoning = {
            "trigger": replenishment.explain(prediction),
            "cycle_days": prediction.get("cycle_days"),
            "intervals_seen": prediction.get("intervals_seen"),
            "confidence": prediction.get("confidence"),
            "considered": len(candidates),
            "chosen_because": ranked["basis"],
            "signals": ranked["signals"],
            # The funnel, as data: how many the market offered and what each
            # screen removed. An explanation of a purchase nobody watched
            # should be checkable, not merely readable.
            "funnel": ranked["stages"],
            "engines": engine_result["engines"],
            "need": engine_result["need"],
            "explanation": engine_result["explanation"]["text"],
            "gates": gate["checks"],
        }
        save_order(
            order_id=order_id,
            razorpay_order_id=f"simulated_{order_id}",
            amount_paise=pick["price_paise"],
            product_name=pick.get("name"),
            customer_id=customer_id,
            status="simulated_paid",
            product=pick,
            mandates={"autonomous_reasoning": reasoning},
        )
        log_decision(
            action_type="autonomous_purchase",
            amount_paise=pick["price_paise"],
            decision="allowed",
            reason=(f"Bought {pick.get('name')} unattended. "
                    f"{replenishment.explain(prediction)} "
                    f"Chosen from {len(candidates)} screened listings. "
                    f"CAPTURE SIMULATED — netbanking is the only rail this "
                    f"Razorpay account can complete and it needs a human at "
                    f"the bank page, so no money moved."),
            customer_id=customer_id,
            order_id=order_id,
        )
        action.update(
            outcome="bought",
            order_id=order_id,
            simulated=True,
            reasoning=reasoning,
            detail=("Ordered without asking. The capture is simulated — see "
                    "the audit trail entry."),
        )
        if pick.get("sponsored"):
            from app.merchant import promotions
            action["placement"] = promotions.settle_placements(
                [pick], chosen_id=pick.get("id"), customer_id=customer_id)

        action["notification"] = _notify(
            customer_id, "Bought while you were away",
            f"{pick.get('name')} at ₹{pick['price_paise'] / 100:,.0f}"
            + (" (a promoted listing, ranked here on its own signals)"
               if pick.get("sponsored") else "") + ". "
            f"{replenishment.explain(prediction)} Capture simulated.",
            "bought", {"amount_paise": pick["price_paise"]})
        actions.append(action)

    return {
        "customer_id": customer_id,
        "ran_at": now,
        "dry_run": dry_run,
        "tracked": len([p for p in predictions if p.get("predictable")]),
        "due": len(due),
        "actions": actions,
        "capture": "simulated",
    }
