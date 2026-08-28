"""
The main pipeline endpoint. Uses a WebSocket so the frontend's
"reasoning stream" panel can show each step as it actually happens,
not just a final result.
"""
import asyncio
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.ollama_agent import (
    parse_intent,
    rank_candidates,
    effective_priority,
    screen_relevance,
)
from app.agent.catalog import search_catalog
from app.agent.risk_gate import evaluate as risk_evaluate
from app.agent.trust_agent import assess as trust_assess
from app.agent.budget_agent import assess as budget_assess
from app.agent import settings
from app.agent import clarifier
from app.agent import refine as refiner
from app.agent.mandates import (
    allowed_venues,
    issue_intent_mandate,
    issue_cart_mandate,
    verify_chain,
    summarise as summarise_chain,
    digest as mandate_digest,
)
from app.firebase_client import (
    get_or_create_customer,
    log_decision,
    save_order,
    adjust_trust_score,
    log_market_scan,
    save_run,
)
from app.razorpay_client import create_order

router = APIRouter()

# conversation id -> what the last run found, so the next message can narrow
# it. In-process and short-lived on purpose: these are listings mid-decision,
# not a record. Anything that must survive is already in Firestore.
_LAST_RESULTS: dict[str, dict] = {}
_RESULTS_TTL_SECONDS = 1800

# conversation id -> the clarifying answers already given in this thread.
# Kept so a second search does not re-ask what was answered a minute ago.
_ANSWERS: dict[str, dict] = {}


def _remember(session_id, query, intent, candidates):
    if not session_id:
        return
    _LAST_RESULTS[session_id] = {
        "query": query, "intent": dict(intent),
        "candidates": candidates, "at": time.time(),
    }


def _recall(session_id):
    entry = _LAST_RESULTS.get(session_id) if session_id else None
    if not entry:
        return None
    if time.time() - entry["at"] > _RESULTS_TTL_SECONDS:
        _LAST_RESULTS.pop(session_id, None)
        return None
    return entry


