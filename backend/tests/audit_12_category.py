"""
Does the agent return the thing that was asked for?

Guarding the failure from the screenshot: "nothing 3A phone black under
30000" answered with four phone cases at ₹680–806. Two faults, tested apart:

  Accessory patterns were anchored on "case for", and the titles read "For
  Nothing Phone 4A ... Back Case" — noun last, "for" first, so nothing fired.

  A budget was read only as a ceiling, when it also says what class of thing
  is wanted. ₹680 against a ₹30,000 phone request is a different product.

The opposite errors matter as much: someone asking for a case must still get
cases, and a genuinely cheap category must not be emptied out because the
budget was generous.
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

from app.agent.ollama_agent import (
    is_accessory_for, names_accessory, screen_relevance, fast_intent,
)

print("\n=== A. An accessory is recognised in any word order ===")
CASES = [
    ("For Nothing Phone 4A Pro 4A 3A Carbon Fiber Magnetic Rubber Back Case",
     "nothing 3A phone black under 30000", True, "noun last, 'for' first"),
    ("Shockproof Soft Rubber TPU Back Case For Nothing Phone",
     "nothing 3A phone under 30000", True, "the old word order too"),
    ("Nothing Phone 3a 128GB Black Unlocked Dual SIM",
     "nothing 3A phone black under 30000", False, "the actual product"),
    ("Tempered Glass Screen Protector for Nothing Phone 3a",
     "nothing 3A phone", True, "a protector is not a phone"),
]
for title, query, expected, why in CASES:
    check(f"{'accessory' if expected else 'the product'}: {title[:44]!r}",
          is_accessory_for(title, query) == expected, why)

print("\n=== B. Asking for an accessory still returns accessories ===")
check("A request naming a case is recognised", names_accessory("iphone 15 case"))
check("A case is kept when a case was asked for",
      is_accessory_for("Leather Case for iPhone 15", "iphone 15 case") is False)
check("A cable is kept when a cable was asked for",
      is_accessory_for("Braided USB-C Cable 2m", "usb-c cable 2 metre") is False)
check("A sleeve is kept when a sleeve was asked for",
      is_accessory_for("Felt Laptop Sleeve 14 inch", "felt laptop sleeve") is False)

print("\n=== C. The budget says what class of thing is wanted ===")
phones = [{"name": f"Nothing Phone 3a {i}", "price_paise": p, "condition": "New"}
          for i, p in enumerate([2871700, 2378400, 2100000, 1950000])]
cases = [{"name": f"Back Case cover {i}", "price_paise": p, "condition": "New"}
         for i, p in enumerate([68000, 73900, 74100])]

out = screen_relevance(phones + cases, "nothing 3a phone under 30000",
                       [], budget_paise=3000000)
kept = out["candidates"]
check("The cases are gone", all("Case" not in c["name"] for c in kept),
      f"{len(kept)} kept of {len(phones) + len(cases)}")
check("The phones survive", len(kept) == len(phones), f"{len(kept)} phones")

print("\n=== D. A cheap category is not emptied by a generous budget ===")
cables = [{"name": f"USB-C cable {i}", "price_paise": p, "condition": "New"}
          for i, p in enumerate([9300, 43900, 74600, 32000, 51000])]
out = screen_relevance(list(cables), "braided usb-c cable under 800", [],
                       budget_paise=80000)
check("Cheap-but-legitimate listings are kept",
      len(out["candidates"]) == len(cables),
      f"{len(out['candidates'])}/{len(cables)} kept")

print("\n=== E. The floor needs corroboration before it fires ===")
# Only two plausible listings: not enough to call the rest wrong.
thin = [{"name": "Thing A", "price_paise": 2500000, "condition": "New"},
        {"name": "Thing B", "price_paise": 2400000, "condition": "New"},
        {"name": "Thing C", "price_paise": 50000, "condition": "New"}]
out = screen_relevance(thin, "thing under 30000", [], budget_paise=3000000)
check("With too few plausible listings, nothing is dropped",
      len(out["candidates"]) == 3, f"{len(out['candidates'])}/3 kept")

print("\n=== F. Live: the query from the screenshot ===")
from app.agent.catalog import search_catalog
from app.agent.ebay_client import enrich_reviews
from app.agent import quality, explain
from app.agent.ollama_agent import effective_priority

q = "nothing 3A phone black under 30000"
intent = fast_intent(q)
items = search_catalog(intent["category"], intent["max_price_paise"])
scr = screen_relevance(items, q, intent["requirements"],
                       budget_paise=intent["max_price_paise"])
kept = scr["candidates"]
enrich_reviews(kept, 6)
quality.annotate(kept)
r = explain.choose(kept, effective_priority(intent["priority"]),
                   intent["max_price_paise"], intent["requirements"])
pick = r["product"]
print(f"    picked Rs{pick['price_paise']/100:,.0f} — {str(pick['name'])[:56]}")

check("The pick is not a case or cover",
      not is_accessory_for(pick["name"], q), pick["name"][:60])
check("The pick is a meaningful share of the stated budget",
      pick["price_paise"] >= intent["max_price_paise"] * 0.5,
      f"Rs{pick['price_paise']/100:,.0f} of Rs{intent['max_price_paise']/100:,.0f}")
check("The pick is still within budget",
      pick["price_paise"] <= intent["max_price_paise"])

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
