"""
Is the brand signal real, and does it stay in its lane?

The danger with a "recognition" score is that it becomes a popularity tax:
big names always win, unbranded listings are punished for being unbranded,
and the number gets presented as if it measured quality. Each of those is
tested here, along with the plain question of whether brands are identified
correctly at all.
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

from app.agent import brands, quality

VOCAB = {"Nike": 829151, "adidas": 335354, "Saucony": 53600,
         "New Balance": 157059, "Bose": 3049}

print("\n=== A. Brands come from eBay, not from guesswork ===")
dist = [{"localizedAspectName": "Brand", "aspectValueDistributions": [
    {"localizedAspectValue": "SanDisk", "matchCount": 219},
    {"localizedAspectValue": "Unbranded", "matchCount": 11},
    {"localizedAspectValue": "Not Specified", "matchCount": 7},
]}]
m = brands.market("sandisk pendrive", dist)
check("Named brands are kept", m.get("SanDisk") == 219, str(m))
check("'Unbranded' is not treated as a brand", "Unbranded" not in m)
check("'Not Specified' is not treated as a brand", "Not Specified" not in m)

print("\n=== B. Identification ===")
check("A brand in the title is found",
      brands.identify({"name": "Nike Air Zoom Pegasus 40"}, VOCAB) == "Nike")
check("Longest name wins over a substring",
      brands.identify({"name": "New Balance 1080 running"}, VOCAB) == "New Balance",
      brands.identify({"name": "New Balance 1080 running"}, VOCAB))
check("No false match inside another word",
      brands.identify({"name": "Bosepacked cable set"}, VOCAB) is None,
      str(brands.identify({"name": "Bosepacked cable set"}, VOCAB)))
check("An unbranded title matches nothing",
      brands.identify({"name": "Generic running shoes for men"}, VOCAB) is None)
check("A brand eBay stated on the listing is trusted",
      brands.identify({"name": "shoes", "brand": "adidas"}, VOCAB) == "adidas")
check("'Unbranded' stated on the listing is not a brand",
      brands.identify({"name": "cable", "brand": "Unbranded"}, VOCAB) is None)

print("\n=== C. Standing is relative and log-scaled ===")
big = brands.recognition("Nike", VOCAB)["score"]
mid = brands.recognition("Saucony", VOCAB)["score"]
small = brands.recognition("Bose", VOCAB)["score"]
check("A bigger presence scores higher", big > mid > small,
      f"Nike {big:.2f} > Saucony {mid:.2f} > Bose {small:.2f}")
check("A smaller brand is not crushed to nothing", small > 0.5,
      f"Bose {small:.2f} on 3,049 listings")
check("The listing count is reported for checking",
      brands.recognition("Nike", VOCAB)["listings"] == 829151)
check("An unknown brand yields no score",
      brands.recognition("Nobody", VOCAB)["score"] is None)
check("No brand yields no score",
      brands.recognition(None, VOCAB)["score"] is None)

print("\n=== D. Unbranded is not punished ===")
base = {"seller_feedback": 99.0, "seller_feedback_count": 5000,
        "condition": "New", "condition_id": "1000"}
plain = quality.assess(dict(base))
branded = quality.assess(dict(base, brand_standing={
    "brand": "Nike", "score": 1.0, "listings": 829151}))
weak = quality.assess(dict(base, brand_standing={
    "brand": "Tiny", "score": 0.2, "listings": 5}))
print(f"    unbranded {plain['score']}  strong {branded['score']}  weak {weak['score']}")
check("A strong brand helps", branded["score"] > plain["score"])
check("An unbranded listing is not scored below a weakly branded one",
      plain["score"] >= weak["score"],
      f"{plain['score']} vs {weak['score']}")

print("\n=== E. Brand cannot outweigh the evidence about the listing ===")
big_brand_bad_seller = quality.assess({
    "seller_feedback": 91.0, "seller_feedback_count": 30,
    "condition": "Used", "condition_id": "3000",
    "brand_standing": {"brand": "Nike", "score": 1.0, "listings": 829151}})
no_brand_good = quality.assess({
    "seller_feedback": 99.8, "seller_feedback_count": 400270,
    "condition": "New", "condition_id": "1000",
    "review_stars": 4.7, "review_count": 298, "returns_accepted": True})
print(f"    big brand / poor listing {big_brand_bad_seller['score']}   "
      f"no brand / strong listing {no_brand_good['score']}")
check("A famous name does not rescue a poor listing",
      no_brand_good["score"] > big_brand_bad_seller["score"])

print("\n=== F. Live ===")
from app.agent.catalog import search_catalog
from app.agent.ebay_client import enrich_reviews
from app.agent import explain

items = search_catalog("running shoes", 400000)
if items:
    enrich_reviews(items, 8)
    quality.annotate(items)
    named = [i for i in items if (i.get("brand_standing") or {}).get("brand")]
    check("Most live listings get a brand identified",
          len(named) >= len(items) * 0.6,
          f"{len(named)}/{len(items)}")
    r = explain.choose(items, "value", 400000)
    bs = r["product"].get("brand_standing") or {}
    print(f"    picked: {bs.get('brand')} ({bs.get('listings')}) — "
          f"Rs{r['product']['price_paise']/100:,.0f}")
    check("The explanation is checkable against eBay's own count",
          not bs.get("brand") or "listings in this category" in r["reason"],
          r["reason"][:110])
else:
    check("Live search returned listings", False)

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
