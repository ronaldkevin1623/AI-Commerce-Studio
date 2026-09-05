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
    fast_intent,
    merge_model_intent,
    rank_candidates,
    effective_priority,
    screen_relevance,
    condition_preference,
    condition_conflict,
)
from app.agent.catalog import search_catalog, deduplicate
from app.agent.risk_gate import evaluate as risk_evaluate
from app.agent.trust_agent import assess as trust_assess
from app.agent.budget_agent import assess as budget_assess
from app.agent import settings
from app.agent import refine as refiner
from app.agent import router as turn_router
from app.agent import answer as answerer
from app.agent import preferences
from app.agent import quality
from app.agent import precision
from app.merchant import promotions

# How many ranked results the carousel receives. Was an implicit five, which
# contradicted the sentence above it saying two dozen were found. High enough
# that a screened set is shown whole in practice, bounded so a pathological
# search cannot flood the socket.
SHOWN_LIMIT = 40


def _without_budget(query: str) -> str:
    """
    Strip a price ceiling out of a query so a new one can be appended.

    The stand-down notice suggests re-asking with a lower budget, built as
    "<original query> under <new figure>". The original already carried its
    own ceiling, so the suggestion came out as "wireless earbuds under 2000
    under 500" — two budgets in one sentence, which is not a query anybody
    should be told to type. Advice printed in the product has to be advice
    that works.
    """
    import re as _re
    cleaned = _re.sub(
        r"\s*\b(?:under|below|within|upto|up\s+to|less\s+than)\b\s*"
        r"(?:₹|rs\.?|inr)?\s*[\d,]+\s*(?:k|thousand)?\b",
        # A space, not an empty string: the pattern eats the whitespace on
        # both sides, so removing a clause from the middle would weld the
        # words either side of it together.
        " ", query or "", flags=_re.I)
    return " ".join(cleaned.split()).strip(" ,-") or (query or "").strip()


from app.adapters import sponsored_adapter
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
from app.agent import merchant_client
from app.firebase_client import db

router = APIRouter()

# conversation id -> what the last run found, so the next message can narrow
# it. In-process and short-lived on purpose: these are listings mid-decision,
# not a record. Anything that must survive is already in Firestore.
_LAST_RESULTS: dict[str, dict] = {}
_RESULTS_TTL_SECONDS = 1800

# conversation id -> the clarifying answers already given in this thread.
# Kept so a second search does not re-ask what was answered a minute ago.


def _remember(session_id, query, intent, candidates):
    if not session_id:
        return
    _LAST_RESULTS[session_id] = {
        "query": query, "intent": dict(intent),
        "candidates": candidates, "at": time.time(),
    }


def _remember_reason(session_id, reason):
    """
    Why this turn's pick won, kept for the next message to quote.

    Stored separately because it is computed after the listings are — the
    ranker needs the screened set before it can justify a choice — and
    because "why did you pick that one" deserves the sentence the agent
    actually gave rather than one reconstructed afterwards.
    """
    entry = _LAST_RESULTS.get(session_id) if session_id else None
    if entry:
        entry["pick_reason"] = reason


def _recall(session_id):
    entry = _LAST_RESULTS.get(session_id) if session_id else None
    if not entry:
        return None
    if time.time() - entry["at"] > _RESULTS_TTL_SECONDS:
        _LAST_RESULTS.pop(session_id, None)
        return None
    return entry



# How long the run will wait for the intent model once its answer is due.
#
# It has already had the whole catalogue fetch to work in, so this is a
# backstop rather than a budget. Set because parse_intent("santhosh") ran
# past two minutes — a bare name gives the model nothing to parse and it
# keeps generating — and an unbounded await turned that into a console that
# sat on "Matching catalog" forever.
INTENT_MODEL_GRACE_SECONDS = 8


