"""
Can the explanation say something untrue?

The old failure was not an invented product or an invented number — it was a
false relationship between real ones ("slightly over budget" about an item
under the ceiling). So these tests do not check that the words are grounded;
they check that every claim is *true of the data it was computed from*.

The strongest case is the last one: the exact scenario that produced the
false claim, asserted against the real numbers.
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
import sys, re, itertools, random

PASS, FAIL = [], []
def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

from app.agent import explain

print("\n=== A. The sentence that used to be wrong ===")
# ₹649 under a ₹800 ceiling. The model called this "slightly over budget".
cands = [
    {"id": "m", "name": "Braided USB-C Cable, 2 metre", "price_paise": 64900,
     "condition": "New", "condition_id": "1000", "source": "merchant",
     "merchant_name": "Commerce Studio Demo Store", "seller_feedback": 100,
     "seller_feedback_count": 5000, "returns_accepted": True},
    {"id": "e", "name": "USB C Cable Fast Charge", "price_paise": 32000,
     "condition": "New", "condition_id": "1000", "source": "ebay",
     "seller_feedback": 98.9, "seller_feedback_count": 900},
]
out = explain.choose(cands, "rating", budget_paise=80000, requirements=["2 metre"])
print(f"    {out['reason']}")
check("It does not claim the item is over budget",
      "over your" not in out["reason"])
check("It states the comparison correctly",
      "under your ₹800" in out["reason"], out["reason"])
check("It is marked as derived", out.get("derived") is True)
check("The reason does not repeat the product name",
      not out["reason"].lower().startswith("braided usb-c cable"), out["reason"])

print("\n=== B. Superlatives are verified, not asserted ===")
pool = [
    {"id": "a", "name": "Cable A", "price_paise": 30000, "seller_feedback": 90,
     "discount_percent": 10, "delivery_days": 5},
    {"id": "b", "name": "Cable B", "price_paise": 20000, "seller_feedback": 99,
     "discount_percent": 40, "delivery_days": 2},
]
r = explain.choose(pool, "price")
check("The cheapest is called cheapest", "cheapest" in r["reason"],
      r["reason"])
check("...and it really is the cheapest",
      r["product"]["price_paise"] == min(p["price_paise"] for p in pool))

r = explain.choose(pool, "rating")
check("The top feedback is named accurately",
      "99%" in r["reason"] and r["product"]["id"] == "b", r["reason"])

r = explain.choose(pool, "discount")
check("The biggest discount is named accurately",
      "40% off" in r["reason"] and r["product"]["id"] == "b", r["reason"])

r = explain.choose(pool, "delivery_days")
check("The fastest delivery is named accurately",
      "2 days" in r["reason"] and r["product"]["id"] == "b", r["reason"])

print("\n=== C. It only claims requirements the title actually contains ===")
r = explain.choose(
    [{"id": "x", "name": "SanDisk Ultra 128GB Flash Drive", "price_paise": 80000,
      "seller_feedback": 99}],
    "rating", requirements=["128gb", "waterproof", "good camera quality"])
check("A requirement present in the title is claimed",
      "128gb" in r["reason"].lower(), r["reason"])
check("A requirement absent from the title is not claimed",
      "waterproof" not in r["reason"].lower())
check("A multi-word judgement is left to the relevance screen",
      "camera" not in r["reason"].lower())

print("\n=== D. The venue claim is exclusive only when it is ===")
r = explain.choose([cands[0], cands[1]], "rating")
check("'only one that can be delivered' when it is the sole merchant item",
      "only one" in r["reason"], r["reason"])

two_merchants = [dict(cands[0]), dict(cands[0], id="m2", name="Other store item",
                                      price_paise=70000, seller_feedback=99)]
r = explain.choose(two_merchants, "rating")
check("Not claimed when another store item exists",
      "only one" not in r["reason"], r["reason"])

print("\n=== E. Nothing is said when nothing distinguishes ===")
flat = [{"id": "p", "name": "Thing", "price_paise": 10000},
        {"id": "q", "name": "Thing", "price_paise": 10000}]
r = explain.choose(flat, "rating")
check("It falls back to an honest non-claim",
      "closest match" in r["reason"], r["reason"])
check("The fallback does not name the product either",
      not r["reason"].startswith("Thing"), r["reason"])

print("\n=== F. Fuzzing: no superlative survives that is not true ===")
random.seed(7)
violations = []
for _ in range(400):
    n = random.randint(2, 6)
    pool = [{
        "id": str(i),
        "name": f"Item {i}",
        "price_paise": random.randrange(1000, 200000),
        "seller_feedback": random.choice([0, 80, 90, 95, 99, 100]),
        "discount_percent": random.choice([0, 5, 20, 50]),
        "delivery_days": random.choice([1, 3, 7, 99]),
        "condition": random.choice(["New", "Used", ""]),
    } for i in range(n)]
    budget = random.choice([0, 50000, 150000, 250000])
    for pr in explain.PRIORITIES:
        res = explain.choose([dict(p) for p in pool], pr, budget_paise=budget)
        c, reason = res["product"], res["reason"]

        if "cheapest" in reason and any(
                p["price_paise"] < c["price_paise"] for p in pool):
            violations.append(("cheapest", reason))
        if "highest seller feedback" in reason and any(
                p["seller_feedback"] > c["seller_feedback"] for p in pool):
            violations.append(("feedback", reason))
        if "biggest discount" in reason and any(
                p["discount_percent"] > c["discount_percent"] for p in pool):
            violations.append(("discount", reason))
        if "fastest delivery" in reason and any(
                p["delivery_days"] < c["delivery_days"] for p in pool):
            violations.append(("delivery", reason))

        price = c["price_paise"]
        if budget:
            if "over your" in reason and price <= budget:
                violations.append(("false over-budget", reason))
            if "under your" in reason and price > budget:
                violations.append(("false under-budget", reason))
        else:
            if "your ₹" in reason:
                violations.append(("budget claimed with no budget", reason))

check("1,600 generated comparisons, no false claim",
      not violations, f"{len(violations)} violations"
      + (f" e.g. {violations[0]}" if violations else ""))

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
