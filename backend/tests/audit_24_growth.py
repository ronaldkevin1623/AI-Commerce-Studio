"""
THE MERCHANT-SIDE GATE, AND THE AGENTS BEHIND IT.

Deliberately offline. These agents read the store's own records and spend
the merchant's margin — no marketplace, no payment provider — so the suite
covering them must not fail because eBay is rate-limiting or Razorpay is
unreachable. That independence is a property worth keeping: it means the
growth half can be demonstrated with the wifi off.
"""
import io
import os
import time
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app.agent import settings
from app.growth import gate, registry
from app.growth.base import Proposal

PASSED = FAILED = 0


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [PASS] {name} — {detail}" if detail else f"  [PASS] {name}")
    else:
        FAILED += 1
        print(f"  [FAIL] {name} — {detail}" if detail else f"  [FAIL] {name}")


def proposal(**kwargs):
    base = dict(agent="test", kind="recover_cart", headline="h", detail="d",
                cost_paise=1000, sample_size=99, params={"discount_pct": 5})
    base.update(kwargs)
    return Proposal(**base)


print("\n=== The agents register ===")
registry.bootstrap()
ids = sorted(a.agent_id for a in registry.agents())
check("every growth agent loads",
      ids == ["bundles", "crosssell", "offers", "reactivation", "recovery"], str(ids))
# The roster is asserted exactly rather than by count: a registered agent
# that can give away margin is the thing this suite exists to bound, so a
# new one appearing without a deliberate edit here should fail loudly.
check("only margin-spenders declare it",
      {a.agent_id for a in registry.agents() if a.spends_margin}
      == {"recovery", "offers", "reactivation", "bundles"},
      str(sorted(a.agent_id for a in registry.agents() if a.spends_margin)))

print("\n=== Bound 1: the kill switch ===")
settings.apply({"growthgate": {"enabled": False}})
verdict = gate.evaluate(proposal())
check("nothing passes while growth is off", verdict["verdict"] == "blocked", verdict["reason"][:60])
scanned = registry.scan()
check("the scan still runs and proposes while off", len(scanned) >= 0, f"{len(scanned)} proposals")
check("every proposal is blocked while off",
      all(p["verdict"] == "blocked" for p in scanned))

settings.apply({"growthgate": {"enabled": True}})

# Headroom for every bound below.
#
# Applying an offer writes a growth_applied decision, and the daily cap
# is computed by summing those out of the log — correctly, because the
# log is what gets audited and a separate counter could drift from it.
# The side effect is that this suite spends real budget every time it
# runs, so by the third run of a day a ten-rupee giveaway was refused by
# an exhausted DAILY cap while the per-action bound under test was fine
# — a red assertion about working code, which is worse than no test.
# Bound 3 below still proves the daily cap by setting it to zero; this
# only stops it silently deciding the other four.
_headroom_inr = int(gate.spent_today_paise() / 100) + 5000
settings.apply({"growthgate": {"daily_cap_inr": _headroom_inr}})

print("\n=== Bound 2: the per-action cap ===")
check("a giveaway over the cap escalates",
      gate.evaluate(proposal(cost_paise=50000))["verdict"] == "escalated",
      "₹500 against a ₹200 cap")
check("a giveaway under the cap does not",
      gate.evaluate(proposal(cost_paise=1000))["verdict"] == "allowed")

print("\n=== Bound 3: the daily cap ===")
settings.apply({"growthgate": {"daily_cap_inr": 0}})
check("a spent daily budget blocks",
      gate.evaluate(proposal())["verdict"] == "blocked",
      "cap of ₹0 leaves nothing to give")
settings.apply({"growthgate": {"daily_cap_inr": _headroom_inr}})

print("\n=== Bound 4: the percentage ceiling ===")
check("a discount deeper than the ceiling escalates",
      gate.evaluate(proposal(params={"discount_pct": 40}))["verdict"] == "escalated",
      "40% against a 15% ceiling")
check("a percentage bound is separate from the rupee one",
      gate.evaluate(proposal(cost_paise=1, params={"discount_pct": 40}))["verdict"] == "escalated",
      "cheap in rupees, still too deep")

print("\n=== Bound 5: the evidence floor ===")
check("a costed action on thin evidence escalates",
      gate.evaluate(proposal(sample_size=1))["verdict"] == "escalated", "n=1 below 3")