async def _await_intent(task):
    """
    The model's reading of the request, or None if it could not supply one.

    Losing it costs the run the model's priority and its fuller requirements.
    It must never cost the run itself: the rule-derived intent is complete on
    its own, which is why it is derived.
    """
    if task is None:
        return None
    try:
        return await asyncio.wait_for(
            asyncio.shield(task), timeout=INTENT_MODEL_GRACE_SECONDS)
    except asyncio.TimeoutError:
        task.cancel()
        print(f"[agent] intent model did not answer within "
              f"{INTENT_MODEL_GRACE_SECONDS}s — continuing on rules", flush=True)
        return None
    except Exception as exc:
        print(f"[agent] intent model call failed, continuing on rules: {exc}",
              flush=True)
        return None

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

        # What kind of message is this? Narrowing, a question about what is
        # on screen, a new search, or none of those. This used to be a
        # two-way fork — narrow it or search for it — which meant every
        # question became a search: "why did you pick that one" went to eBay
        # as a query. Which route was taken is said out loud, so a wrong
        # turn is visible rather than silent.
        previous = _recall(session_id)
        turn = turn_router.classify(
            user_text,
            has_results=bool(previous and previous.get("candidates")),
            previous_query=previous["query"] if previous else "")

        if turn["route"] in ("question", "aside", "clarify"):
            await _answer_without_searching(
                websocket, turn, user_text, previous, session_id)
            return

        decision = refiner.parse(user_text, previous["query"] if previous else "")
        refining = bool(previous and decision.get("refine"))

        # A spec the current results do not contain is not a filter — it is
        # the same request with one value changed.
        #
        # "512gb" after an iPhone search matched none of the twenty-four
        # listings, because they were all 256GB. Filtering would have shown
        # them anyway (a filter that empties the page is skipped), and
        # searching for "512gb" alone lost the iPhone and returned SSDs. The
        # subject is carried over and the storage swapped, so the query
        # becomes what the person meant: the same phone, 512GB.
        amended_query = None
        if refining and (decision["ops"].get("attributes")):
            wanted = decision["ops"]["attributes"]
            present = [c for c in previous["candidates"]
                       if all(w in (c.get("name") or "").lower() for w in wanted)]
            if not present:
                amended_query = refiner.amend(previous["query"], wanted)
                refining = False
                await _send(websocket, "step",
                            f'None of the {len(previous["candidates"])} listings '
                            f'found are {", ".join(wanted)} — searching again for '
                            f'"{amended_query}"')

        # The amended phrase stands in for what was typed, so intent parsing,
        # screening and ranking all see the full request rather than a bare
        # spec with no subject.
        search_text = amended_query or user_text

        def shaping_budget(intent_dict):
            """
            The budget allowed to influence which listing wins.

            Zero unless the person named a figure. The ceiling still bounds
            the search, but a default must never reach the stages that read a
            budget as a statement of taste: the floor that discards listings
            priced far below it, and the tie-break that prefers the dearer of
            two equals because someone who says "₹30,000" is describing the
            class of thing they want. Applied to an invented number, both
            turn "iphone 17 pro" into a hunt for something near ₹5,000.
            """
            return (intent_dict.get("max_price_paise") or 0
                    if intent_dict.get("budget_stated") else 0)

        # Set on the fresh-search branch only; a refinement reuses the intent
        # that was already parsed on the turn that produced these listings.
        model_intent = None
        # Bound here because the screen only runs on a fresh search;
        # a refinement reuses listings already screened.
        screened = None
        # How many listings the venues actually returned, before any screen
        # ran. `candidates` is rebound by every stage, so by the time the
        # ranker has finished it holds the survivors — counting it in a
        # message about what was screened out reports zero out of zero.
        fetched_count = 0
        # Same reason, and one more: the precision checkpoint below runs on
        # both paths, so this has to exist on both. A refinement re-shows
        # listings, sponsored ones included, and a card shown again is a
        # second placement — so it is tracked and charged again, bounded by
        # the merchant's daily budget rather than by how often somebody
        # narrows a search.
        placements = promotions.PlacementRun([])
        sponsored_pool = []

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
            await _send(websocket, "step", "Reading the request")
            # Rule-derived, and instant. The search phrase and the ceiling
            # were already taken from the person's own words rather than the
            # model's reading of them, so waiting on the model to produce two
            # values that get overwritten anyway bought nothing but latency.
            intent = fast_intent(search_text)

            # The model still runs — it just runs alongside the search. Its
            # answer is joined before ranking, which is the first stage that
            # reads it.
            model_intent = asyncio.create_task(
                asyncio.to_thread(parse_intent, search_text))

            # Say "no budget stated" rather than quoting the search bound.
            # Printing a figure nobody typed is what made a ₹5,000 default
            # look like the person's own limit.
            bound = (f"under ₹{intent['max_price_paise'] / 100:,.0f}"
                     if intent.get("budget_stated") else "no budget stated")
            await _agent(websocket, "intent", "done", tools=[], summary=
                         f"{intent['category']} · {bound} · by {intent['priority']}")

        # Sign the constraints BEFORE any listing is fetched, so the bounds
        # can't be quietly widened later to fit whatever the agent found.
        intent_jwt = issue_intent_mandate(intent, customer["id"])
        await _send(websocket, "mandate", {
            "stage": "intent",
            "hash": mandate_digest(intent_jwt),
            "constraints": {
                "max_amount_paise": intent["max_price_paise"],
                # Whether that figure is the person's or ours. Printing a
                # ₹10,00,000 search bound as "signed — under ₹10,00,000"
                # states a spending permission nobody gave; what actually
                # bounds spending is the risk gate and the session ceiling.
                "budget_stated": bool(intent.get("budget_stated")),
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
            fetched_count = len(candidates)
            placements = promotions.PlacementRun(candidates)
            sponsored_pool = [dict(c) for c in candidates if c.get("sponsored")]
            quantity = 1
            await _agent(websocket, "scout", "done",
                         f'{len(candidates)} of the previous results kept', tools=[])
            await _send(websocket, "step", narrowed["summary"])

            # A refinement that could not be applied has to be said out
            # loud, not filed in the trace.
            #
            # "under 5000" against a set that starts at ₹7,051 stands down
            # rather than emptying the list — reasonable — but the only
            # notice of that went out as a `step`, which lands inside the
            # collapsed "How I got here" panel. On screen the person saw
            # "I found the top 4 for you" above four listings costing more
            # than the limit they had just named, and nothing saying why.
            # A constraint about money is exactly the one that must not be
            # quietly dropped.
            if narrowed.get("skipped"):
                cheapest = min((c.get("price_paise") or 0) for c in candidates)                     if candidates else 0
                asked = decision["ops"].get("max_price_paise") or 0
                await _send(websocket, "notice", {
                    "kind": "refinement_not_applied",
                    "headline": ("Nothing in these results is under "
                                 f"₹{asked / 100:,.0f}."
                                 if asked else
                                 "That filter could not be applied."),
                    # The suggested phrasing repeats the ORIGINAL query.
                    # "search again under 5000" was the first wording here
                    # and it routes to a fresh search whose category parses
                    # as "search again" — the agent would have gone off and
                    # queried eBay for that. Advice printed in the product
                    # has to be advice that works.
                    "detail": (
                        f"The cheapest of them is ₹{cheapest / 100:,.0f}. "
                        "These are still the previous results, unfiltered — "
                        "shown so you can see what is actually available, "
                        "not because they match what you asked for. To look "
                        "for cheaper ones instead of narrowing these, ask "
                        f"for “{_without_budget(previous['query'])} under "
                        f"{asked / 100:,.0f}”."
                        if asked and cheapest else narrowed["summary"]),
                    "skipped": narrowed["skipped"],
                })
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
            scope = (f"under ₹{intent['max_price_paise'] / 100:,.0f}"
                     if intent.get("budget_stated") else "at any price")
            await _send(websocket, "step",
                         f"Matching catalog {scope}" + {
                             "best": " — best quality first, then how much of your budget it uses, since you asked for the best",
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
            # New unless the person said otherwise. A marketplace prices
            # open-box and refurbished stock below new, so any ranking that
            # weighs price will surface them — and somebody who typed
            # "iphone 17 pro" was asking for a phone, not for a cheaper one.
            wanted_condition = condition_preference(search_text)
            candidates = await asyncio.to_thread(
                search_catalog, intent["category"], intent["max_price_paise"], sort,
                intent.get("requirements"), wanted_condition["allow"],
            )
            # Before anything counts them: a relisted offer appearing twice
            # took two of the five places on screen.
            candidates = deduplicate(candidates)
            fetched_count = len(candidates)

            # Follows any promoted candidates from here to the screen. It
            # only watches — every filter below runs on the same rules it
            # ran on before retail media existed, and this records what
            # they did to a sponsored card rather than softening it.
            placements = promotions.PlacementRun(candidates)
            # Kept before the screens run, because the complement strip is
            # built from products the screens will drop — that is what it is
            # for. The ranked answer above it is never drawn from here.
            sponsored_pool = [dict(c) for c in candidates if c.get("sponsored")]

            # The filter above is eBay's; this is ours, and it also covers
            # the merchant store, whose products carry no eBay condition id.
            # First-party stock is new, so it is kept whenever new is wanted.
            allowed = wanted_condition["allow"]
            before_condition = len(candidates)
            candidates = [
                c for c in candidates
                if (str(c.get("condition_id") or "") in allowed
                    or (c.get("source") == "merchant" and "1000" in allowed))
                # A seller who ticks "New" and then writes "open box" in the
                # title has told us twice, and the second answer is the one
                # they had to type out. Only drops when the person did not
                # ask for that condition anyway.
                and not (condition_conflict(c)
                         and not wanted_condition["stated"])
            ]
            placements.after("condition", candidates)
            set_aside = before_condition - len(candidates)
            if wanted_condition["stated"]:
                await _send(websocket, "step",
                            f"Showing {wanted_condition['label']} listings only, "
                            f"because you asked for them"
                            + (f" — set aside {set_aside} in other conditions"
                               if set_aside else ""))
            elif set_aside:
                await _send(websocket, "step",
                            f"New only — set aside {set_aside} open-box, "
                            f"refurbished or used listings. Say \"refurbished\" "
                            f"or \"used\" if you want those too.")

            # eBay matches every word, so a very specific request can return
            # nothing at all. The search broadens rather than reporting an
            # empty market — and says so, because searching for less than was
            # asked for is not something to leave a person to infer.
            try:
                from app.agent.catalog import _search_ebay as _ebay_stage
                used = getattr(_ebay_stage, "last_phrase", None)
                asked = (intent["category"] or "").strip()
                if used and used.lower() != asked.lower():
                    await _send(
                        websocket, "step",
                        f'Nothing matched "{asked}" exactly — searched '
                        f'"{used}" and kept the rest of your request as '
                        f'requirements to filter on')
            except Exception as exc:
                print(f"[agent] broadening note skipped: {exc}", flush=True)

            if not candidates:
                # Why it is empty decides what is worth saying. A product
                # that exists but costs more than the ceiling is a fact the
                # person can act on; "no products matched" is not.
                diagnosis = {}
                try:
                    from app.agent.catalog import _search_ebay as _ebay_stage
                    diagnosis = getattr(_ebay_stage, "last_diagnosis", None) or {}
                except Exception:
                    pass

                if diagnosis.get("reason") == "over_budget":
                    short_by = diagnosis["cheapest_paise"] - intent["max_price_paise"]
                    message = (
                        f"Found {diagnosis['seen']} listings for "
                        f"\"{diagnosis['phrase']}\", but the cheapest is "
                        f"₹{diagnosis['cheapest_paise'] / 100:,.0f} — "
                        f"₹{short_by / 100:,.0f} above your "
                        f"₹{intent['max_price_paise'] / 100:,.0f}. "
                        f"Nothing was bought. Raise the budget to about "
                        f"₹{diagnosis['cheapest_paise'] / 100:,.0f} and I can "
                        f"look again."
                    )
                    await _agent(websocket, "scout", "blocked",
                                 "In stock, over budget", "warn", tools=["ebay"])
                elif getattr(_ebay_stage, "last_rate_limited", False):
                    # Not the shopper's fault and not fixable by rewording.
                    message = (
                        "eBay is rate limiting this project's API key right "
                        "now, so the marketplace could not be searched at "
                        "all — this is not a result about your request.\n\n"
                        "The shop's own catalogue was still searched and had "
                        "nothing matching either. eBay's Browse quota resets "
                        "at midnight US/Pacific. Nothing was bought and "
                        "nothing was charged."
                    )
                    await _agent(websocket, "scout", "blocked",
                                 "eBay rate limited", "warn", tools=["ebay"])
                else:
                    phrase = diagnosis.get("phrase") or intent["category"]
                    # What is certain, then what to do — without asserting a
                    # cause. The same sentence covers a misspelling, a product
                    # eBay does not carry, and a word that is not a product at
                    # all, and it cannot know which of those happened.
                    message = (
                        f"No listings matched \"{phrase}\" at any price, so "
                        f"there was nothing to rank and nothing was bought.\n\n"
                        f"Worth trying: check the spelling, drop a word or two "
                        f"to widen it, or name the brand and model. eBay's "
                        f"catalogue is also thin on India-market products, so "
                        f"some things sold here are simply not listed there."
                    )
                    await _agent(websocket, "scout", "blocked",
                                 "No listings matched", "error", tools=["ebay"])

                await _send(websocket, "error", message)
                await websocket.close()
                return

            await _agent(websocket, "scout", "done", f"{len(candidates)} live listings retrieved",
                         tools=["ebay"])

            # Relevance: does the listing actually answer the request? Nothing
            # before this point reads the person's own words — Scout matches a
            # price ceiling, Trust looks at price and seller, and neither can
            # tell a camera phone from a ₹166 flip phone.
            await _agent(websocket, "value", "running", tools=["ollama"])

            # Join the model here — this is the first stage that reads anything
            # only it can provide. By now it has had the whole fetch, the trust
            # pass and the clarifying question to finish in, so it is usually
            # already done and this waits on nothing.
            model_reading = await _await_intent(model_intent)
            if model_intent is not None and model_reading is None:
                await _send(websocket, "step",
                            "The intent model did not answer in time — ranking "
                            "on the rules read from your own words")
            intent = merge_model_intent(intent, model_reading)

            await _send(websocket, "step", "Screening listings against what you asked for")
            screened = screen_relevance(candidates, search_text,
                                        intent.get("requirements"),
                                        budget_paise=shaping_budget(intent))
            candidates = screened["candidates"]
            placements.after("relevance", candidates)
            await _send(websocket, "step", screened["summary"])
            if screened.get("attribute_note"):
                await _send(websocket, "step", screened["attribute_note"])

            # Asked for the best? Then a model several generations behind a
            # newer one in the same results is not a candidate for it. This
            # compares model numbers within a line — arithmetic on the data —
            # and makes no claim about what is still in production.
            if (intent.get("quality_bias") or "").lower() == "best":
                try:
                    from app.agent import generation
                    recent = generation.drop_superseded(candidates)
                    if recent["dropped"]:
                        candidates = recent["candidates"]
                        await _send(websocket, "step", recent["note"])
                except Exception as exc:
                    print(f"[agent] generation check skipped: {exc}", flush=True)

            # What this person has actually paid for before, used only to break
            # ties among listings that already answer the request. Built from
            # captured payments — an abandoned order says what was considered,
            # not what was chosen.
            try:
                profile = await asyncio.to_thread(preferences.build, customer["id"])
                if profile.get("confidence") == "usable":
                    tuned = preferences.apply(candidates, profile,
                                              intent.get("requirements"))
                    if tuned["applied"]:
                        candidates = tuned["candidates"]
                        await _send(websocket, "step", tuned["note"])
                elif profile.get("purchases"):
                    # Say why it was not used, rather than silently not using it.
                    await _send(websocket, "step", profile["summary"])
            except Exception as exc:
                # Personalisation must never take down a purchase run.
                print(f"[preferences] skipped: {exc}", flush=True)

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
                    placements.after("trust", candidates)

            # Nothing is asked before the results are shown. The person came
            # with a sentence, and the next thing they should see is products
            # — not a form built out of whatever happened to vary in the
            # result set. Narrowing happens in conversation, once there is
            # something concrete to narrow.
            quantity = 1

        # Show the top real candidates (with clickable links) before narrowing
        # to one — this is what the "top matching products" panel renders
        # Order the shown list by what the person actually asked for. This
        # used to sort by discount unconditionally, so the biggest markdown
        # led the carousel even when nobody mentioned discounts — which put
        # an 80%-off flip phone at the front of a camera-phone search.
        # Real product reviews for the listings that could actually win.
        # Seller reputation is always present; stars are not, and the ones
        # that have them deserve to be judged on them.
        try:
            from app.agent.ebay_client import enrich_reviews
            candidates = await asyncio.to_thread(enrich_reviews, candidates, 8)
        except Exception as exc:
            print(f"[quality] review lookup skipped: {exc}", flush=True)

        # The precision stage: drop what eBay reports as unbuyable before
        # anything ranks it or explains it. Same stage the autonomous path
        # runs, so a person's search and an unattended one agree about what
        # counts as a candidate.
        precision_screen = precision.screen(candidates)
        if precision_screen["dropped"]:
            await _send(websocket, "step", precision_screen["summary"])
        candidates = precision_screen["candidates"]
        placements.after("precision", candidates)

        quality.annotate(candidates)
        reviewed = [c for c in candidates if (c.get("review_count") or 0) > 0]
        if reviewed:
            await _send(websocket, "step",
                        f"Read product reviews on {len(reviewed)} of "
                        f"{len(candidates)} listings — the rest are judged on "
                        f"seller record and condition alone")
        else:
            await _send(websocket, "step",
                        "None of these listings carry product reviews, so "
                        "quality is judged on seller record and condition")

        # Score on what is known now — seller record and condition. The
        # review lookup below refines these before the pick is made.
        quality.annotate(candidates)
        effective_sort = effective_priority(intent["priority"])
        # Read from the intent rather than a variable set on one branch only:
        # a refinement never runs the search block, and the rating sorter
        # below closes over this.
        bias = (intent.get("quality_bias") or "neutral").lower()
        sort_keys = {
            # The same key the recommendation is computed with, so the strip
            # and the pick cannot disagree about what "best" means.
            "value": lambda p: quality.value_key(
                p, shaping_budget(intent),
                (intent.get("quality_bias") or "neutral").lower()),
            "discount": lambda p: (-(p.get("discount_percent") or 0), p["price_paise"]),
            "price": lambda p: (p["price_paise"],),
            "delivery_days": lambda p: (p.get("delivery_days") or 99, p["price_paise"]),
            # Seller feedback used to order this list, which is why a 100%
            # feedback flip phone led a camera-phone search. Feedback says
            # the seller is reliable; it says nothing about the product.
            "rating": lambda p: (-p["price_paise"],) if bias == "best" else (p["price_paise"],),
        }
        ranked = sorted(candidates, key=sort_keys.get(effective_sort, sort_keys["rating"]))

        # Everything that survived the screens, in rank order — not the top
        # five.
        #
        # The sentence above the carousel already says how many were found
        # and how many were set aside, so showing five of eighteen made the
        # agent look like it was hiding its work: the count was honest and
        # the drawer was not. Scrolling right now walks the whole ranked
        # list, best first, which is also the only way to see for yourself
        # that the order is defensible.
        #
        # Capped so a very broad search cannot post hundreds of cards down a
        # websocket; the cap is well above what a screened set reaches in
        # practice, and the run says when it bites.
        top_candidates = ranked[:SHOWN_LIMIT]
        if len(ranked) > SHOWN_LIMIT:
            await _send(websocket, "step",
                        f"Showing the top {SHOWN_LIMIT} of {len(ranked)} that "
                        f"survived screening — scroll for the rest")

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
                top_candidates = top_candidates[:SHOWN_LIMIT - 1] + [buyable]
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
            user_text=search_text,
            requirements=intent.get("requirements"),
            budget_paise=shaping_budget(intent),
            unmet=(screened or {}).get("unmet_attributes"),
            # "best … under N" is a request about the product, so price
            # leads within a wider quality band. See quality.value_key.
            bias=(intent.get("quality_bias") or "neutral").lower(),
        )
        product = result["product"]

        # NOTHING SURVIVED THE SCREENS. THAT IS AN ANSWER.
        #
        # The guard further up covers the case where the venues returned
        # nothing at all. This is the other one, and it was missing: listings
        # WERE found and every screen — accessory, relevance, condition,
        # trust, precision — took its share until none were left. The run
        # then walked into `product["id"]` with product set to None and the
        # shopper was shown `'NoneType' object is not subscriptable`.
        #
        # A raw TypeError is the worst possible way to say "nothing here
        # answers that", and it is the most likely thing to happen on a small
        # catalogue, which is exactly when somebody is watching.
        if not product:
            limited = False
            try:
                from app.agent.catalog import _search_ebay as _ebay_stage
                limited = bool(getattr(_ebay_stage, "last_rate_limited", False))
            except Exception:
                pass

            await _agent(websocket, "value", "blocked",
                         result.get("reason") or "Nothing matched", "error",
                         tools=["ollama"])
            await _send(websocket, "error", (
                (f"{fetched_count} listing"
                 f"{'' if fetched_count == 1 else 's'} came back for "
                 f"\"{search_text}\", and none of them survived the screens "
                 f"for accessories, relevance, condition, trust and stock."
                 if fetched_count else
                 f"Nothing came back for \"{search_text}\" that could be "
                 f"ranked.")
                + ("\n\neBay is also rate limiting this project's API key "
                   "right now, so the marketplace was not searched — only the "
                   "shop's own catalogue was. Its quota resets at midnight "
                   "US/Pacific." if limited else "")
                + "\n\nNothing was bought and nothing was charged. Worth "
                  "trying: drop a word to widen the search, name the brand "
                  "and model, or raise the budget if you set one."
            ))
            await websocket.close()
            return

        summary = result["reason"]
        # Kept so the next message can be "why that one" and get this
        # sentence back rather than a reconstruction of it.
        _remember_reason(session_id, result["reason"])
        if effective != intent["priority"]:
            summary = f"{summary} (ranked by {effective}, pinned on the Value node)"
        await _agent(websocket, "value", "done", summary, tools=["ollama"])

        await _send(websocket, "match", {
            "product": product,
            "reason": result["reason"],
        })

        # The complement strip: promoted products offered BESIDE the answer.
        #
        # Measured, not assumed — a promoted product competing inside the
        # ranked results above has to pass the relevance screen, and across
        # five products and twelve queries none ever did, because that
        # screen and the store's own search both read the product name.
        # What retail media actually sells is the complement, so it is
        # offered as one, in its own strip, labelled as not being an answer
        # to the search. It is exempt from relevance and nothing else.
        complements = sponsored_adapter.complements(sponsored_pool, top_candidates)
        if complements:
            await _send(websocket, "sponsored", {
                "items": complements,
                "heading": f"Promoted by {complements[0].get('sponsored_by') or 'the merchant'}",
                "disclosure": (
                    "A complement, not an answer to your search. The merchant "
                    "paid to show this here; it did not affect the results "
                    "above, which were ranked on price, stock, condition and "
                    "seller record alone."
                ),
            })

        # Retail media settles here and nowhere earlier: a promoted product
        # that was considered and then dropped by a screen costs the
        # merchant nothing, because it never reached the shopper. Only the
        # cards actually on screen are charged for.
        if placements or complements:
            placement_report = await asyncio.to_thread(
                placements.settle, top_candidates + complements,
                product.get("id"), customer["id"])
            await _send(websocket, "placements", placement_report)
            if placement_report["shown"]:
                await _send(
                    websocket, "step",
                    f'{placement_report["shown"]} sponsored '
                    f'{"result is" if placement_report["shown"] == 1 else "results are"} '
                    f"in this list — promoted into consideration, then ranked "
                    f"on the same signals as everything else")

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
            # The person clicked a button with the amount written on it.
            #
            # This used to end the run: "₹86,318 would exceed the ₹20,000
            # ceiling", socket closed, nothing to do. But the ceiling bounds
            # what the AGENT may spend without being asked — it was never a
            # limit on the account holder, and the cart already treats it
            # that way. Here the button reads "Buy now · ₹86,318", so the
            # click is the authorisation; asking again would be asking a
            # question already answered.
            #
            # Nothing else is relaxed. The risk gate still runs below and
            # still stops duplicates, velocity, dead stock and unauthorised
            # venues, and this decision is written to the audit trail as the
            # person's own rather than disappearing into a successful order.
            ceiling = settings.get("budget", "session_ceiling_inr") * 100
            excess = max(0, budget.get("projected_paise", 0) - ceiling)
            log_decision(
                action_type="human_authorised_spend",
                amount_paise=product["price_paise"],
                decision="allowed",
                reason=(f"Person bought at ₹{product['price_paise'] / 100:,.2f} with "
                        f"the amount shown on the button"
                        + (f", ₹{excess / 100:,.2f} above their "
                           f"₹{ceiling / 100:,.0f} session ceiling" if excess else "")
                        + ". That ceiling bounds what the agent may spend "
                          "unattended, not what the account holder may spend."),
                customer_id=customer["id"],
            )
            await _send(websocket, "step",
                        f"Above your ₹{ceiling / 100:,.0f} session ceiling — going "
                        f"ahead because you chose this price yourself, and "
                        f"recording it in the audit trail as your decision.")
            await _agent(websocket, "budget", "done",
                         "Authorised by you", tools=["firestore"])

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

        # An escalation asks a question. Sometimes the click already answered
        # it.
        #
        # The gate escalates for two different reasons, and only one of them
        # is "does a person agree to spend this much". That one was answered
        # by pressing a button reading "Buy now · ₹86,318", and asking again
        # on the next screen is asking twice.
        #
        # The other is velocity — several purchases inside a few minutes —
        # which is not a question about this price at all. It is the guard
        # against a loop making many individually reasonable purchases, and
        # no amount printed on a button answers it. That one still stops and
        # asks, as does anything blocked outright.
        auto_approve = settings.get("risk", "auto_approve_limit_inr") * 100
        amount_only = (risk_result["decision"] == "escalated"
                       and (product.get("price_paise") or 0) > auto_approve)

        if amount_only:
            log_decision(
                action_type="human_authorised_spend",
                amount_paise=product["price_paise"],
                decision="allowed",
                reason=(f"{risk_result['reason']} — authorised by the person at "
                        f"the point of purchase, with the amount shown on the "
                        f"button they pressed."),
                customer_id=customer["id"],
            )
            await _send(websocket, "step",
                        "Above the amount the agent may spend unattended — "
                        "allowed because you chose it yourself, and recorded "
                        "as your decision.")
            risk_result = {**risk_result, "decision": "allowed",
                           "reason": risk_result["reason"] + " — authorised by you"}
            await _send(websocket, "risk_gate", risk_result)
        elif risk_result["decision"] == "escalated":
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

        # Razorpay caps `receipt` at 56 chars, and live eBay item IDs are
        # long — so use a short hash of the product/customer pair plus a
        # timestamp, keeping it unique without risking the limit.
        receipt_id = f"cp-{uuid.uuid4().hex[:16]}"
        from_merchant = (product.get("source") == "merchant")
        checkout_session = None

        if from_merchant:
            # Same handshake the cart performs. Without it the buyer is
            # charged and the seller is never told: settlement looks for a
            # session id, finds none, and reports nothing wrong.
            await _send(websocket, "step",
                        f"Opening a checkout with "
                        f"{product.get('merchant_name') or 'the merchant'}")
            try:
                checkout_session = await asyncio.to_thread(
                    merchant_client.open_checkout,
                    [{"id": product["id"], "quantity": quantity}],
                    {"customer_id": customer["id"], "name": customer.get("name"),
                     "email": customer.get("email")},
                    f"agent-{uuid.uuid4().hex}",
                )
            except Exception as exc:
                log_decision(
                    action_type="merchant_checkout_failed",
                    amount_paise=product["price_paise"],
                    decision="blocked",
                    reason=f"Could not open a checkout with the seller: {exc}",
                    customer_id=customer["id"],
                )
                await _agent(websocket, "payment", "blocked",
                             "The seller did not open a checkout", "error",
                             tools=["razorpay"])
                await _send(websocket, "error",
                            "The seller could not open a checkout for this item. "
                            "Nothing has been charged.")
                await websocket.close()
                return

            # The gate approved a number. A different number is not covered
            # by that approval.
            charged = checkout_session.get("total_paise")
            if charged != product["price_paise"]:
                log_decision(
                    action_type="merchant_price_mismatch",
                    amount_paise=charged or 0,
                    decision="blocked",
                    reason=(f"Gate approved Rs{product['price_paise'] / 100:,.2f} but "
                            f"the seller's session is for Rs{(charged or 0) / 100:,.2f}"),
                    customer_id=customer["id"],
                    order_id=checkout_session.get("razorpay_order_id"),
                )
                await _agent(websocket, "payment", "blocked",
                             "The seller's price changed", "error", tools=["razorpay"])
                await _send(websocket, "error",
                            "The seller's price changed while this was being "
                            "approved. Nothing was charged — try again.")
                await websocket.close()
                return

            # The merchant priced it and created the order; we reference it.
            razorpay_order = {"id": checkout_session["razorpay_order_id"],
                              "receipt": receipt_id}
        else:
            await _send(websocket, "step", "Creating Razorpay order")
            razorpay_order = create_order(
                amount_paise=product["price_paise"],
                receipt=receipt_id,
                notes={"customer_id": customer["id"],
                       "product_id": str(product["id"])},
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

        # What settlement reads. Written for both venues so an order always
        # says which one it came from rather than leaving it to be inferred.
        db.collection("orders").document(razorpay_order["receipt"]).update({
            "source": "merchant" if from_merchant else "ebay",
            "merchant_checkout_session": (checkout_session or {}).get("session_id"),
            "merchant_id": product.get("merchant_id") if from_merchant else None,
            "merchant_name": product.get("merchant_name") if from_merchant else None,
        })

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
        # A datastore outage is not a bug in the run, and "429 Quota
        # exceeded" tells the person nothing they can act on. The HTTP
        # routes already answer this case with a readable 503; the agent
        # socket said the raw exception instead, so the same outage looked
        # like two different failures depending on which screen you were on.
        from google.api_core.exceptions import GoogleAPICallError, ResourceExhausted
        if isinstance(exc, ResourceExhausted):
            message = ("The project's Firestore has hit its free-tier daily "
                       "read quota, so the agent cannot record this run. "
                       "It resets at midnight US/Pacific. Nothing is broken "
                       "and nothing was charged.")
        elif isinstance(exc, GoogleAPICallError):
            message = (f"The agent could not reach its datastore "
                       f"({type(exc).__name__}), so the run was stopped "
                       f"before anything was decided.")
        else:
            message = f"Agent run failed: {exc}"
        try:
            await _send(websocket, "error", message)
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
    # A turn that answered a question is complete, not incomplete — it just
    # never had a product to end on.
    if "reply" in types:
        return "answered"
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


async def _answer_without_searching(ws: WebSocket, turn: dict, user_text: str,
                                    previous: dict, session_id: str):
    """
    A turn that ends in a sentence rather than a search.

    Two routes arrive here. A question is answered from the listings already
    on screen — the answerer reads their fields and quotes the seller's own
    words, and says the listing is silent when it is, because the alternative
    is inventing a fact about something someone is about to buy.

    An aside gets the truth about what this is: a shopping agent. Saying so
    costs a sentence and is worth more than a guessed answer — a system that
    knows where its knowledge ends is easier to trust with money than one
    that always has something to say.

    Both are logged like any other turn, so the audit trail shows what was
    asked even when nothing was searched or spent.
    """
    await _send(ws, "step", f"Read as a question about the results — {turn['reason']}"
                if turn["route"] == "question"
                else f"Not a product request — {turn['reason']}")

    if turn["route"] == "question":
        candidates = (previous or {}).get("candidates") or []
        reason = (previous or {}).get("pick_reason") or ""
        text = answerer.answer(user_text, candidates, reason)
    elif turn["route"] == "clarify":
        # Ask instead of guessing. Whichever way this message was meant, the
        # person can say so in three words — and the results already on
        # screen are left alone, so an ambiguous line cannot replace what
        # they were looking at.
        # The router's `subject` is an unordered set of leftover words, which
        # quoted back reads as "capital france what" — worse than not
        # quoting at all. The person knows what they typed; what they need
        # is the boundary and the way forward.
        text = ("I only search marketplaces, so I cannot answer that from "
                "general knowledge. If it is something you want to buy, say "
                "what you are shopping for and I will look for it."
                # Only true when there are some. Said because the reassurance
                # is the point: an ambiguous message costs nothing.
                + (" The results above are untouched."
                   if (previous or {}).get("candidates") else ""))
    else:
        text = ("I search real marketplaces, compare what they return, and buy "
                "and track orders — that is the whole of what I do. I do not "
                "answer general questions, because I would only be guessing. "
                "Tell me what you are shopping for, or paste a photo of it.")

    await _send(ws, "reply", text)
    # Close explicitly. A search run ends by falling out of the handler and
    # letting the server tear the socket down, but this turn answered in a
    # quarter of a second and the socket was still open fifteen seconds
    # later — leaving the composer disabled, because the interface treats an
    # open socket as a run still thinking. Nothing more will be received on
    # this turn, so say so rather than relying on teardown to happen.
    await ws.close()


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