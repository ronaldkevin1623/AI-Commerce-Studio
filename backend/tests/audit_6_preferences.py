"""
Does the profile describe real purchases, and does it stay in its lane?

The risk with personalisation is not that it fails — it is that it quietly
succeeds at the wrong thing: inventing a taste from two data points, or
overriding what someone just asked for because of what they did last month.
Both are tested here.
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

from app.agent import preferences

print("\n=== A. Nothing is claimed without evidence ===")
p = preferences.build(None)
check("No customer means no profile", p["confidence"] == "none", p["summary"][:60])

fake_orders = [
    {"customer_id": "u1", "status": "paid", "razorpay_payment_id": "pay_1",
     "amount_paise": 30000, "product_name": "USB C Cable Braided",
     "source": "ebay", "items": [{"condition": "New"}]},
    {"customer_id": "u1", "status": "created", "amount_paise": 900000,
     "product_name": "Laptop", "source": "ebay", "items": [{"condition": "New"}]},
]
p = preferences.build("u1", fake_orders)
check("An abandoned order is not treated as a purchase",
      p["purchases"] == 1, f"{p['purchases']} counted from 2 orders")
check("One purchase is too few to act on", p["confidence"] == "thin",
      p["summary"][:70])
check("A thin profile changes nothing",
      preferences.apply([{"id": "a"}, {"id": "b"}], p)["applied"] is False)

paid = [{"customer_id": "u2", "status": "paid",
         "razorpay_payment_id": f"pay_{i}", "amount_paise": amt,
         "product_name": name, "source": "ebay",
         "items": [{"condition": "New"}]}
        for i, (amt, name) in enumerate([
            (31955, "USB C Type C Charger Cable Fast Charging"),
            (33117, "HeavyDuty USB Type C Charging Cable Braided"),
            (35690, "Braided USB C Charging Cable Fast"),
        ])]
p = preferences.build("u2", paid)
check("Three purchases become a usable profile", p["confidence"] == "usable",
      p["summary"])
check("The typical spend is the real median",
      p["median_paise"] == 33117, f"₹{p['median_paise']/100:,.2f}")
check("The observed condition is recorded", p["conditions"] == ["New"],
      str(p["conditions"]))
check("Recurring words are learned from the names",
      "cable" in p["keywords"] and "charging" in p["keywords"],
      str(p["keywords"]))

print("\n=== B. It breaks ties, it does not overrule ===")
candidates = [
    {"id": "far",  "name": "Premium Laptop Stand", "price_paise": 900000,
     "condition": "Used", "source": "merchant"},
    {"id": "near", "name": "Braided USB C Charging Cable", "price_paise": 33000,
     "condition": "New", "source": "ebay"},
]
out = preferences.apply(list(candidates), p)
check("A listing resembling their history moves up",
      out["applied"] and out["candidates"][0]["id"] == "near",
      [c["id"] for c in out["candidates"]])
check("It explains itself", bool(out["note"]), str(out["note"])[:80])
check("Nothing is dropped", len(out["candidates"]) == len(candidates))

same = [{"id": "a", "name": "Cable", "price_paise": 33000, "condition": "New",
         "source": "ebay"},
        {"id": "b", "name": "Cable", "price_paise": 33000, "condition": "New",
         "source": "ebay"}]
check("Identical affinity means no claim of reordering",
      preferences.apply(same, p)["applied"] is False)

print("\n=== C. Against the real database ===")
from app.firebase_client import db
orders = [d.to_dict() or {} for d in db.collection("orders").get()]
buyers = {o.get("customer_id") for o in orders
          if o.get("status") == "paid" and o.get("razorpay_payment_id")}
print(f"  {len(buyers)} customer(s) with a real captured payment")
for cid in list(buyers)[:3]:
    real = preferences.build(cid, orders)
    print(f"    {cid}: {real['purchases']} purchases · {real['confidence']}")
    print(f"      {real['summary']}")
check("A real profile can be built without error", True)

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
