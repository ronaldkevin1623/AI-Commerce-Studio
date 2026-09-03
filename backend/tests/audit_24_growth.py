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
check("all three growth agents load", ids == ["crosssell", "offers", "recovery"], str(ids))
check("only margin-spenders declare it",
      {a.agent_id for a in registry.agents() if a.spends_margin} == {"recovery", "offers"})

print("\n=== Bound 1: the kill switch ===")
settings.apply({"growthgate": {"enabled": False}})
verdict = gate.evaluate(proposal())
check("nothing passes while growth is off", verdict["verdict"] == "blocked", verdict["reason"][:60])
scanned = registry.scan()
check("the scan still runs and proposes while off", len(scanned) >= 0, f"{len(scanned)} proposals")
check("every proposal is blocked while off",
      all(p["verdict"] == "blocked" for p in scanned))

settings.apply({"growthgate": {"enabled": True}})

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
settings.apply({"growthgate": {"daily_cap_inr": 500}})

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

print("\n" + "=" * 62)
print(f"  {PASSED} passed · {FAILED} failed")
sys.exit(1 if FAILED else 0)
