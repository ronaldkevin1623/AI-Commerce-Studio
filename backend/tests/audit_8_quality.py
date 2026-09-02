"""
Does the agent still fall for the cheap bad one?

The question this feature exists to answer: given a budget, does it spend it
on something good, or does it hand back the cheapest listing and call that a
result. Also tested is the quieter failure — treating "no reviews" as "bad
reviews", which would punish listings for eBay's catalogue coverage rather
than for anything about them.
"""
import os
import sys
from pathlib import Path

# The backend package, found from this file rather than from where the
# runner happened to be invoked — so a suite works the same whether it is
# run on its own, through run_all.py, or from any directory.
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
# The app resolves serviceAccountKey.json and the .env relative to the
# working directory, so a suite has to stand where the server stands. Doing
# it here rather than in the runner keeps every suite runnable on its own.
os.chdir(BACKEND)
sys.stdout.reconfigure(encoding="utf-8")

PASS, FAIL = [], []
def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

from app.agent import quality, explain

print("\n=== A. Nothing is invented ===")
bare = {"name": "Mystery item", "price_paise": 10000}
a = quality.assess(bare)
check("A listing with no signals scores nothing, not a default",
      a["score"] is None and a["confidence"] == "unknown", str(a))

check("No feedback means unknown, not zero",
      quality.shrunk_feedback(None, 0) is None)

print("\n=== B. Volume is weighed, not just percentage ===")
thin = quality.shrunk_feedback(100.0, 72)
thick = quality.shrunk_feedback(99.8, 400270)
check("100% from 72 ratings scores below 99.8% from 400,270",
      thin < thick, f"{thin:.2f} vs {thick:.2f}")

tiny = quality.shrunk_feedback(100.0, 1)
check("A single perfect rating barely moves off the baseline",
      tiny < 97.5, f"{tiny:.2f}")

print("\n=== C. The cheap bad one does not win ===")
cheap_bad = {
    "id": "cheap", "name": "USB C Cable", "price_paise": 15000,
    "seller_feedback": 91.0, "seller_feedback_count": 40,
    "condition": "Used", "condition_id": "3000",
}
dearer_good = {
    "id": "good", "name": "USB C Cable", "price_paise": 45000,
    "seller_feedback": 99.8, "seller_feedback_count": 400270,
    "condition": "New", "condition_id": "1000",
    "review_stars": 4.7, "review_count": 298,
    "top_rated_seller": True, "returns_accepted": True,
}
pool = [cheap_bad, dearer_good]
quality.annotate(pool)
print(f"    cheap: {cheap_bad['quality']['score']}  "
      f"good: {dearer_good['quality']['score']}")

r = explain.choose([dict(p) for p in pool], "value", budget_paise=80000)
check("Within budget, the better one is chosen over the cheaper",
      r["product"]["id"] == "good", f"chose {r['product']['id']}")
check("The explanation cites the real evidence",
      "298 reviews" in r["reason"] or "4.7 stars" in r["reason"], r["reason"])

r = explain.choose([dict(p) for p in pool], "price")
check("Asking for cheapest still gives cheapest",
      r["product"]["id"] == "cheap", f"chose {r['product']['id']}")

print("\n=== D. Similar quality is settled on price ===")
twin_a = dict(dearer_good, id="a", price_paise=45000)
twin_b = dict(dearer_good, id="b", price_paise=39000)
r = explain.choose([dict(twin_a), dict(twin_b)], "value", budget_paise=80000)
check("With a budget stated, the one that uses it wins",
      r["product"]["id"] == "a",
      f"chose {r['product']['id']} — Rs{r['product']['price_paise']/100:,.0f} "
      f"of a Rs800 budget")

r = explain.choose([dict(twin_a), dict(twin_b)], "value", budget_paise=0)
check("With no budget stated, the cheaper of equals wins",
      r["product"]["id"] == "b", f"chose {r['product']['id']}")

r = explain.choose([dict(twin_a), dict(twin_b)], "price", budget_paise=80000)
check("Asking for cheapest still overrides the budget preference",
      r["product"]["id"] == "b", f"chose {r['product']['id']}")

print("\n=== E. Unrated is not punished as bad ===")
unrated = dict(dearer_good, id="unrated", review_stars=None, review_count=None)
scored = quality.assess(unrated)
check("Losing reviews does not collapse the score",
      scored["score"] > 80, f"{scored['score']} without reviews")
check("...but confidence drops", scored["confidence"] != "high",
      scored["confidence"])

print("\n=== F. Live: does it pick something good within budget? ===")
from app.agent.catalog import search_catalog
from app.agent.ebay_client import enrich_reviews

items = search_catalog("sandisk 128gb pendrive", 200000)
items = enrich_reviews(items, 8)
quality.annotate(items)

r = explain.choose(items, "value", budget_paise=200000,
                   requirements=["sandisk", "128gb"])
pick = r["product"]
cheapest = min(items, key=lambda i: i.get("price_paise") or 0)
print(f"    picked   Rs{pick['price_paise']/100:,.0f}  "
      f"score {pick['quality']['score']}  {str(pick['name'])[:40]}")
print(f"    cheapest Rs{cheapest['price_paise']/100:,.0f}  "
      f"score {cheapest['quality']['score']}  {str(cheapest['name'])[:40]}")
print(f"    reason: {r['reason'][:150]}")

check("The pick is within budget", pick["price_paise"] <= 200000)
check("The pick is at least as good as the cheapest",
      (pick["quality"]["score"] or 0) >= (cheapest["quality"]["score"] or 0))

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
