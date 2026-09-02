"""
The refinement path, tested where it can be tested reliably.

Driving this through the browser proved unreliable — each message opens a new
socket and a follow-up sent before the previous run settles abandons it
instead of refining, so the DOM shows stale results and the test reads a lie.
These are the same code paths without that ambiguity.

The bug this is really guarding: the "rating" sorter closes over `bias`,
which used to be assigned only on the fresh-search branch, so refining a
rating-ranked run raised NameError. The rule-derived default made rating the
common case, which is what turned it from latent into constant.
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

from app.agent import refine as refiner
from app.agent.ollama_agent import fast_intent, effective_priority, merge_model_intent

print("\n=== A. Does a follow-up refine or start over? ===")
CASES = [
    ("running shoes under 3000", "red", True, "a colour already understood as an attribute"),
    # "ones" is a filler pronoun, not a new product — the parser sees through
    # it to the attribute, which is what makes natural phrasing work.
    ("running shoes under 3000", "red ones", True, "filler word, real attribute"),
    ("running shoes under 3000", "under 2000", True, "tightening the budget"),
    ("running shoes under 3000", "leather jacket", False, "a different product"),
    ("sandisk 128gb pendrive", "black", True, "an attribute"),
]
for prev, follow, expected, why in CASES:
    d = refiner.parse(follow, prev)
    check(f"{follow!r} after {prev!r} -> {'refine' if expected else 'new search'}",
          bool(d.get("refine")) == expected, why)

print("\n=== B. The sorter that used to crash ===")
# Exactly what the route does, on the branch where the search block is skipped.
intent = fast_intent("running shoes under 3000")
check("A fresh intent carries quality_bias", "quality_bias" in intent,
      repr(intent.get("quality_bias")))

refining_intent = dict(intent)          # what the refine branch starts from
check("A refined intent still carries it", "quality_bias" in refining_intent)

bias = (refining_intent.get("quality_bias") or "neutral").lower()
from app.agent import quality as _quality

sort_keys = {
    "value": lambda p: _quality.value_key(p, 0),
    "discount": lambda p: (-(p.get("discount_percent") or 0), p["price_paise"]),
    "price": lambda p: (p["price_paise"],),
    "delivery_days": lambda p: (p.get("delivery_days") or 99, p["price_paise"]),
    "rating": lambda p: (-p["price_paise"],) if bias == "best" else (p["price_paise"],),
}
products = [
    {"id": "a", "price_paise": 250000, "discount_percent": 5, "delivery_days": 4},
    {"id": "b", "price_paise": 120000, "discount_percent": 30, "delivery_days": 9},
    {"id": "c", "price_paise": 300000, "discount_percent": 0, "delivery_days": 2},
]
for key in ["value", "rating", "price", "discount", "delivery_days"]:
    try:
        order = [p["id"] for p in sorted(products, key=sort_keys[key])]
        check(f"Sorting by {key!r} on the refine path", True, " < ".join(order))
    except NameError as exc:
        check(f"Sorting by {key!r} on the refine path", False, str(exc))

eff = effective_priority(intent["priority"])
check("The default priority resolves to a real sorter", eff in sort_keys, eff)

print("\n=== C. The model stays an enrichment, not a dependency ===")
check("A failed model call leaves the intent usable",
      merge_model_intent(intent, None) == intent)

enriched = merge_model_intent(intent, {"priority": "discount",
                                       "requirements": ["waterproof"]})
# Reversed deliberately. The model reads any budget as "cheapest", which
# handed back a used drive over a 4.73-star one, so priority is decided by
# the rules and the model does not get to overrule them.
check("The model's priority is ignored in favour of the rules",
      enriched["priority"] == intent["priority"],
      f"model said discount, rules said {intent['priority']}")
check("The model's requirements are added, not replacing the rules'",
      "waterproof" in enriched["requirements"], str(enriched["requirements"]))
check("The rules keep the search phrase and the ceiling",
      enriched["category"] == intent["category"]
      and enriched["max_price_paise"] == intent["max_price_paise"])

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