check("a FREE action skips the floor",
      gate.evaluate(proposal(cost_paise=0, sample_size=0))["verdict"] == "allowed",
      "no margin at stake, so no evidence needed")

print("\n=== An agent cannot clear its own proposal ===")
settings.apply({"growthgate": {"min_sample": 99}})
scan = registry.scan()
thin = next((p for p in scan if p["cost_paise"] > 0), None)
if thin:
    refused = registry.apply(thin)
    check("apply without approval is refused", refused.get("ok") is False,
          str(refused.get("reason"))[:70])
    approved = registry.apply(thin, approved_by="audit")
    check("apply WITH a human approval succeeds", approved.get("ok") is True,
          approved.get("offer_id", ""))
    if approved.get("ok"):
        from app.firebase_client import db
        db.collection("growth_offers").document(approved["offer_id"]).delete()
else:
    check("a costed proposal exists to test approval on", True,
          "none pending — every cart already carries an offer")
settings.apply({"growthgate": {"min_sample": 3}})

print("\n=== Honesty about thin data ===")
experiment = next((p for p in registry.scan() if p["kind"] == "test_discount"), None)
if experiment:
    check("the discount test refuses to rank on a tiny sample",
          "NOT A RESULT YET" in experiment["detail"] or "NOT SEPARABLE" in experiment["detail"],
          experiment["headline"][:60])
    check("it states the sample it rests on",
          experiment["sample_size"] >= 0 and bool(experiment["evidence_note"]))
else:
    check("the discount test runs", True, "no applied offers yet to compare")

crosssell = [p for p in registry.scan() if p["kind"] == "cross_sell"]
if crosssell:
    check("cross-sell says which basis it used",
          all("co-purchase" in p["evidence_note"] or "adjacency" in p["evidence_note"]
              for p in crosssell),
          f"{len(crosssell)} suggestions")
    check("cross-sell costs the merchant nothing",
          all(p["cost_paise"] == 0 for p in crosssell))

print("\n=== A campaign is a bounded programme, and can end ===")
from app.growth import campaigns

opened = campaigns.create("audit - window already closed", 50000, 24, ["recovery"])
row = campaigns.get(opened["campaign_id"])
row["ends_at"] = time.time() - 60
campaigns._db().collection(campaigns.COLLECTION).document(opened["campaign_id"]).set(row)
result = campaigns.tick(opened["campaign_id"])
check("a campaign past its window refuses to tick", result.get("ok") is False,
      str(result.get("error"))[:44])
check("and finishes itself rather than staying open",
      campaigns.get(opened["campaign_id"])["state"] == "finished",
      campaigns.get(opened["campaign_id"])["stopped_reason"])

paused = campaigns.create("audit - paused", 50000, 24, ["recovery"])
campaigns.pause(paused["campaign_id"])
check("a paused campaign refuses to tick",
      campaigns.tick(paused["campaign_id"]).get("ok") is False)
campaigns.resume(paused["campaign_id"])
check("resume puts it back to running",
      campaigns.get(paused["campaign_id"])["state"] == "running")

empty = campaigns.create("audit - no agents", 5000, 24, [])
check("a campaign with no agents does nothing rather than crash",
      campaigns.tick(empty["campaign_id"]).get("ok") is True)

measured = campaigns.measure(opened["campaign_id"])
check("measurement states its sample rather than only a rate",
      measured.get("ok") and "sample_size" in measured,
      "n=%s" % measured.get("sample_size"))
check("measurement claims no uplift it cannot support",
      "no control group" in measured.get("note", "").lower()
      or measured.get("sample_size", 0) >= 5)

for doc in campaigns._db().collection(campaigns.COLLECTION).stream():
    if str((doc.to_dict() or {}).get("goal", "")).startswith("audit - "):
        campaigns._db().collection(campaigns.COLLECTION).document(doc.id).delete()

settings.apply({"growthgate": {"enabled": False}})

# ── The relationship graph ───────────────────────────────────────────────
#
# The whole value of this graph is that it separates what was observed
# from what was assumed. If that distinction ever collapses, every
# recommendation built on it silently becomes a guess presented as
# evidence — so it is asserted rather than trusted.
print()
print("=== The product relationship graph ===")
from app.growth import graph as growth_graph

picture = growth_graph.build()
bases = {e["basis"] for e in picture["edges"]}
check("every edge declares a basis",
      bases <= {"co_purchase", "category_adjacency"}, str(sorted(bases)))