@router.websocket("/ws/agent")
async def agent_pipeline(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        user_text = data["message"]
        session_id = data.get("session_id")
        customer_email = data.get("email", "demo@commerce-studio.dev")
        customer_name = data.get("name", "Demo User")

        # Resolved up front so both mandates carry the same subject — the
        # chain is worth less if the two halves name the person differently.
        customer = get_or_create_customer(customer_name, customer_email)

        # Start recording. Attached to the socket so the helpers below can
        # find it without every call site having to carry it.
        websocket._cp_run = {
            "id": f"run-{uuid.uuid4().hex[:16]}",
            "query": user_text,
            "customer_id": customer["id"],
            "t0": time.time(),
            "events": [],
        }

        # A follow-up to results already on screen narrows them; anything
        # naming a different product starts over. Which one happened is said
        # out loud, so a wrong guess is visible rather than silent.
        previous = _recall(session_id)
        decision = refiner.parse(user_text, previous["query"] if previous else "")
        refining = bool(previous and decision.get("refine"))

        await _agent(websocket, "intent", "running", tools=["ollama"])

        if refining:
            await _send(websocket, "step",
                        f'Refining the {len(previous["candidates"])} listings already found')
            intent = dict(previous["intent"])
            if decision["ops"].get("max_price_paise"):
                intent["max_price_paise"] = decision["ops"]["max_price_paise"]
            await _agent(websocket, "intent", "done", tools=[], summary=
                         f'{intent["category"]} · refined')
        else:
            await _send(websocket, "step", "Parsing intent into category, budget and priority")
            intent = parse_intent(user_text)
            await _agent(websocket, "intent", "done", tools=["ollama"], summary=
                         f"{intent['category']} · under ₹{intent['max_price_paise']/100:.0f} · by {intent['priority']}")

        # Sign the constraints BEFORE any listing is fetched, so the bounds
        # can't be quietly widened later to fit whatever the agent found.
        intent_jwt = issue_intent_mandate(intent, customer["id"])
        await _send(websocket, "mandate", {
            "stage": "intent",
            "hash": mandate_digest(intent_jwt),
            "constraints": {
                "max_amount_paise": intent["max_price_paise"],
                "category": intent["category"],
                "priority": intent["priority"],
            },
        })

        if refining:
            # These listings were searched, screened and asked about on the
            # turn that produced them. Doing any of it again would spend an
            # API call to re-fetch the same page and re-ask a question the
            # person has already answered.
            narrowed = refiner.apply(previous["candidates"], decision["ops"])
            candidates = narrowed["candidates"]
            quantity = 1
            await _agent(websocket, "scout", "done",
                         f'{len(candidates)} of the previous results kept', tools=[])
            await _send(websocket, "step", narrowed["summary"])
            if not candidates:
                await _send(websocket, "error",
                            "Nothing in the last results matches that — try relaxing it.")
                await websocket.close()
                return
        else:
            await _agent(websocket, "scout", "running", tools=["ebay"])

            # "Best X under N" and "cheapest X" want opposite ends of the same
            # result set, and eBay's default Best Match gives neither — it
            # favours cheap and popular, which is why a good-camera phone search
            # with a ₹20,000 budget came back full of ₹3,000 handsets from 2016.
            bias = (intent.get("quality_bias") or "neutral").lower()
            sort = {"best": "-price", "cheapest": "price"}.get(bias)
            budget = intent["max_price_paise"] / 100
            await _send(websocket, "step",
                         f"Matching catalog under ₹{budget:,.0f}" + {
                             "best": " — highest-value first, since you asked for the best",
                             "cheapest": " — lowest price first",
                         }.get(bias, ""))
            # Off the event loop, deliberately.
            #
            # This is a blocking network call inside an async handler, so running
            # it inline stalls the whole loop until eBay answers. That was merely
            # wasteful while every venue was external; it became a deadlock the
            # moment one of the venues was this same process. The merchant search
            # is an HTTP request back to our own server, and a blocked loop can
            # never serve it — discovery timed out every time, silently, and the
            # merchant's results just never appeared.
            candidates = await asyncio.to_thread(
                search_catalog, intent["category"], intent["max_price_paise"], sort,
                intent.get("requirements"),
            )

            if not candidates:
                await _agent(websocket, "scout", "blocked", "No listings matched", "error",
                             tools=["ebay"])
                await _send(websocket, "error", "No products matched — try relaxing your budget")
                await websocket.close()
                return

            await _agent(websocket, "scout", "done", f"{len(candidates)} live listings retrieved",
                         tools=["ebay"])

            # Trust runs before ranking so suspect listings never become the
            # recommendation in the first place.
            # Trust calls nothing — an explicit empty list, so the canvas draws it
            # with no tool edge instead of falling back to a declared dependency.
            await _agent(websocket, "trust", "running", tools=[])
            trust = trust_assess(candidates)
            candidates = trust["candidates"]
            await _agent(
                websocket, "trust",
                "warn" if trust["flagged"] else "done",
                trust["summary"],
                "warn" if trust["flagged"] else None,
                tools=[],
            )
            await _send(websocket, "step", trust["summary"])

            # Record what the market looked like, not just what got bought —
            # this is the only place real price and discount spread is visible.
            try:
                log_market_scan(intent["category"], candidates, trust["flagged"])
            except Exception as exc:
                # Analytics must never take down a purchase run.
                print(f"[market_scan] not recorded: {exc}")

            # Prefer listings that passed trust checks; fall back to the full
            # set only if every option was flagged. Turning "drop flagged" off
            # on the Trust node keeps them in the running — they still carry
            # their warning, so the choice stays informed rather than hidden.
            if settings.get("trust", "drop_flagged"):
                trusted = [c for c in candidates if c["trust"]["ok"]]
                if trusted:
                    candidates = trusted

            # ── Ask before spending ──────────────────────────────────────────
            # The agent has read one sentence and is about to commit money on
            # what it inferred from it. These questions are built from the
            # listings actually retrieved — the conditions present, the makers
            # that recur, the real price split — so every option offered is one
            # the result set can honour. Skipping leaves the results untouched.
            questions = clarifier.build(candidates, intent["category"])
            quantity = 1
            remembered = _ANSWERS.get(session_id) if session_id else None

            if remembered:
                # Already answered in this thread. Reapplying is not the same
                # as assuming — these are the person's own words from a
                # moment ago, and the step line says they were reused.
                refined = clarifier.apply(candidates, remembered)
                candidates = refined["candidates"]
                quantity = refined["quantity"]
                await _send(websocket, "step",
                            f"Carrying over what you told me earlier — {refined['summary']}")
            elif questions:
                await _send(websocket, "clarify", {
                    "questions": questions,
                    "candidate_count": len(candidates),
                })
                reply = await websocket.receive_json()
                answers = reply.get("answers") or {}
                if session_id and answers:
                    _ANSWERS[session_id] = answers
                refined = clarifier.apply(candidates, answers)
                candidates = refined["candidates"]
                quantity = refined["quantity"]
                await _send(websocket, "step", refined["summary"])
                if refined["applied"]:
                    await _agent(websocket, "value", "running", tools=[])

        # Show the top real candidates (with clickable links) before narrowing
        # to one — this is what the "top matching products" panel renders
        # Order the shown list by what the person actually asked for. This
        # used to sort by discount unconditionally, so the biggest markdown
        # led the carousel even when nobody mentioned discounts — which put
        # an 80%-off flip phone at the front of a camera-phone search.
        effective_sort = effective_priority(intent["priority"])
        sort_keys = {
            "discount": lambda p: (-(p.get("discount_percent") or 0), p["price_paise"]),
            "price": lambda p: (p["price_paise"],),
            "delivery_days": lambda p: (p.get("delivery_days") or 99, p["price_paise"]),
            # Seller feedback used to order this list, which is why a 100%
            # feedback flip phone led a camera-phone search. Feedback says
            # the seller is reliable; it says nothing about the product.
            "rating": lambda p: (-p["price_paise"],) if bias == "best" else (p["price_paise"],),
        }
        ranked = sorted(candidates, key=sort_keys.get(effective_sort, sort_keys["rating"]))
        top_candidates = ranked[:5]

        # Keep one slot for something the agent can actually buy.
        #
        # Ranking is venue-blind, which is right — but it means a purchasable
        # in-budget item can be pushed off the list by listings the agent can
        # only link to. A keyboard search did exactly that: two wrist rests
        # and a mouse pad outranked the one keyboard that could be paid for.
        # The merchant item is not moved to the front and its price is not
        # adjusted; it takes the last slot, and the card labels it as the
        # buyable one so the promotion is visible rather than smuggled in.
        if not any(c.get("source") == "merchant" for c in top_candidates):
            buyable = next((c for c in ranked if c.get("source") == "merchant"), None)
            if buyable:
                top_candidates = top_candidates[:4] + [buyable]
                await _send(
                    websocket, "step",
                    f"Holding a slot for {buyable.get('merchant_name') or 'the merchant'} — "
                    "the one result the agent can pay for directly",
                )

        # Kept so the next message can narrow these rather than starting a
        # fresh search. The whole screened set is stored, not just the five
        # shown, so "more options" has somewhere to draw from.
        _remember(session_id, user_text if not refining else previous["query"],
                  intent, candidates)

        await _send(websocket, "candidates", top_candidates)

        # Relevance: does the listing actually answer the request? Nothing
        # before this point reads the person's own words — Scout matches a
        # price ceiling, Trust looks at price and seller, and neither can
        # tell a camera phone from a ₹166 flip phone.
        await _agent(websocket, "value", "running", tools=["ollama"])
        await _send(websocket, "step", "Screening listings against what you asked for")
        screened = screen_relevance(candidates, user_text, intent.get("requirements"))
        candidates = screened["candidates"]
        await _send(websocket, "step", screened["summary"])
        # Announce the priority the ranker will really use, not the one that
        # was parsed — a pin on the Value node overrides the request wording,
        # and the stream should say so as it happens.
        effective = effective_priority(intent["priority"])
        pinned_note = " (pinned on the Value node)" if effective != intent["priority"] else ""
        await _send(websocket, "step",
                     f"Ranking {len(candidates)} candidates by {effective}{pinned_note}")
        result = rank_candidates(
            candidates,
            intent["priority"],
            user_text=user_text,
            requirements=intent.get("requirements"),
            budget_paise=intent.get("max_price_paise") or 0,
        )
        product = result["product"]
        summary = result["reason"]
        if effective != intent["priority"]:
            summary = f"{summary} (ranked by {effective}, pinned on the Value node)"
        await _agent(websocket, "value", "done", summary, tools=["ollama"])

        await _send(websocket, "match", {
            "product": product,
            "reason": result["reason"],
        })

        # Human-in-the-loop: the agent recommends, but the person chooses.
        # Nothing is charged until they pick — the frontend sends back
        # {"selected_product_id": "..."} from the product choice card.
        await _send(websocket, "await_selection", {
            "candidates": top_candidates,
            "recommended_id": product["id"],
            "reason": result["reason"],
        })

        selection = await websocket.receive_json()
        selected_id = selection.get("selected_product_id")
        if selected_id:
            chosen = next((c for c in top_candidates if str(c["id"]) == str(selected_id)), None)
            if chosen:
                product = chosen

        await _send(websocket, "step", f"Proceeding with {product['name']}")

        # Quantity was asked for, so it has to be charged for. Folding it into
        # the line's price here — before the cart mandate is issued — means
        # the risk bound, the signature and the Razorpay order all describe
        # the same total, exactly as a multi-item cart does. It also means a
        # quantity that breaks the budget fails the mandate chain rather than
        # quietly overspending, which is the chain doing its job.
        if quantity > 1:
            unit = product["price_paise"]
            product = {
                **product,
                "quantity": quantity,
                "unit_price_paise": unit,
                "price_paise": unit * quantity,
            }
            await _send(
                websocket, "step",
                f"{quantity} x Rs{unit / 100:,.0f} = Rs{product['price_paise'] / 100:,.0f}",
            )

        # The person has chosen; bind that exact cart to the intent that
        # authorised it. Price is captured here, at the moment of approval.
        cart = issue_cart_mandate(intent_jwt, product, customer["id"])
        await _send(websocket, "mandate", {
            "stage": "cart",
            "hash": mandate_digest(cart["cart_jwt"]),
            "checkout_hash": cart["checkout_hash"],
            "intent_hash": cart["intent_hash"],
            "total_paise": cart["total_paise"],
        })

        await _agent(websocket, "budget", "running", tools=["firestore"])
        budget = budget_assess(customer, product["price_paise"])
        await _agent(
            websocket, "budget",
            "blocked" if budget["status"] == "exceeded" else
            ("warn" if budget["status"] == "near_limit" else "done"),
            budget["summary"],
            "error" if budget["status"] == "exceeded" else
            ("warn" if budget["status"] == "near_limit" else None),
            tools=["firestore"],
        )
        await _send(websocket, "step", f"Budget: {budget['summary']}")

        if budget["status"] == "exceeded":
            log_decision(
                action_type="purchase_attempt",
                amount_paise=product["price_paise"],
                decision="blocked",
                reason=budget["summary"],
                customer_id=customer["id"],
            )
            await _send(websocket, "risk_gate", {"decision": "blocked", "reason": budget["summary"]})
            await websocket.close()
            return

        await _agent(websocket, "risk", "running", tools=["firestore"])
        await _send(websocket, "step", "Running risk check before order creation")
        risk_result = risk_evaluate(
            customer, product, allowed_venues=allowed_venues(intent_jwt)
        )

        log_decision(
            action_type="purchase_attempt",
            amount_paise=product["price_paise"],
            decision=risk_result["decision"],
            reason=risk_result["reason"],
            customer_id=customer["id"],
        )

        await _agent(
            websocket, "risk",
            "blocked" if risk_result["decision"] == "blocked" else
            ("warn" if risk_result["decision"] == "escalated" else "done"),
            risk_result["reason"],
            "error" if risk_result["decision"] == "blocked" else
            ("warn" if risk_result["decision"] == "escalated" else None),
            tools=["firestore"],
        )
        await _send(websocket, "risk_gate", risk_result)

        if risk_result["decision"] == "blocked":
            adjust_trust_score(customer["id"], -5)
            await websocket.close()
            return

        if risk_result["decision"] == "escalated":
            # Frontend shows a real Approve/Deny UI and sends back a decision
            approval = await websocket.receive_json()
            if not approval.get("approved"):
                await _send(websocket, "step", "Human denied the escalated purchase")
                await websocket.close()
                return

        # ── The last gate before money: verify the mandate chain ──────────
        # Everything above is procedural — this is the check that can prove
        # the order about to be created is the one the person authorised.
        # eBay prices are live, so "the price moved between approval and
        # checkout" is a real thing that happens, and it fails here.
        await _send(websocket, "step", "Verifying the signed mandate chain")
        chain = verify_chain(intent_jwt, cart["cart_jwt"], product)
        await _send(websocket, "mandate", {
            "stage": "verify",
            "ok": chain["ok"],
            "checks": chain["checks"],
            "reason": chain["reason"],
            "summary": summarise_chain(intent_jwt, cart["cart_jwt"]),
        })

        if not chain["ok"]:
            log_decision(
                action_type="mandate_rejected",
                amount_paise=product["price_paise"],
                decision="blocked",
                reason=f"{chain['failed_check']}: {chain['reason']}",
                customer_id=customer["id"],
            )
            await _agent(websocket, "payment", "blocked",
                         f"Mandate chain failed: {chain['failed_check']}", "error",
                         tools=[])
            await _send(websocket, "risk_gate", {
                "decision": "blocked",
                "reason": f"Mandate chain failed — {chain['reason']}",
            })
            await websocket.close()
            return

        await _agent(websocket, "payment", "running", tools=["razorpay", "firestore"])
        await _send(websocket, "step", "Creating Razorpay order")
        # Razorpay caps `receipt` at 56 chars, and live eBay item IDs are
        # long — so use a short hash of the product/customer pair plus a
        # timestamp, keeping it unique without risking the limit.
        receipt_id = f"cp-{uuid.uuid4().hex[:16]}"
        razorpay_order = create_order(
            amount_paise=product["price_paise"],
            receipt=receipt_id,
            notes={"customer_id": customer["id"], "product_id": str(product["id"])},
        )

        save_order(
            order_id=razorpay_order["receipt"],
            razorpay_order_id=razorpay_order["id"],
            amount_paise=product["price_paise"],
            product_name=product["name"],
            customer_id=customer["id"],
            product=product,
            mandates={
                "intent_jwt": intent_jwt,
                "cart_jwt": cart["cart_jwt"],
                "verified_at": int(time.time()),
            },
        )

        adjust_trust_score(customer["id"], 2)

        await _agent(websocket, "payment", "done",
                     f"Order {razorpay_order['id']} created",
                     tools=["razorpay", "firestore"])
        await _send(websocket, "order_created", {
            "razorpay_order_id": razorpay_order["id"],
            "amount_paise": product["price_paise"],
            "product_name": product["name"],
            "customer_id": customer["id"],
        })
        # Frontend now opens Razorpay Checkout.js with this order_id.
        # Payment confirmation arrives separately via the webhook route.

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        # Without this the socket just closes and the UI freezes with no
        # explanation. Report the failure so the person sees what broke.
        import traceback
        traceback.print_exc()
        try:
            await _send(websocket, "error", f"Agent run failed: {exc}")
            await websocket.close()
        except Exception:
            pass
    finally:
        # Every exit lands here — completed, blocked, errored, or the tab
        # simply closed — so a run is recorded however it ended. An
        # abandoned run is exactly the kind you want to replay later.
        _persist_run(websocket)


def _persist_run(ws: WebSocket) -> None:
    recorder = getattr(ws, "_cp_run", None)
    if not recorder or not recorder["events"]:
        return
    try:
        save_run(
            run_id=recorder["id"],
            query=recorder["query"],
            events=recorder["events"],
            outcome=_outcome(recorder["events"]),
            customer_id=recorder.get("customer_id"),
        )
    except Exception as exc:
        # Recording is never worth losing a run over.
        print(f"[run] not recorded: {exc}")


def _outcome(events: list[dict]) -> str:
    """How the run actually ended, read off its own event stream."""
    types = {e["type"] for e in events}
    if "order_created" in types:
        return "order_created"
    if "error" in types:
        return "error"
    for event in reversed(events):
        if event["type"] == "risk_gate" and event["payload"].get("decision") == "blocked":
            return "blocked"
    if "await_selection" in types:
        return "abandoned_at_selection"
    return "incomplete"


def _record(ws: WebSocket, event_type: str, payload) -> None:
    """
    Append to the run's recording.

    The recorder is attached to the websocket rather than threaded through
    every call site — there are two dozen of those, and passing a recorder
    into each would bury the pipeline's actual logic in plumbing.
    """
    recorder = getattr(ws, "_cp_run", None)
    if recorder is None:
        return
    recorder["events"].append({
        "type": event_type,
        "payload": payload,
        # Seconds since the run started, so a replay can honour the real
        # pacing — including how long the model actually took to think.
        "t": round(time.time() - recorder["t0"], 3),
    })


async def _send(ws: WebSocket, event_type: str, payload):
    _record(ws, event_type, payload)
    await ws.send_json({"type": event_type, "payload": payload})


async def _agent(ws: WebSocket, agent_id: str, status: str, summary: str = None,
                 tone: str = None, tools: list[str] = None):
    """
    Lifecycle event for one specialist agent. The hive canvas lights a node
    only when its agent actually runs, so these are emitted from the real
    call sites rather than a script.

    `tools` names the external services this agent genuinely touched on this
    run, so the canvas's tool tier lights from what happened rather than from
    a mapping the frontend guessed at. Trust passes an empty list on purpose:
    it calls nothing.
    """
    _record(ws, "agent", {
        "id": agent_id, "status": status, "summary": summary,
        "tone": tone, "tools": tools,
    })
    await ws.send_json({
        "type": "agent",
        "payload": {
            "id": agent_id,
            "status": status,
            "summary": summary,
            "tone": tone,
            "tools": tools,
        },
    })