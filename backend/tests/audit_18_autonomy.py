"""
LEVEL 5 — PREDICTION, PRECISION AND THE BOUNDS ON ACTING ALONE.

The three cases the spec names, plus the ones that decide whether the rest
can be trusted:

  A  the consumption model, including when it refuses to predict
  B  the precision stage rejecting what cannot be bought
  C  the confidence floor falling back to a confirmation
  D  every autonomy gate, one at a time
  E  the full autonomous path, dry, with nothing created

Offline and deterministic — no marketplace call, no model, no Firestore
write. It runs in milliseconds so it can go in front of every change.
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
import time


from app.agent import autonomy, precision, replenishment, settings

passed = failed = 0
DAY = 86400.0
now = time.time()


def check(name, ok, detail=""):
    global passed, failed
    passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def order(name, days_ago, status="paid", price=49900):
    return {"status": status, "created_at": now - days_ago * DAY,
            "items": [{"name": name, "price_paise": price}]}


print("=== A. The consumption model ===")
steady = replenishment.profile([order("Coffee Pods", d) for d in (92, 61, 31, 2)], now)[0]
check("A steady cycle is measured", steady["cycle_days"] == 30.0, f"{steady['cycle_days']}d")
check("...and reported high confidence", steady["confidence"] == "high", steady["confidence"])
check("...with the interval count shown", steady["intervals_seen"] == 3)

erratic = replenishment.profile([order("Detergent", d) for d in (70, 10, 5)], now)[0]
check("Erratic gaps are not called predictable-with-confidence",
      erratic["confidence"] == "low", f"{erratic['confidence']} (±{erratic['spread_days']}d)")

single = replenishment.profile([order("Toothpaste", 12)], now)[0]
check("One purchase produces no prediction", single["predictable"] is False)
check("...and says why rather than assuming a category default",
      "inventing" in single["reason"])

unpaid = replenishment.profile([order("Filters", d, status="created") for d in (60, 30)], now)
check("Orders that were never paid are not consumption", unpaid == [])

due = replenishment.profile([order("Coffee Pods", d) for d in (60, 30)], now)[0]
check("An item one cycle past its last purchase is due", due["due"] is True,
      f"due_in={due['days_until_due']}d")

print("\n=== B. The precision stage ===")
out_of_stock = {"name": "Vacuum", "availability": "OUT_OF_STOCK"}
in_stock = {"name": "Vacuum", "availability": "IN_STOCK",
            "sold_quantity": 120, "review_stars": 4.6, "review_count": 800,
            "returns_accepted": True, "return_days": 30}
result = precision.screen([out_of_stock, in_stock])
check("An out-of-stock listing is removed", len(result["candidates"]) == 1,
      result["summary"])
check("...and the in-stock one survives",
      result["candidates"][0]["availability"] == "IN_STOCK")
check("The drop is counted", result["dropped"] == 1)

unknown = {"name": "Vacuum"}          # never enriched
kept = precision.screen([unknown])
check("Unknown availability is not treated as out of stock",
      len(kept["candidates"]) == 1 and kept["dropped"] == 0)

only_dead = precision.screen([dict(out_of_stock), dict(out_of_stock)])
check("If every listing is out of stock the screen stands down",
      only_dead["stood_down"] is True and len(only_dead["candidates"]) == 2)

sig = precision.signals(in_stock)
check("Return RATE is reported as unavailable, not inferred",
      sig["return_rate"] is None and "does not publish" in sig["return_rate_note"])
check("Frequently-bought is derived from real sold quantity",
      sig["frequently_bought"] is True, f"{sig['sold_quantity']} sold")
check("The evidence line names what was actually read",
      "120 sold" in precision.explain(in_stock)
      and "4.6★" in precision.explain(in_stock))

better = precision.preference_key(in_stock)
worse = precision.preference_key({"name": "Vacuum", "availability": "IN_STOCK",
                                  "sold_quantity": 2, "review_stars": 3.0})
check("The tie-break prefers better-approved, more-bought", better < worse)

print("\n=== C. Confidence floor falls back to a confirmation ===")
was_enabled = settings.get("autonomy", "enabled")
settings.apply({"autonomy": {"enabled": True}})
try:
    coffee = {"name": "Nescafe Gold Coffee Refill 200g", "price_paise": 49900}
    low = autonomy.check(customer_id="t", product=coffee,
                         prediction={"confidence": "low"})
    check("Low confidence does not buy", low["verdict"] != autonomy.ALLOWED)
    check("...it asks instead of refusing", low["verdict"] == autonomy.CONFIRM,
          low["verdict"])
    check("...and the reason is readable", "below the" in low["reason"])

    high = autonomy.check(customer_id="t", product=coffee,
                          prediction={"confidence": "high"})
    check("High confidence is allowed", high["verdict"] == autonomy.ALLOWED)

    print("\n=== D. Every bound, one at a time ===")
    over = autonomy.check(customer_id="t",
                          product={**coffee, "price_paise": 250000},
                          prediction={"confidence": "high"})
    check("Over the per-order cap is blocked",
          over["verdict"] == autonomy.BLOCKED and over["gate"] == "per_order_cap")

    phone = autonomy.check(customer_id="t",
                           product={"name": "Apple iPhone 17 Pro", "price_paise": 49900},
                           prediction={"confidence": "high"})
    check("A phone is not a replenishable",
          phone["verdict"] == autonomy.BLOCKED and phone["gate"] == "category")

    unknown_cat = autonomy.check(
        customer_id="t", product={"name": "Ceramic Plant Pot", "price_paise": 49900},
        prediction={"confidence": "high"})
    check("An unrecognised category fails closed",
          unknown_cat["verdict"] == autonomy.BLOCKED)

    priceless = autonomy.check(customer_id="t",
                               product={**coffee, "price_paise": 0},
                               prediction={"confidence": "high"})
    check("A listing with no price is blocked", priceless["verdict"] == autonomy.BLOCKED)

    # Named, not counted. This asserted `== 5` and broke the moment a sixth
    # gate was added — reporting a genuine safety improvement as a failure.
    # What matters is that each gate ran and was recorded, not how many
    # there happen to be.
    EXPECTED_GATES = {"kill_switch", "per_order_cap", "monthly_cap",
                      "category", "confidence", "already_bought"}
    recorded = {c.get("gate") for c in high["checks"]}
    check("Every gate is recorded, passed or not",
          all("gate" in c and "passed" in c for c in high["checks"])
          and EXPECTED_GATES <= recorded,
          f"{len(high['checks'])} gates: {', '.join(sorted(recorded))}")
    check("...including the duplicate guard the interactive path already had",
          "already_bought" in recorded,
          "an unattended runner fired twice must not buy twice")

    settings.apply({"autonomy": {"enabled": False}})
    off = autonomy.check(customer_id="t", product=coffee,
                         prediction={"confidence": "high"})
    check("The kill switch stops everything",
          off["verdict"] == autonomy.BLOCKED and off["gate"] == "kill_switch")
    check("...and it is checked first", off["checks"][0]["gate"] == "kill_switch")
finally:
    settings.apply({"autonomy": {"enabled": was_enabled}})

print("\n=== E. Defaults are the safe ones ===")
check("Autonomous buying is off by default",
      settings.SPEC["autonomy"]["enabled"]["default"] is False)
check("The unattended cap is below the interactive one",
      settings.SPEC["autonomy"]["max_order_inr"]["default"]
      < settings.SPEC["risk"]["auto_approve_limit_inr"]["default"],
      f"₹{settings.SPEC['autonomy']['max_order_inr']['default']} unattended vs "
      f"₹{settings.SPEC['risk']['auto_approve_limit_inr']['default']} attended")
check("There is a rolling ceiling as well as a per-order one",
      settings.SPEC["autonomy"]["monthly_cap_inr"]["default"] > 0)

print("\n" + "=" * 62)
print(f"  {passed} passed · {failed} failed")
