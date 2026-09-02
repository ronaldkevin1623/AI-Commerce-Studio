"""
RETAIL MEDIA — can the recommendation be bought?

The claim is narrow and testable: a promotion buys consideration and a
label, and nothing in the ranking. These try to break that:

  A  reach — what a promotion can and cannot be considered for
  B  NEUTRALITY — the same candidates rank identically with the flag on the
     best item, on the worst item, and on nothing at all
  C  the same screens drop a promoted product, and the stage is recorded
  D  money — charged for what was shown, never for what was only considered
  E  a promotion cannot be created on something that could never run

Writes real promotions on real products and deletes them at the end. Bids
are the ₹1.00 floor, so the accrual it leaves in the decision log is a true
record of a real placement and a trivial amount.
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


from app.adapters import sponsored_adapter as sponsored
from app.adapters.sponsored_adapter import SponsoredAdapter
from app.agent import precision, quality
from app.agent.explain import choose
from app.engines.contracts import NeedSpec
from app.engines.recsys import SignalRecSys
from app.firebase_client import db
from app.merchant import promotions, store

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


HUB = "cds-usbc-hub"          # computer accessories, in stock
LAMP = "cds-desk-lamp"        # home office, in stock
DRAFT = "cds-unfinished-prototype-stand"   # status=draft
FLOOR = promotions.MIN_BID_PAISE           # ₹1.00

adapter = SponsoredAdapter()


def cleanup():
    for pid in (HUB, LAMP, DRAFT, "no-such-product-at-all"):
        try:
            promotions.remove(pid)
        except Exception:
            pass


cleanup()

try:
    print("=== A. What a promotion is considered for ===")
    promotions.set_promotion(HUB, bid_paise=FLOOR, daily_budget_paise=FLOOR * 20)

    reached = [i["id"] for i in adapter.search("mechanical keyboard")]
    check("Reaches a search in its own category that keywords missed",
          HUB in reached, "'mechanical keyboard' → usb-c hub")

    check("Is NOT a placement where the shop already returns it",
          HUB not in [i["id"] for i in adapter.search("usb-c hub")],
          "no charging a merchant for their own organic traffic")

    check("Cannot reach a category the search never touched",
          adapter.search("coffee pods") == [], "'coffee pods' → nothing")
    check("...nor an unrelated category that did return results",
          adapter.search("desk lamp") == [], "'desk lamp' → nothing")

    placement = adapter.search("mechanical keyboard")[0]
    check("Every placement is stamped sponsored", placement.get("sponsored") is True)
    check("...names who promoted it", bool(placement.get("sponsored_by")))
    check("...and says what that did and did not buy",
          "not" in (placement.get("sponsored_note") or "").lower())
    check("source stays 'merchant', so checkout still routes",
          placement.get("source") == "merchant", placement.get("source"))
    check("...with the channel recorded separately",
          placement.get("sponsored_via") == "sponsored")

    print("\n=== B. Ranking neutrality — the thing that cannot be bought ===")


    def listing(pid, price, stars, count, sold, **extra):
        return {"id": pid, "name": f"Wireless Bluetooth Headphones {pid}",
                "price_paise": price, "source": "ebay", "condition_id": "1000",
                "seller_feedback": 99.0, "seller_feedback_count": 5000,
                "availability": "IN_STOCK", "stock": 4, "review_stars": stars,
                "review_count": count, "sold_quantity": sold, **extra}


    POOL = [
        listing("best", 180000, 4.6, 400, 300),
        listing("middle", 210000, 4.2, 120, 80),
        listing("worst", 260000, 3.1, 9, 3),
    ]
    need = NeedSpec(query="wireless bluetooth headphones",
                    category="wireless bluetooth headphones",
                    max_price_paise=0, budget_stated=False,
                    priority="value", bias="neutral")


    def order_with(sponsored_id=None):
        rows = []
        for row in POOL:
            copy = dict(row)
            if copy["id"] == sponsored_id:
                copy.update(sponsored=True, sponsored_via="sponsored",
                            sponsored_bid_paise=999999)
            rows.append(copy)
        ranked = SignalRecSys().rank(need, rows)
        return [c["id"] for c in ranked.candidates], (ranked.chosen or {}).get("id")


    clean_order, clean_pick = order_with(None)
    check("Baseline ranks and picks something", bool(clean_order) and clean_pick,
          f"{clean_order} → {clean_pick}")

    for flagged in ("worst", "best", "middle"):
        order, pick = order_with(flagged)
        check(f"Flagging {flagged!r} sponsored changes the order not at all",
              order == clean_order, f"{order}")
        check(f"...and does not change the pick", pick == clean_pick, pick)

    # The sort keys themselves, in isolation. A boost hidden in either one
    # would be invisible above if every promoted item happened to rank the
    # same anyway.
    plain = dict(POOL[2])
    bought = {**POOL[2], "sponsored": True, "sponsored_bid_paise": 10 ** 9}
    quality.annotate([plain, bought])
    check("quality.value_key ignores the flag",
          quality.value_key(plain, 0, "neutral") == quality.value_key(bought, 0, "neutral"))
    check("precision.preference_key ignores the flag",
          precision.preference_key(plain) == precision.preference_key(bought))

    picked_plain = choose([dict(c) for c in POOL], "value", user_text=need.query)
    flagged_pool = [{**c, "sponsored": True} if c["id"] == "worst" else dict(c)
                    for c in POOL]
    quality.annotate(flagged_pool)
    picked_flagged = choose(flagged_pool, "value", user_text=need.query)
    check("The recommender picks the same product either way",
          picked_plain["product"]["id"] == picked_flagged["product"]["id"],
          f'{picked_plain["product"]["id"]} both times')

    # And the honest converse: a promoted item that IS the best still wins,
    # because merit is the only thing being read.
    top_flagged = [{**c, "sponsored": True} if c["id"] == "best" else dict(c)
                   for c in POOL]
    ranked = SignalRecSys().rank(need, top_flagged)
    check("A promoted product that is genuinely best still wins",
          ranked.chosen["id"] == clean_pick and ranked.chosen.get("sponsored"),
          "won on merit, and is still labelled")

    print("\n=== C. The same screens, and the stage is recorded ===")
    run = promotions.PlacementRun([{"id": HUB, "sponsored": True},
                                   {"id": "organic-1"}])
    check("The run notices what entered", run.entered == {HUB})
    run.after("relevance", [{"id": "organic-1"}])
    check("...and which stage dropped it", run.fate == {HUB: "relevance"},
          str(run.fate))

    report = run.settle(shown=[{"id": "organic-1"}], chosen_id="organic-1")
    check("A screened-out placement is charged nothing",
          report["accrued_paise"] == 0 and report["shown"] == 0)
    after = promotions.get(HUB)
    check("...but the merchant sees it happened",
          after["screened_out"] == 1 and after["last_screened_out_at"] == "relevance",
          f'screened_out={after["screened_out"]} at {after["last_screened_out_at"]}')
    check("...and it cost nothing", after["spent_today_paise"] == 0)

    print("\n=== D. Money: charged for what reached the shopper ===")
    before = promotions.get(HUB)["spent_today_paise"]
    shown = adapter.search("mechanical keyboard")
    run2 = promotions.PlacementRun(shown)
    report2 = run2.settle(shown=shown, chosen_id=HUB)
    after2 = promotions.get(HUB)
    check("A placement that was shown is charged the bid",
          after2["spent_today_paise"] == before + FLOOR,
          f'₹{after2["spent_today_paise"] / 100:.2f} accrued')
    check("...counted as placed", after2["placed"] == 1)
    check("...and as chosen, because it was", after2["chosen"] == 1)
    check("The report says plainly that nothing is billed",
          report2["billed"] is False and "no rail" in report2["billing_note"].lower())

    rows = [d.to_dict() for d in
            db.collection("decisions")
              .where("action_type", "==", "sponsored_placement").limit(20).get()]
    check("The accrual is in the decision log like every other money event",
          any(r.get("amount_paise") == FLOOR for r in rows), f"{len(rows)} rows")
    check("...and the log entry itself says it is not billed",
          any("not billed" in (r.get("reason") or "").lower() for r in rows))

    # Budget exhaustion
    promotions.set_promotion(HUB, bid_paise=FLOOR, daily_budget_paise=FLOOR)
    exhausted = promotions.get(HUB)
    check("A budget spent down reads as exhausted, not as switched off",
          exhausted["exhausted"] and exhausted["active"],
          f'remaining ₹{exhausted["remaining_today_paise"] / 100:.2f}')
    check("...and it stops entering searches",
          HUB not in [i["id"] for i in adapter.search("mechanical keyboard")])
    check("...so the venue reports itself unavailable when nothing can run",
          adapter.available() is False)

    print("\n=== E. A promotion that could never run is refused ===")
    check("Unknown product",
          promotions.set_promotion("no-such-product-at-all", bid_paise=FLOOR,
                                   daily_budget_paise=FLOOR * 5)["ok"] is False)
    check("Bid under the floor",
          promotions.set_promotion(HUB, bid_paise=1,
                                   daily_budget_paise=FLOOR * 5)["ok"] is False)
    check("Budget that cannot cover one placement",
          promotions.set_promotion(HUB, bid_paise=FLOOR * 4,
                                   daily_budget_paise=FLOOR)["ok"] is False)

    promotions.set_promotion(DRAFT, bid_paise=FLOOR, daily_budget_paise=FLOOR * 5)
    check("A draft product accepts a promotion but never runs",
          DRAFT not in [p["product_id"] for p in promotions.eligible()],
          "eligible() refuses it")

    promotions.remove(HUB)
    promotions.set_promotion(LAMP, bid_paise=FLOOR, daily_budget_paise=FLOOR * 5)
    original_stock = store.get_product(LAMP).get("stock")
    store.db.collection(store.PRODUCTS).document(LAMP).update({"stock": 0})
    try:
        check("An out-of-stock product is not promoted into a search",
              LAMP not in [p["product_id"] for p in promotions.eligible()],
              "promoting something unbuyable is refused up front")
    finally:
        store.db.collection(store.PRODUCTS).document(LAMP).update(
            {"stock": original_stock})
    print("\n=== F. The complement slot ===")
    promotions.remove(LAMP)
    promotions.set_promotion(HUB, bid_paise=FLOOR, daily_budget_paise=FLOOR * 50)
    pool = adapter.search("mechanical keyboard")
    check("A promoted product reaches the pool for a category-adjacent search",
          [i["id"] for i in pool] == [HUB])

    offered = sponsored.complements(pool, shown=[{"id": "some-keyboard"}])
    check("It is offered as a complement", [i["id"] for i in offered] == [HUB])
    check("...marked as a complement, not as a ranked result",
          offered[0].get("sponsored_slot") == "complement")
    check("...with a note that says it is beside the results, not among them",
          "beside" in offered[0]["sponsored_note"] and
          "not claim" in offered[0]["sponsored_note"],
          offered[0]["sponsored_note"][:58] + "…")

    check("Anything already shown in the answer is not offered again",
          sponsored.complements(pool, shown=[{"id": HUB}]) == [],
          "no double placement")

    # Exempt from relevance, and from nothing else.
    dead = [{**pool[0], "stock": 0}]
    check("An out-of-stock complement is dropped",
          sponsored.complements(dead, shown=[]) == [])
    unbuyable = [{**pool[0], "availability": "OUT_OF_STOCK"}]
    check("...and one the venue reports unbuyable is too",
          sponsored.complements(unbuyable, shown=[]) == [])
    check("An empty pool yields an empty strip, not a stand-down",
          sponsored.complements([], shown=[]) == [],
          "unlike precision.screen, which keeps its last candidate")

    # The books have to agree: an item dropped from the answer and then
    # offered beside it is shown, not screened out.
    run3 = promotions.PlacementRun(pool)
    run3.after("relevance", [])
    before3 = promotions.get(HUB)
    report3 = run3.settle(shown=[{"id": "some-keyboard"}] + offered, chosen_id=None)
    after3 = promotions.get(HUB)
    check("A complement is charged as a placement",
          after3["spent_today_paise"] == before3["spent_today_paise"] + FLOOR,
          f'+₹{FLOOR / 100:.2f}')
    check("...and is NOT also counted as screened out",
          after3["screened_out"] == before3["screened_out"],
          "the two columns cannot both claim it")
    check("...and the report counts it as shown", report3["shown"] == 1)

finally:
    cleanup()
    left = [p["product_id"] for p in promotions.list_all()]
    check("Every test promotion was cleaned up", left == [], str(left))

print("\n" + "=" * 62)
print(f"  {passed} passed · {failed} failed")