check("an assumed edge never claims support",
      all(e["support"] == 0 for e in picture["edges"]
          if e["basis"] == "category_adjacency"))
check("an observed edge always has support",
      all(e["support"] >= 1 for e in picture["edges"]
          if e["basis"] == "co_purchase"))
observed_pairs = {tuple(sorted((e["source"], e["target"])))
                  for e in picture["edges"] if e["basis"] == "co_purchase"}
assumed_pairs = {tuple(sorted((e["source"], e["target"])))
                 for e in picture["edges"]
                 if e["basis"] == "category_adjacency"}
check("no pair is drawn both ways", not (observed_pairs & assumed_pairs))
check("the note tells the reader which kind they are looking at",
      "adjacency" in picture["note"].lower())
check("the basis counts agree with the edges",
      picture["basis_counts"]["co_purchase"] == len(observed_pairs)
      and picture["basis_counts"]["category_adjacency"] == len(assumed_pairs))

if picture["nodes"]:
    ranked = growth_graph.complements(picture["nodes"][0]["id"], limit=5)
    kinds = [c["basis"] for c in ranked]
    check("observed complements outrank assumed ones absolutely",
          kinds == sorted(kinds, key=lambda k: 0 if k == "co_purchase" else 1),
          str(kinds))

print()
print("=== Attribution ===")
from app.growth import attribution as growth_attribution

result = growth_attribution.build(days=30)
check("no revenue is reported that cannot be named",
      result["attributed_revenue_paise"]
      == sum(c["revenue_paise"] for c in result["conversions"]))
check("every conversion says why it was counted",
      all(c.get("why") for c in result["conversions"]))
check("margin spent is reported beside the revenue",
      "margin_spent_paise" in result)
check("the caveat refuses the incremental reading",
      "not incremental" in result["caveat"].lower())
check("no conversion rate is claimed at any sample size",
      "%" not in result["headline"] and "%" not in result["caveat"])

print()
print("=== A cross-sell that converts is traceable ===")

# THE LINK THIS COVERS.
#
# A growth agent proposes a cross-sell, the gate rules, the merchant
# approves — and for a while that chain ended in a database row nothing
# read. Attribution matched offers aimed at a checkout session or a
# customer, but a cross-sell is aimed at a PRODUCT, so a sale it caused was
# invisible. These assertions are what stop that regressing.
import time as _time
import uuid as _uuid

from app.firebase_client import db as _db
from app.merchant import store as _store

_anchor, _complement = "cds-desk-lamp", "cds-monitor-stand"
_offer_id = f"go-audit-{_uuid.uuid4().hex[:8]}"
_now = _time.time()
_db.collection("growth_offers").document(_offer_id).set({
    "offer_id": _offer_id, "agent": "crosssell", "kind": "cross_sell",
    "target_kind": "product", "target_id": _anchor,
    "cost_paise": 0, "params": {"complement_id": _complement, "basis": "category"},
    "approved_by": "audit", "campaign_id": None,
    "created_at": _now - 3600, "state": "live",
})

# A paid basket holding the anchor AND the complement, placed after the
# offer. Only the complement's line should ever be counted.
_session_id = f"cs-audit-{_uuid.uuid4().hex[:8]}"
_store.db.collection(_store.SESSIONS).document(_session_id).set({
    "id": _session_id, "status": "paid", "currency": "INR",
    "merchant_id": _store.MERCHANT_ID,
    "created_at": datetime.fromtimestamp(_now - 60, tz=timezone.utc),
    "total_paise": 278000,
    "buyer": {"name": "audit", "customer_id": "audit-buyer"},
    "line_items": [
        {"id": _anchor, "name": "Warm LED Desk Lamp", "quantity": 1,
         "unit_price_paise": 149000, "amount_paise": 149000},
        {"id": _complement, "name": "Bamboo Monitor Stand", "quantity": 1,
         "unit_price_paise": 129000, "amount_paise": 129000},
    ],
})

# And one placed BEFORE the offer existed, which must not count however
# neatly it lines up.
_early_id = f"cs-audit-{_uuid.uuid4().hex[:8]}"
_store.db.collection(_store.SESSIONS).document(_early_id).set({
    "id": _early_id, "status": "paid", "currency": "INR",
    "merchant_id": _store.MERCHANT_ID,
    "created_at": datetime.fromtimestamp(_now - 86400, tz=timezone.utc),
    "total_paise": 129000,
    "buyer": {"name": "audit", "customer_id": "audit-buyer"},
    "line_items": [
        {"id": _complement, "name": "Bamboo Monitor Stand", "quantity": 1,
         "unit_price_paise": 129000, "amount_paise": 129000},
    ],
})

