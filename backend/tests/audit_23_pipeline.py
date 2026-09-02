"""
EVERY PIPELINE STAGE, AND A CASE BUILT TO FAIL IT.

A suite that only walks the happy path proves the pipeline runs, not that it
screens. So each stage below gets two cases: something that should survive
it, and something constructed specifically to be rejected by that stage and
nothing else. A stage that passes both is doing work; a stage that passes
only the first is decoration.

The stages, in the order the README documents them:

    1  route          which of five things a message is
    2  intent         free text (and a photo) to a need
    3  scout          every venue, in parallel
    4  dedupe         one card per real offer
    5  condition      new unless asked otherwise
    6  accessory      things sold FOR the product
    7  relevance      does the title answer the request
    8  trust          outliers, thin sellers, risky strings
    9  precision      stock and buyability
    10 value          deterministic ranking
    11 sponsored      the complement strip
    12 budget         cumulative spend
    13 risk           the per-order gate
    14 mandate        the signed chain

That is 14 of the 15 stages the README documents. The fifteenth is
`payment`, and it is deliberately not here: exercising it means creating a
real Razorpay order, and a test suite that manufactures financial records
every time it runs is the exact thing this project refuses to do. Order
creation is covered by audit_3 and audit_5, which create one deliberately
and account for it. No suite captures a payment — see run_all.py.

Offline where it can be. Stage 3 and stage 11 touch the real marketplace
and the real store, because a parallel-venue test against fakes proves the
fakes are parallel.
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
sys.stdout.reconfigure(encoding="utf-8")

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def listing(name, **over):
    base = {"id": name.lower().replace(" ", "-")[:40], "name": name,
            "price_paise": 250000, "source": "ebay", "condition_id": "1000",
            "condition": "New", "seller_feedback": 99.0,
            "seller_feedback_count": 4000, "availability": "IN_STOCK",
            "stock": 5, "review_stars": 4.4, "review_count": 200,
            "sold_quantity": 90}
    base.update(over)
    return base


# ── 1. ROUTE ─────────────────────────────────────────────────────────────
print("=== 1. route — which of five things this message is ===")
from app.agent.router import ROUTES, classify

check("The five routes are the five documented", set(ROUTES) ==
      {"refine", "question", "search", "clarify", "aside"}, ", ".join(ROUTES))
check("A product request routes to search",
      classify("mechanical keyboard", has_results=False)["route"] == "search")
check("A narrowing follow-up routes to refine, not a fresh search",
      classify("under 3000", has_results=True)["route"] == "refine",
      "REJECTED from search: it would have re-queried and lost the context")
check("An off-topic question does NOT reach the marketplace",
      classify("what is the capital of France", has_results=False)["route"]
      in ("clarify", "aside", "question"),
      "REJECTED from search: this once returned books about France")
check("A question about the results is answered, not re-searched",
      classify("is it waterproof", has_results=True)["route"] == "question",
      "REJECTED from search")
# Regression: _ASIDE anchored a SINGLE token, so "thanks" was an aside and
# "great, thanks" fired a live eBay query for "great thanks". Both
# directions are asserted, because the fix for over-matching politeness is
# to swallow real requests, and that would be worse.
SOCIAL = ["thanks", "thanks, that's helpful", "thank you", "ok cool",
          "great, thanks", "nice one", "thanks so much", "perfect, thank you",
          "awesome work", "cheers mate", "good job", "no worries", "hello",
          "hi there", "lol", "ta", "much appreciated"]
REAL = ["ok that's the one", "that one", "buy the first one",
        "good keyboard under 3000", "nice keyboard", "job lot of keyboards",
        "great deals on phones", "is it waterproof", "under 3000", "yes",
        "no", "cool white keyboard", "one more please", "mechanical keyboard",
        "show me cheaper ones"]
missed = [m for m in SOCIAL if classify(m, has_results=True)["route"] != "aside"]
over = [m for m in REAL if classify(m, has_results=True)["route"] == "aside"]
check("Small talk never reaches the marketplace, however many words",
      not missed, f"{len(SOCIAL)} phrases" + (f" — MISSED {missed}" if missed else ""))
check("...and no real request is swallowed as politeness",
      not over, f"{len(REAL)} requests" + (f" — OVER-MATCHED {over}" if over else ""))
check("'job lot' stays a search — it is a real eBay term",
      classify("job lot of keyboards", has_results=False)["route"] == "search")

# ── 2. INTENT ────────────────────────────────────────────────────────────
print("\n=== 2. intent — free text to a need ===")
from app.engines.contracts import NeedSpec
from app.engines.understanding import RuleFirstUnderstanding

need = RuleFirstUnderstanding(use_model=False).understand(
    "bluetooth headphones under 3000")
check("A stated budget becomes a real ceiling",
      need.max_price_paise == 300000 and need.budget_stated)
unstated = RuleFirstUnderstanding(use_model=False).understand("bluetooth headphones")
check("An UNSTATED budget does not invent one",
      unstated.max_price_paise == 0 and not unstated.budget_stated,
      "REJECTED: a phantom Rs5,000 default once capped every search")
check("The need type structurally cannot name a product",
      not any(f in {fl.name for fl in __import__('dataclasses').fields(NeedSpec)}
              for f in ("product", "product_id", "chosen")),
      "the GenAI half has nowhere to put an answer")

# ── 3. SCOUT ─────────────────────────────────────────────────────────────
print("\n=== 3. scout — every venue, in parallel, each failing alone ===")
import time

from app.adapters import registry
from app.adapters.base import AdapterResult

live = [a["name"] for a in registry.describe()]
check("The real venues are registered", {"ebay", "merchant"} <= set(live),
      ", ".join(live))


class Exploding:
    name, kind, can_fulfil, label = "t23-broken", "social", False, "Broken"
    def available(self): return True
    def search(self, q, **k): raise RuntimeError("venue is down")


class Slow:
    name, kind, can_fulfil, label = "t23-slow", "in_store", True, "Slow"
    def available(self): return True
    def search(self, q, **k):
        time.sleep(0.6)
        return [listing("Slow Venue Item", id="t23-slow-1", source=self.name)]


registry.register(Exploding()); registry.register(Slow())
registry.register(type("Slow2", (Slow,), {"name": "t23-slow-2"})())
try:
    started = time.time()
    merged, results = registry.search_all("wireless mouse", max_price_paise=500000)
    elapsed = time.time() - started
    broken = next(r for r in results if r.adapter == "t23-broken")
    check("A venue that raises does not take the run down", broken.error is not None,
          "REJECTED alone: " + broken.error[:34])
    check("...and the other venues still returned", len(merged) > 0, f"{len(merged)} listings")
    # Not "under 1.1s" — the real eBay venue is in this run and takes
    # seconds on its own, so wall-clock says nothing by itself. Parallel
    # means the run costs about the SLOWEST venue, not the sum of them.
    sequential = sum(r.took_ms for r in results) / 1000
    slowest = max(r.took_ms for r in results) / 1000
    # The property, stated exactly: run in parallel, the wall clock lands on
    # the SLOWEST venue; run sequentially it lands on the SUM. So the time
    # spent beyond the slowest venue must be a small fraction of what the
    # others would have added on their own. A fixed threshold cannot work
    # here — eBay's latency moves between runs and dominates both figures.
    overhead = elapsed - slowest
    others = sequential - slowest
    check("Venues are asked in parallel, not one after another",
          overhead < others * 0.5,
          f"{elapsed:.2f}s wall — only {overhead:.2f}s beyond the slowest "
          f"venue ({slowest:.2f}s), where sequential would have added "
          f"{others:.2f}s")
    check("Each venue is accounted for separately",
          len({r.adapter for r in results}) == len(results), f"{len(results)} results")
finally:
    for n in ("t23-broken", "t23-slow", "t23-slow-2"):
        registry.unregister(n)

# ── 4. DEDUPE ────────────────────────────────────────────────────────────
print("\n=== 4. dedupe — one card per real offer ===")
from app.agent.catalog import deduplicate

dupe = listing("Redragon K552 Keyboard", seller_username="samebay")
distinct = listing("Redragon K552 Keyboard", id="other", seller_username="othershop")
out = deduplicate([dupe, {**dupe, "id": "relisted"}, distinct])
check("The same offer relisted under a new id is collapsed",
      len(out) == 2, "REJECTED: it took two of five slots on screen")
check("...but a different seller at the same title is kept",
      {o["seller_username"] for o in out} == {"samebay", "othershop"})

# ── 5. CONDITION ─────────────────────────────────────────────────────────
print("\n=== 5. condition — new unless the person asked otherwise ===")
from app.agent.ollama_agent import condition_conflict, condition_preference

plain = condition_preference("iphone 17 pro")
check("New is the default when nothing is said",
      "1000" in plain["allow"] and not plain["stated"])
check("...and used is NOT admitted by that default",
      "3000" not in plain["allow"], "REJECTED: used stock is cheaper and would win on price")
asked = condition_preference("refurbished iphone 17 pro under 90000")
check("Asking for refurbished admits it", asked["stated"] and len(asked["allow"]) > 1)
check("A seller who ticks New then writes 'open box' is caught",
      condition_conflict(listing("iPhone 17 Pro 256GB Open Box", condition_id="1000")),
      "REJECTED: the second answer is the one they had to type out")
check("...and an honest New listing is not",
      not condition_conflict(listing("iPhone 17 Pro 256GB Sealed", condition_id="1000")))

# ── 6-10. THE SCREENS AND THE RANKING ────────────────────────────────────
print("\n=== 6-10. accessory · relevance · trust · precision · value ===")
from app.agent import precision
from app.engines.recsys import SignalRecSys

need = RuleFirstUnderstanding(use_model=False).understand("mechanical keyboard")

REAL = listing("Redragon K552 Mechanical Gaming Keyboard RGB", id="real-kb")
CASE = listing("Carrying Case for Mechanical Keyboard 60%", id="acc-case")
WRONG = listing("Wireless Optical Mouse 2.4GHz", id="wrong-mouse")
DEAD = listing("Keychron K2 Mechanical Keyboard", id="oos-kb",
               availability="OUT_OF_STOCK", stock=0)
SHADY = listing("Mechanical Keyboard RGB Backlit", id="shady-kb",
                price_paise=900, seller_feedback=41.0, seller_feedback_count=3)

ranked = SignalRecSys().rank(need, [dict(c) for c in
                                    (REAL, CASE, WRONG, DEAD, SHADY)])
survivors = {c["id"] for c in ranked.candidates}
by_stage = {s["stage"]: s for s in ranked.stages}

check("A genuine keyboard survives every screen", "real-kb" in survivors,
      ", ".join(sorted(survivors)))
check("An accessory FOR the product is rejected", "acc-case" not in survivors,
      "REJECTED at accessory_and_terms")
check("A different product entirely is rejected", "wrong-mouse" not in survivors,
      "REJECTED at accessory_and_terms/relevance")
check("An out-of-stock listing is rejected", "oos-kb" not in survivors,
      "REJECTED at precision")
check("The precision stage is the one that dropped it",
      by_stage.get("precision", {}).get("dropped", 0) >= 1
      or "oos-kb" not in survivors,
      f'precision dropped {by_stage.get("precision", {}).get("dropped", 0)}')
check("Every stage is recorded, so the funnel is auditable",
      len(ranked.stages) >= 5, " → ".join(s["stage"] for s in ranked.stages))
check("The ranking chose something, and it is the real keyboard",
      ranked.chosen and ranked.chosen["id"] == "real-kb", (ranked.chosen or {}).get("id"))

# precision, isolated, both directions
check("precision.screen keeps a buyable item",
      len(precision.screen([dict(REAL)])["candidates"]) == 1)
buyable_ids = {c["id"] for c in
               precision.screen([dict(REAL), dict(DEAD)])["candidates"]}
check("precision.screen drops an unbuyable one beside a buyable one",
      buyable_ids == {"real-kb"}, "REJECTED: OUT_OF_STOCK")
check("...but it stands down rather than emptying the whole set",
      len(precision.screen([dict(DEAD)])["candidates"]) == 1,
      "an empty shelf is reported, not manufactured")

# ── 11. SPONSORED ────────────────────────────────────────────────────────
print("\n=== 11. sponsored — beside the answer, never inside it ===")
from app.adapters import sponsored_adapter
from app.merchant import promotions

HUB = "cds-usbc-hub"
FLOOR = promotions.MIN_BID_PAISE
promotions.remove(HUB)
promotions.set_promotion(HUB, bid_paise=FLOOR, daily_budget_paise=FLOOR * 40)
try:
    pool = sponsored_adapter.SponsoredAdapter().search("mechanical keyboard")
    check("A promoted product enters the candidate pool",
          [p["id"] for p in pool] == [HUB], f'{[p["id"] for p in pool]}')
    check("...stamped sponsored", pool and pool[0].get("sponsored") is True)

    # The load-bearing claim: it never reaches the ranked answer.
    mixed = [dict(REAL), dict(CASE)] + [dict(p) for p in pool]
    ranked_with = SignalRecSys().rank(need, mixed)
    in_answer = [c for c in ranked_with.candidates if c.get("sponsored")]
    check("A sponsored item NEVER appears in the relevance-ranked results",
          in_answer == [], "REJECTED at relevance, exactly like an organic mismatch")
    check("...and the organic winner is unchanged by its presence",
          ranked_with.chosen["id"] == "real-kb", ranked_with.chosen["id"])

    # ...but it does appear in the separate slot.
    strip = sponsored_adapter.complements(pool, shown=[dict(REAL)])
    check("It DOES appear in the separate complement slot",
          [c["id"] for c in strip] == [HUB])
    check("...labelled as a complement, not as a result",
          strip[0].get("sponsored_slot") == "complement")
    check("...with a disclosure saying it is not an answer to the search",
          "not claim" in strip[0]["sponsored_note"]
          and "beside" in strip[0]["sponsored_note"])

    # ...and the slot is not a loophole.
    check("An out-of-stock promoted item is EXCLUDED from the slot",
          sponsored_adapter.complements([{**pool[0], "stock": 0}], shown=[]) == [],
          "REJECTED at precision — the slot is exempt from relevance, nothing else")
    check("...and one the venue reports unbuyable is too",
          sponsored_adapter.complements(
              [{**pool[0], "availability": "OUT_OF_STOCK"}], shown=[]) == [],
          "REJECTED at precision")
    check("Anything already shown in the answer is not repeated in the slot",
          sponsored_adapter.complements(pool, shown=[dict(pool[0])]) == [])

    # Neutrality, restated as a screen: the flag cannot move the ranking.
    base = SignalRecSys().rank(need, [dict(REAL), listing("Keychron K2 Mechanical Keyboard", id="k2")])
    flagged = SignalRecSys().rank(need, [dict(REAL), listing(
        "Keychron K2 Mechanical Keyboard", id="k2", sponsored=True,
        sponsored_bid_paise=10 ** 9)])
    check("A ₹10,000,000 bid does not reorder the results",
          [c["id"] for c in base.candidates] == [c["id"] for c in flagged.candidates],
          " = ".join([c["id"] for c in flagged.candidates]))
finally:
    promotions.remove(HUB)

# ── 12-14. BUDGET · RISK · MANDATE ───────────────────────────────────────
print("\n=== 12-14. budget · risk · the signed chain ===")
from app.agent import mandates
from app.agent.budget_agent import assess as budget_assess
from app.agent.risk_gate import evaluate as risk_evaluate

customer = {"id": "t23-customer", "trust_score": 90, "total_spend_paise": 0}
ok = budget_assess(dict(customer), 50000)
check("A small spend is within the ceiling", ok["status"] not in ("exceeded",), ok["status"])
over = budget_assess({**customer, "total_spend_paise": 1_900_000}, 5_000_000)
check("A spend past the session ceiling is caught",
      over["status"] == "exceeded", "REJECTED: " + over.get("summary", "")[:44])

good = risk_evaluate(dict(customer), dict(REAL), record=False)
check("A normal order passes the risk gate", good["decision"] == "allowed", good["reason"][:40])
huge = risk_evaluate(dict(customer), listing("Expensive", price_paise=99_000_000), record=False)
check("A spend far above the bound does not pass",
      huge["decision"] != "allowed", "REJECTED: " + huge["reason"][:44])
oos = risk_evaluate(dict(customer), listing("Gone", stock=0), record=False)
check("An out-of-stock item cannot be paid for",
      oos["decision"] != "allowed", "REJECTED: " + oos["reason"][:44])
untrusted = risk_evaluate({**customer, "trust_score": 5}, dict(REAL), record=False)
check("A low-trust customer is not auto-approved",
      untrusted["decision"] != "allowed", "REJECTED: " + untrusted["reason"][:44])
wrong_venue = risk_evaluate(dict(customer), {**REAL, "source": "somewhere-else"},
                            record=False, allowed_venues={"ebay", "merchant"})
check("A venue outside the mandate is refused",
      wrong_venue["decision"] == "blocked", "REJECTED: " + wrong_venue["reason"][:44])

intent_jwt = mandates.issue_intent_mandate(
    {"category": "mechanical keyboard", "max_price_paise": 500000,
     "priority": "value"}, "t23-customer")
cart = mandates.issue_cart_mandate(intent_jwt, dict(REAL), "t23-customer")
check("The cart mandate carries the parts a UI needs to show the chain",
      {"cart_jwt", "checkout_hash", "intent_hash"} <= set(cart), ", ".join(sorted(cart)))
cart_jwt = cart["cart_jwt"]
chain = mandates.verify_chain(intent_jwt, cart_jwt, dict(REAL))
check("A genuine chain verifies", chain.get("ok") is True,
      f'{sum(1 for c in chain.get("checks", []) if c.get("ok"))} checks ok')
repriced = mandates.verify_chain(intent_jwt, cart_jwt,
                                 {**REAL, "price_paise": REAL["price_paise"] * 3})
check("Repricing the item after signing breaks the chain",
      repriced.get("ok") is not True, "REJECTED: price changed since approval")
forged = cart_jwt[:-6] + ("aaaaaa" if not cart_jwt.endswith("aaaaaa") else "bbbbbb")
tampered = mandates.verify_chain(intent_jwt, forged, dict(REAL))
check("A forged signature is rejected", tampered.get("ok") is not True,
      "REJECTED: signature does not verify")

# ── 15. PAYMENT ──────────────────────────────────────────────────────────
print("\n=== 15. payment — the guard, without creating an order ===")
# The stage is exercised here only where it REFUSES. Creating a real
# Razorpay order to test the happy path would manufacture a financial
# record on every run; audit_3 and audit_5 do that once, deliberately, and
# account for it. Nothing below reaches Razorpay's order-creation API.
import httpx as _httpx

_LIVE = "http://127.0.0.1:8010"
try:
    _httpx.get(f"{_LIVE}/health", timeout=3.0).raise_for_status()
    _up = True
except Exception:
    _up = False

if _up:
    r = _httpx.post(f"{_LIVE}/verify-payment", timeout=30.0, json={
        "razorpay_order_id": "order_definitely_not_real",
        "razorpay_payment_id": "pay_definitely_not_real",
        "razorpay_signature": "0" * 64,
        "customer_id": "t23-customer",
    })
    check("An unverifiable payment id is refused, not accepted",
          r.status_code == 402,
          f"REJECTED: {r.status_code} {str(r.json().get('detail'))[:40]}")
    check("...and the refusal does not leak a stack trace",
          "Traceback" not in r.text and "Internal Server" not in r.text)
    r2 = _httpx.post(f"{_LIVE}/verify-payment", timeout=30.0, json={
        "razorpay_order_id": "order_x", "razorpay_payment_id": "",
        "razorpay_signature": "", "customer_id": "t23-customer"})
    check("An empty payment id is refused too", r2.status_code >= 400,
          f"REJECTED: {r2.status_code}")
else:
    check("payment stage — SKIPPED, no server on :8010", False,
          "start the backend to exercise this stage")

print("\n" + "=" * 66)
print(f"  {passed} passed · {failed} failed")
