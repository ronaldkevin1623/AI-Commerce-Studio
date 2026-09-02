"""
Are stated attributes actually enforced — and do they stand down safely?

The failure being guarded: "laptop stand aluminium" answered with a metal
stand, and "braided usb-c cable 2 metre" with a cable that was neither. Both
scored well on quality and won, because attributes only nudged the ranking.

The opposite failure matters as much. Enforcing an attribute nobody offers
would empty the page, and "no results" is a worse answer than "nothing here
is aluminium, here is the closest thing".
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

from app.agent import attributes as A

print("\n=== A. What counts as a stated attribute ===")
cases = [
    ("laptop stand aluminium under 2500", {"aluminium"}),
    ("cotton t shirt under 1000", {"cotton"}),
    ("nothing 3a mobile black under 30000", {"black"}),
    ("sunglasses polarized under 2000", {"polarized"}),
    ("braided usb-c cable 2 metre under 800", {"braided", "2 metre"}),
    ("wireless earbuds under 3000", {"wireless"}),
    # No concrete attribute: "good" and "best" cannot be checked against a
    # title, so they must not become conditions.
    ("good quality headphones under 3000", set()),
]
for query, expected in cases:
    got = {a["text"] for a in A.required(query)}
    check(f"{query[:38]!r} -> {sorted(expected) or 'none'}",
          got == expected, f"got {sorted(got)}")

print("\n=== B. Units are matched however they are written ===")
attrs = A.required("cable 2 metre")
for title, expected in [
    ("Braided USB C Cable 2m Fast Charge", True),
    ("Nylon Braided Cable 2 Meter Long", True),
    ("USB C Cable 2 METRE heavy duty", True),
    ("USB C Cable 1m Short", False),
    ("USB C Cable 100W Fast Charging with LED", False),
]:
    got = all(A.satisfied(title, a) for a in attrs)
    check(f"{'matches' if expected else 'does not match'}: {title[:40]!r}",
          got == expected)

print("\n=== C. Spelling variants of the same attribute ===")
alu = A.required("aluminium stand")[0]
check("'aluminium' matches an 'aluminum' listing",
      A.satisfied("Adjustable Aluminum Laptop Riser", alu))
pol = A.required("polarized sunglasses")[0]
check("'polarized' matches a 'polarised' listing",
      A.satisfied("Polarised UV400 Sunglasses", pol))

print("\n=== D. Enforcement narrows to what was asked for ===")
pool = [
    {"name": "Multifunction Adjustable Aluminium Laptop Stand"},
    {"name": "Aluminum Alloy Laptop Riser Stand"},
    {"name": "360 Rotating Metal Laptop Stand Riser"},
    {"name": "Plastic Foldable Laptop Stand"},
]
out = A.enforce(list(pool), A.required("laptop stand aluminium"))
check("Only the aluminium ones survive", len(out["candidates"]) == 2,
      [c["name"][:34] for c in out["candidates"]])
check("It reports what it held to", "aluminium" in (out["note"] or ""),
      out["note"])
check("The dropped ones say which attribute they missed",
      pool[2].get("attribute_miss") == "aluminium")

print("\n=== E. It stands down when the market has none ===")
thin = [
    {"name": "360 Rotating Metal Laptop Stand"},
    {"name": "Plastic Foldable Laptop Stand"},
    {"name": "Wooden Laptop Riser"},
]
out = A.enforce(list(thin), A.required("laptop stand aluminium"))
check("Nothing is dropped when nothing qualifies",
      len(out["candidates"]) == 3, f"{len(out['candidates'])}/3")
check("And it says so rather than staying silent",
      "too few" in (out["note"] or ""), out["note"])

print("\n=== F. Attributes combine, each on its own evidence ===")
mixed = [
    {"name": "Braided USB C Cable 2m"},
    {"name": "Braided USB C Cable 1m"},
    {"name": "Plain USB C Cable 2m"},
    {"name": "Plain USB C Cable 3m"},
]
out = A.enforce(list(mixed), A.required("braided usb-c cable 2 metre"))
kept = [c["name"] for c in out["candidates"]]
check("Both attributes applied together", kept == ["Braided USB C Cable 2m"],
      str(kept))

print("\n=== G. Live: the two picks that used to be wrong ===")
from app.agent.ollama_agent import (
    fast_intent, screen_relevance, effective_priority,
)
from app.agent.catalog import search_catalog
from app.agent import quality, explain
from app.agent.ebay_client import enrich_reviews

for query, must_have in [
    ("braided usb-c cable 2 metre under 800", ["braided"]),
    ("laptop stand aluminium under 2500", ["alumin"]),
]:
    intent = fast_intent(query)
    items = search_catalog(intent["category"], intent["max_price_paise"])
    scr = screen_relevance(items, query, intent["requirements"],
                           budget_paise=intent["max_price_paise"])
    kept = scr["candidates"]
    if kept:
        enrich_reviews(kept, 5)
        quality.annotate(kept)
        pick = explain.choose(kept, effective_priority(intent["priority"]),
                              intent["max_price_paise"],
                              intent["requirements"])["product"]
        title = (pick.get("name") or "").lower()
        check(f"{query[:34]!r} honours {must_have}",
              all(m in title for m in must_have), pick.get("name")[:60])
    else:
        check(f"{query[:34]!r} returned something", False)

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