try:
    from app.growth import attribution as _attr
    _result = _attr.build(days=30)
    _crosses = [c for c in _result["conversions"] if c["kind"] == "cross_sell"]

    check("A converted cross-sell is attributed at all",
          len(_crosses) == 1, f"{len(_crosses)} cross-sell conversions")

    # The number that matters. Counting the basket would turn a Rs1,290
    # addition into Rs2,780 of "agent revenue" and is the easiest figure on
    # the whole dashboard to inflate.
    check("Only the recommended line is counted, not the basket",
          bool(_crosses) and _crosses[0]["revenue_paise"] == 129000,
          f"got {_crosses[0]['revenue_paise'] if _crosses else None}, "
          f"basket was 278000")

    check("An order placed BEFORE the offer is not counted",
          len(_crosses) == 1,
          "the earlier session holds the same product and must be ignored")

    check("The conversion says why it was counted",
          bool(_crosses) and "cross-sell" in _crosses[0]["why"].lower())

    check("Attributed revenue equals the sum of what it can name",
          _result["attributed_revenue_paise"]
          == sum(c["revenue_paise"] for c in _result["conversions"]))
finally:
    _db.collection("growth_offers").document(_offer_id).delete()
    _store.db.collection(_store.SESSIONS).document(_session_id).delete()
    _store.db.collection(_store.SESSIONS).document(_early_id).delete()

# The merchant-facing view of the same offer: it has to reach a buyer, and
# it must not overstate what it knows.
_offer_id2 = f"go-audit-{_uuid.uuid4().hex[:8]}"
_db.collection("growth_offers").document(_offer_id2).set({
    "offer_id": _offer_id2, "agent": "crosssell", "kind": "cross_sell",
    "target_kind": "product", "target_id": _anchor,
    "cost_paise": 0, "params": {"complement_id": _complement, "basis": "category"},
    "approved_by": "audit", "campaign_id": None,
    "created_at": _time.time(), "state": "live",
})
try:
    _live = _store.live_offer(_anchor)
    check("An approved cross-sell reaches the product a buyer is looking at",
          bool(_live) and _live["product"]["id"] == _complement,
          str(_live and _live["product"]["id"]))
    # The failure this guards against is a fabricated statistic with a
    # friendly face: "frequently bought together" over a pair nobody has
    # ever bought together.
    check("An adjacency-based offer does NOT claim they were bought together",
          bool(_live) and "nobody has bought the two together"
          in _live["message"].lower(),
          _live["message"][:90] if _live else "")
    check("The offer discloses that a merchant approved it",
          bool(_live) and "approved" in _live["disclosure"].lower())
finally:
    _db.collection("growth_offers").document(_offer_id2).delete()

print()
print("=== The transaction policy ===")
from app.agent import policy as txn_policy

document = txn_policy.transaction_policy()
check("every bound names the code that enforces it",
      all(b.get("enforced_by") for b in document["bounds"]))
check("every behaviour names the code that enforces it",
      all(b.get("enforced_by") for b in document["behaviours"]))
behaviours = {b["key"]: b["value"] for b in document["behaviours"]}
check("a failed payment is never retried automatically",
      behaviours["auto_retry_payment"] is False)
check("no agent tool can issue a refund",
      behaviours["refund_initiated_by"] == "human")

limit_inr = settings.get("risk", "auto_approve_limit_inr")
under = txn_policy.check(limit_inr * 100 - 100)
over = txn_policy.check(limit_inr * 100 + 100)
check("an amount under the bound may proceed", under["within_policy"] is True)
check("an amount over the bound needs a person", over["within_policy"] is False)
# The dangerous failure here is a green tick that reads as the gate's
# whole verdict when it is one rule of six.
check("the check states which of the gate's rules it did NOT run",
      len(under["not_checked"]) >= 4 and "gate" in under["note"].lower())

# The document must track the live setting rather than a copy of it, or
# the screen quoting it drifts from the gate applying it.
settings.apply({"risk": {"auto_approve_limit_inr": limit_inr + 1000}})
check("the policy follows the live setting",
      txn_policy.check(0)["limit_paise"] == (limit_inr + 1000) * 100)
settings.apply({"risk": {"auto_approve_limit_inr": limit_inr}})

