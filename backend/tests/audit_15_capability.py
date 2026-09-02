"""
Two failures found by "samsung phone with good camera under 30000".

It answered with a 2015 Galaxy Note 5 and a 2016 S7 Edge, and threw away the
S25 FE at ₹27,224, the Z Flip6 at ₹19,256 and the Note20 Ultra at ₹13,006.

  THE SCREEN REQUIRED WORDS THE MARKET DOES NOT USE. The request's words were
  "samsung", "phone", "camera". A current flagship listing says "Samsung
  Galaxy S25 FE: Verizon Locked, 128GB Storage" — it does not say "phone",
  because it plainly is one. That is one word of three, under the coverage
  floor, so it was discarded. Older listings say "Smartphone", which matches
  "phone" as a prefix, and survived. The screen was selecting on seller
  verbosity and rejecting every modern model.

  QUALITY ANSWERED THE WRONG QUESTION. The score measures how safe a purchase
  is — seller record, condition, returns. Nothing in it knows an S25 is a
  better phone than an S20, so a six-point edge in seller reputation picked a
  two-generation-older handset for someone who asked for the best.
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

from app.agent.ollama_agent import query_terms, useful_terms, fast_intent
from app.agent import quality, explain

PHONES = [{"name": n} for n in [
    "Samsung Galaxy S25 FE: Verizon Locked, 128GB Storage, Navy Blue",
    "Samsung Galaxy Z Flip6: Spectrum Locked, 512GB, Silver Shadow",
    "Samsung Galaxy Note20 | Note20 Ultra 5G - 128GB | 256GB | 512GB",
    "Samsung Galaxy S7 Edge G935U 32GB Unlocked Phone AT&T",
    "Samsung Galaxy S10e - 128 GB - Blue (T-Mobile) SM-G970U",
    "Samsung Galaxy A42 5G SM-A426U Unlocked 128GB Prism Dot Black",
]]

print("\n=== A. A requirement is made of words the market uses ===")
raw = query_terms("samsung phone with good camera under 30000")
useful = useful_terms(raw, PHONES)
check("The brand survives", "samsung" in useful, str(useful))
check("'camera' is dropped — no phone title says it", "camera" not in useful)
check("The budget was never a term", "30000" not in raw, str(raw))

print("\n=== B. Modern flagships are no longer discarded ===")
from app.agent.ollama_agent import matches_request
for title in ["Samsung Galaxy S25 FE: Verizon Locked, 128GB Storage",
              "Samsung Galaxy Z Flip6: Spectrum Locked, 512GB"]:
    check(f"kept: {title[:44]!r}", matches_request(title, useful)[0])

print("\n=== C. It stands down rather than emptying the field ===")
unrelated = [{"name": "Bamboo Monitor Stand"}, {"name": "USB-C Hub"}]
check("When no term is used by anything, the original list stands",
      useful_terms(["nikon", "d850"], unrelated) == ["nikon", "d850"])

print("\n=== D. 'Best … under N' prefers the more capable product ===")
old_good_seller = {
    "id": "s20", "name": "Samsung Galaxy S20 5G Smartphone 128GB",
    "price_paise": 1329600, "seller_feedback": 100.0,
    "seller_feedback_count": 518, "condition_id": "2020",
    "condition": "Very Good - Refurbished", "top_rated_seller": True,
}
# Comparable condition, slightly weaker seller — the shape of the real case
# that started this (76.3 against 82.2). The first version of this fixture
# gave the S25 a worse condition *and* a worse seller, a nine-point gap the
# floor is supposed to respect, and then asserted the floor should be
# ignored. The floor was right and the test was wrong.
new_ok_seller = {
    "id": "s25", "name": "Samsung Galaxy S25 FE 128GB Storage",
    "price_paise": 2722400, "seller_feedback": 98.5,
    "seller_feedback_count": 3000, "condition_id": "2020",
    "condition": "Very Good - Refurbished",
}
quality.annotate([old_good_seller, new_ok_seller])
print(f"    S20 q={old_good_seller['quality']['score']}  "
      f"S25 q={new_ok_seller['quality']['score']}")
check("The older phone genuinely scores higher on transaction safety",
      old_good_seller["quality"]["score"] > new_ok_seller["quality"]["score"])

r = explain.choose([dict(old_good_seller), dict(new_ok_seller)], "value",
                   3000000, user_text="samsung phone good camera", bias="best")
check("...and 'best' still picks the more capable one",
      r["product"]["id"] == "s25", f"chose {r['product']['id']}")

print("\n=== E. It changes only 'best', and only with a budget ===")
r = explain.choose([dict(old_good_seller), dict(new_ok_seller)], "value",
                   3000000, user_text="samsung phone", bias="neutral")
check("A neutral request keeps the safety-first ordering",
      r["product"]["id"] == "s20", f"chose {r['product']['id']}")

r = explain.choose([dict(old_good_seller), dict(new_ok_seller)], "value",
                   0, user_text="samsung phone", bias="best")
check("'best' with no budget stated changes nothing",
      r["product"]["id"] == "s20", f"chose {r['product']['id']}")

r = explain.choose([dict(old_good_seller), dict(new_ok_seller)], "price",
                   3000000, user_text="cheapest samsung phone", bias="cheapest")
check("'cheapest' is untouched", r["product"]["id"] == "s20",
      f"chose {r['product']['id']}")

print("\n=== F. Quality is a floor, not a vote that was removed ===")
junk = {
    "id": "junk", "name": "Samsung Galaxy Phone 128GB",
    "price_paise": 2900000, "seller_feedback": 88.0,
    "seller_feedback_count": 900, "condition_id": "6000",
    "condition": "Acceptable",
}
quality.annotate([junk, new_ok_seller])
print(f"    junk q={junk['quality']['score']}  S25 q={new_ok_seller['quality']['score']}")
r = explain.choose([dict(junk), dict(new_ok_seller)], "value", 3000000,
                   user_text="samsung phone good camera", bias="best")
check("A dearer but genuinely poor listing does not win on price alone",
      r["product"]["id"] == "s25", f"chose {r['product']['id']}")

print("\n=== G. Live: the query that started this ===")
from app.agent.ollama_agent import screen_relevance, effective_priority
from app.agent.catalog import search_catalog
from app.agent.trust_agent import assess as trust_assess
from app.agent import settings
from app.agent.ebay_client import enrich_reviews

q = "samsung phone with good camera under 30000"
intent = fast_intent(q)
budget = intent["max_price_paise"]
bias = (intent.get("quality_bias") or "neutral").lower()
check("The request reads as 'best'", bias == "best", bias)

items = search_catalog(intent["category"], budget)
scr = screen_relevance(list(items), q, intent["requirements"], budget_paise=budget)
kept = scr["candidates"]
check("The screen keeps a real field, not a handful",
      len(kept) >= 10, f"{len(kept)} of {len(items)}")

trust = trust_assess(kept)
kept = trust["candidates"]
if settings.get("trust", "drop_flagged"):
    trusted = [c for c in kept if c["trust"]["ok"]]
    if trusted:
        kept = trusted
enrich_reviews(kept, 8)
quality.annotate(kept)
res = explain.choose(kept, effective_priority(intent["priority"]), budget,
                     intent["requirements"], scr.get("unmet_attributes"), q, bias)
pick = res["product"]
share = 100 * pick["price_paise"] / budget
print(f"    picked Rs{pick['price_paise']/100:,.0f} ({share:.0f}% of budget) — "
      f"{str(pick['name'])[:52]}")
# Not "spends most of the budget" — that assertion was here, and it failed
# on a Samsung S22 at 47% of a Rs30,000 ceiling, which is the RIGHT answer.
# Chasing the ceiling is the behaviour this project explicitly rejects: a
# better phone at 47% beats a worse one at 90%. What "best" actually has to
# mean is that price is not leading, so that is what is checked — against
# the field that survived, which is stable, rather than against a share of
# budget, which depends on what the marketplace happens to be selling today.
prices = sorted(c["price_paise"] for c in kept)
median = prices[len(prices) // 2]
check("'Best' does not collapse to the cheapest listing",
      pick["price_paise"] > prices[0],
      f"picked Rs{pick['price_paise']/100:,.0f} over Rs{prices[0]/100:,.0f}")
check("...and sits in the upper half of what survived",
      pick["price_paise"] >= median,
      f"Rs{pick['price_paise']/100:,.0f} vs median Rs{median/100:,.0f} "
      f"of {len(prices)} survivors ({share:.0f}% of budget)")
check("The pick is within budget", pick["price_paise"] <= budget)

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
