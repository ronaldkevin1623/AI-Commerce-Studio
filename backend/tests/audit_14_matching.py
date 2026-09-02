"""
The matching rules found by this round of tuning.

Four failures came out of the hard benchmark, and each is guarded here so a
later change cannot quietly undo it:

  "750 ml" became "75 ml" — rstrip(".0") ate the zero off any round number,
  turning 100 into 1 and 1000 into 1. Silently, because the result was still
  a plausible measurement.

  "1.5 litre" produced no attribute at all, because the unit pattern held
  "l" but not "litre" — so a 1.5-litre request was answered with 1.7 litres.

  "hp 680" matched "680ml". A leading-only word boundary is right for words
  ("shoe" should find "shoes") and wrong for numbers.

  A listing matching part of the request outranked one matching all of it,
  because ranking never looked at coverage.
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

from app.agent import attributes as A, quality, explain
from app.agent.ollama_agent import query_terms, matches_request

print("\n=== A. Round numbers survive normalisation ===")
for text, expected in [
    ("water bottle 750 ml", "750 ml"),
    ("mixer 1000 watt", "1000 watt"),
    ("hard disk 1 tb", "1 tb"),
    ("kettle 2.0 litre", "2 litre"),
    ("cable 1.5 metre", "1.5 metre"),
]:
    got = [a["text"] for a in A.required(text)]
    check(f"{text!r} -> {expected!r}", got == [expected], f"got {got}")

print("\n=== B. Volume units are understood ===")
for text, expected in [
    ("electric kettle 1.5 litre", "1.5 litre"),
    ("air fryer 4 litre", "4 litre"),
    ("backpack 30 litre", "30 litre"),
]:
    got = [a["text"] for a in A.required(text)]
    check(f"{text!r}", got == [expected], f"got {got}")

litre = A.required("kettle 1.5 litre")[0]
check("1.5 litre matches a 1.5L listing",
      A.satisfied("Kettle 1.5L Fast Boil Stainless", litre))
check("1.5 litre does NOT match a 1.7 Liter listing",
      not A.satisfied("COMFEE Electric Kettle, 1.7 Liter", litre))

print("\n=== C. Numbers match whole; words still match as prefixes ===")
terms = query_terms("hp 680 ink cartridge under 2000")
check("The budget is not a search term", "2000" not in terms, str(terms))
check("The model number is a search term", "680" in terms, str(terms))
# Asserted as a difference rather than a count: two titles identical except
# for how 680 appears. The earlier version hard-coded 3 and was simply wrong
# about its own fixture, which had no "ink" in it.
inside = "HP DESIGNJET INK CARTRIDGE 81 CYAN 680ml"
standalone = "HP DESIGNJET INK CARTRIDGE 81 CYAN 680 ml"
check("'680' does not match '680ml'",
      matches_request(inside, terms)[1] < matches_request(standalone, terms)[1],
      f"{matches_request(inside, terms)[1]} vs {matches_request(standalone, terms)[1]}")
check("'680' matches a real HP 680 cartridge",
      matches_request("HP 680 Original Black Ink Cartridge", terms)[1] == 4)
check("Words still match as prefixes ('shoe' finds 'shoes')",
      matches_request("Mens Trail Running Shoes", query_terms("running shoe"))[0])

print("\n=== D. A complete match outranks a better-evidenced partial ===")
full = {"id": "full", "name": "HP 680 Original Black Ink Cartridge",
        "price_paise": 160000, "seller_feedback": 98.0,
        "seller_feedback_count": 500, "condition_id": "1000", "condition": "New"}
partial = {"id": "partial",
           "name": "HP DESIGNJET INK CARTRIDGE 81 Dye LIGHT CYAN 680ml",
           "price_paise": 166000, "seller_feedback": 99.9,
           "seller_feedback_count": 6129, "condition_id": "1000",
           "condition": "New", "review_stars": 4.33, "review_count": 1,
           "top_rated_seller": True, "returns_accepted": True}
quality.annotate([full, partial])
check("The partial match really does score higher on quality",
      partial["quality"]["score"] > full["quality"]["score"],
      f"{partial['quality']['score']} vs {full['quality']['score']}")

r = explain.choose([partial, full], "value", 200000,
                   user_text="hp 680 ink cartridge under 2000")
check("...and the complete match is still chosen",
      r["product"]["id"] == "full", f"chose {r['product']['id']}")

print("\n=== E. Coverage does not disturb an otherwise equal field ===")
a = {"id": "a", "name": "Running Shoes Mens", "price_paise": 300000,
     "seller_feedback": 99.0, "seller_feedback_count": 900, "condition_id": "1000"}
b = {"id": "b", "name": "Running Shoes Mens", "price_paise": 200000,
     "seller_feedback": 99.0, "seller_feedback_count": 900, "condition_id": "1000"}
r = explain.choose([dict(a), dict(b)], "value", 0, user_text="running shoes")
check("With equal coverage, the usual ranking decides",
      r["product"]["id"] == "b", f"chose {r['product']['id']}")

print("\n=== F. An unmet attribute is stated on the recommendation ===")
kettle = {"id": "k", "name": "COMFEE Stainless Steel Electric Kettle 1.7 Liter",
          "price_paise": 290200, "seller_feedback": 100.0,
          "seller_feedback_count": 1356, "condition_id": "1000",
          "condition": "New"}
r = explain.choose([kettle], "value", 300000, unmet=["1.5 litre"],
                   user_text="stainless steel electric kettle 1.5 litre")
check("The sentence says which part of the request went unmet",
      "no listing offered 1.5 litre" in r["reason"], r["reason"][:120])

r = explain.choose([kettle], "value", 300000, unmet=[],
                   user_text="stainless steel electric kettle")
check("Nothing is claimed unmet when everything was met",
      "no listing offered" not in r["reason"], r["reason"][:90])

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