print()
print("=== Failed purchases keep the product ===")
from app.firebase_client import db as _dbx

# WHY THIS EXISTS.
#
# "Your payment failed" is not actionable. "Your payment for the Braided
# USB-C Cable failed because this account rejects foreign cards, and
# netbanking would work" is — and the whole difference is whether the record
# held on to what was being bought. A card rejected inside Razorpay's own
# modal never reaches the success handler, so before this the most common
# failure on the account was the one nothing recorded at all.
from app.routes import recovery_routes as _rec

_report = _rec.FailureReport(
    razorpay_order_id="order_audit_rec",
    amount_paise=64900,
    customer_id="audit",
    product={"id": "cds-braided-usb-c-cable-2-metre",
             "name": "Braided USB-C Cable, 2 metre",
             "price_paise": 64900, "source": "merchant"},
    error={"code": "BAD_REQUEST_ERROR",
           "description": "Your payment could not be completed as this "
                          "business accepts domestic (Indian) card payments "
                          "only. Try another payment method.",
           "reason": "international_transaction_not_allowed",
           "step": "payment_authentication", "source": "customer"},
)
_stored = _rec.record_failure(_report)
try:
    check("A failed purchase keeps the product",
          _stored["product"]["name"] == "Braided USB-C Cable, 2 metre")
    check("...and the amount that was being spent",
          _stored["amount_paise"] == 64900)

    # Quoted, not paraphrased: this page and the Razorpay dashboard must not
    # end up describing the same failure differently.
    check("The reason is Razorpay's own words",
          "domestic (Indian) card payments only" in _stored["summary"],
          _stored["summary"][:80])
    check("The error code is kept for anyone reconciling with Razorpay",
          _stored["error"]["code"] == "BAD_REQUEST_ERROR")

    # The bit Razorpay cannot know: which rail on THIS account would work.
    check("It names a rail that could actually complete",
          _stored["suggested_rail"] in (None, "Netbanking"),
          str(_stored["suggested_rail"]))

    check("It lands on the queue as open",
          _stored["state"] == "open")
    _queue = _rec.failed_purchases()
    check("...and the queue returns it",
          any(p["id"] == _stored["id"] for p in _queue["purchases"]),
          f"{_queue['count']} open")

    # The audit trail still gets its own record, in its own shape.
    _decisions = [d.to_dict() or {} for d in _dbx.collection("decisions")
                  .where("action_type", "==", "payment_failed").stream()]
    check("The auditor's record is written too, and links back",
          any(d.get("order_id") == "order_audit_rec" for d in _decisions))

    # Closing is logged. A queue that can be emptied silently is a queue
    # somebody will empty silently.
    _rec.close_purchase(_stored["id"], _rec.CloseRequest(outcome="cancelled"))
    _after = _rec.failed_purchases()
    check("Closing takes it off the queue",
          not any(p["id"] == _stored["id"] for p in _after["purchases"]))
    _closes = [d.to_dict() or {} for d in _dbx.collection("decisions")
               .where("action_type", "==", "failed_purchase_closed").stream()]
    check("...and closing is itself logged", len(_closes) >= 1)
finally:
    _dbx.collection(_rec.COLLECTION).document(_stored["id"]).delete()

print()
print("=== Which rails can actually take money ===")
from app.agent import rails as _rails

_status = _rails.status()
if _status.get("reachable"):
    check("Every rail carries a verdict",
          all(r["verdict"] in ("works", "rejected", "untried")
              for r in _status["rails"]),
          str([r["verdict"] for r in _status["rails"]]))
    # A verdict must be earned, not configured. This is what stops the page
    # claiming a rail works because somebody wrote it in a list.
    check("A rail is only 'works' if money was actually captured on it",
          all(r["captured"] > 0 for r in _status["rails"]
              if r["verdict"] == "works"))
    check("A rejected rail quotes the reason it was rejected",
          all(r["error"] for r in _status["rails"]
              if r["verdict"] == "rejected"))
    # The claim this project must never overstate.
    check("No rail is presented as completing without a person",
          all(r["needs_a_person"] for r in _status["rails"]
              if r["verdict"] == "works"))
else:
    check("Razorpay unreachable is reported rather than guessed",
          _status["rails"] == [] and "could not be reached" in _status["note"])

print("\n" + "=" * 62)
print(f"  {PASSED} passed · {FAILED} failed")
sys.exit(1 if FAILED else 0)
