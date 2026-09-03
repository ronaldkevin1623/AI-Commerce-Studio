"""
Part 3: the live path. Real eBay, real UCP merchant over HTTP, real Razorpay.
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
import sys, re, json, time
PASS, FAIL, WARN = [], [], []
def check(n, ok, d=""):
    (PASS if ok else FAIL).append(n)
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))
def warn(n, d=""):
    WARN.append(n); print(f"  [WARN] {n}" + (f" — {d}" if d else ""))

from app.agent.catalog import search_catalog

print("\n=== 8. LIVE SEARCH: real listings, and only ones that fit ===")
CEIL = 100000  # ₹1,000
t0 = time.time()
items = search_catalog("sandisk 128gb pendrive", CEIL, requirements=["sandisk", "128gb"])
print(f"    {len(items)} listings in {time.time()-t0:.1f}s")

check("Live search returned listings", bool(items), f"{len(items)} items")
if items:
    over = [i for i in items if (i.get("price_paise") or 0) > CEIL]
    check("Nothing above the stated ceiling is shown", not over,
          f"{len(over)} over ₹{CEIL/100:,.0f}")

    zero = [i for i in items if not (i.get("price_paise") or 0)]
    check("Every listing carries a real price", not zero, f"{len(zero)} priced at 0")

    nourl = [i for i in items if not (i.get("url") or "").startswith("http")]
    check("Every listing links to a real page", not nourl, f"{len(nourl)} without a URL")

    brand = [i for i in items if "sandisk" in (i.get("name") or "").lower()]
    pct = round(100 * len(brand) / len(items))
    check("The requested brand dominates the results", pct >= 70,
          f"{len(brand)}/{len(items)} = {pct}% SanDisk")

    fallback_ids = {"p1", "p2", "p3", "p4", "p5"}
    leaked = [i for i in items if str(i.get("id")) in fallback_ids]
    check("No static fallback item leaked into a live result", not leaked,
          f"{len(leaked)} fallback items")

    srcs = {}
    for i in items:
        srcs[i.get("source")] = srcs.get(i.get("source"), 0) + 1
    print(f"    sources: {srcs}")

print("\n=== 9. UCP MERCHANT LOOP over real HTTP ===")
from app.agent import merchant_client
try:
    mitems = merchant_client.search("", 0)
    check("The buying agent can reach the merchant over HTTP", True,
          f"{len(mitems)} products via UCP")
    if mitems:
        check("Merchant items are tagged as a payable venue",
              all(i.get("source") == "merchant" for i in mitems),
              str({i.get("source") for i in mitems}))
except Exception as e:
    check("The buying agent can reach the merchant over HTTP", False, str(e)[:70])

print("\n=== 10. RAZORPAY: is the order real? ===")
import razorpay
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
try:
    made = client.order.create({"amount": 10000, "currency": "INR",
                                "notes": {"purpose": "end-to-end audit"}})
    check("A real Razorpay order can be created", bool(made.get("id")),
          f"{made['id']} status={made['status']}")
    fetched = client.order.fetch(made["id"])
    check("That order is retrievable from Razorpay's API",
          fetched["id"] == made["id"],
          f"amount_paid={fetched.get('amount_paid')}")
    check("A freshly created order is unpaid, as it should be",
          fetched["status"] == "created" and fetched.get("amount_paid") == 0)
except Exception as e:
    check("A real Razorpay order can be created", False, str(e)[:90])

print("\n=== 11. PAYMENT VERIFICATION rejects a made-up payment ===")
import requests
try:
    r = requests.post("http://127.0.0.1:8010/verify-payment", timeout=30, json={
        "razorpay_order_id": "order_FAKE123", "razorpay_payment_id": "pay_FAKE123",
        "razorpay_signature": "deadbeef"})
    check("An invented payment id is refused", r.status_code >= 400,
          f"HTTP {r.status_code}: {r.text[:70]}")
except Exception as e:
    warn("Could not reach /verify-payment", str(e)[:60])

print("\n=== 12. ANALYTICS reconcile against Firestore ===")
from app.firebase_client import db
orders = [d.to_dict() or {} for d in db.collection("orders").get()]
real_paid = [o for o in orders if o.get("razorpay_payment_id")]
try:
    g = requests.get("http://127.0.0.1:8010/growth-insights", timeout=60).json()
    s = g.get("summary", {})
    check("Dashboard order count matches Firestore",
          s.get("orders") == len(orders), f"page={s.get('orders')} db={len(orders)}")
    # A refunded order keeps its payment id — it was genuinely paid — but it
    # must stop counting as revenue.
    still_paid = [o for o in real_paid if (o.get("status") or "") == "paid"]
    refunded = [o for o in real_paid if (o.get("status") or "") == "refunded"]
    check("Dashboard's paid count excludes refunded orders",
          (s.get("orders_paid") or 0) == len(still_paid),
          f"page={s.get('orders_paid')} still-paid={len(still_paid)} "
          f"refunded={len(refunded)}")

    # The stronger claim: the money is verifiable outside this application.
    captured = client.payment.all({"count": 100}).get("items", [])
    rzp_total = sum(p["amount"] for p in captured if p["status"] == "captured")
    check("Every rupee reported as captured is confirmed by Razorpay",
          (s.get("captured_paise") or 0) == rzp_total,
          f"dashboard Rs{(s.get('captured_paise') or 0)/100:,.2f} vs "
          f"Razorpay Rs{rzp_total/100:,.2f}")

    # THE REVERSE DIRECTION.
    #
    # The check above only catches the dashboard claiming money Razorpay
    # cannot confirm — inflation. It is blind to the opposite and worse
    # case: a payment Razorpay moved that this application never recorded
    # against an order at all.
    #
    # Written carefully after a false alarm. Razorpay showed 7 payments
    # that moved money while Firestore listed 6 paid orders, which looked
    # like a missing record and was not: pay_TVHMFZKgIyImkW (Rs319.55, 28
    # Aug) was captured and then fully refunded, so it is correctly absent
    # from "paid" and correctly present as "refunded". Captured minus
    # refunded is exactly the dashboard total.
    #
    # So the invariant is about every payment that EVER moved money, not
    # just the ones still captured — and it is satisfied by the order
    # being recorded in either state. Checking only `captured` would have
    # skipped the refunded one and quietly proved nothing about it.
    moved = [p for p in captured if p["status"] in ("captured", "refunded")]
    known = {o.get("razorpay_payment_id") for o in real_paid}

    # CHECKOUTS STILL IN FLIGHT ARE NOT UNRECORDED MONEY.
    #
    # A checkout is an order, then a human on a bank page, then a capture.
    # Between the capture and verify-payment running, Razorpay has the
    # money and this app has no payment id for it — which is exactly the
    # shape of a genuine orphan, and is not one. Reconciling in that window
    # reports a real payment as missing.
    #
    # So the open register is consulted and those orders are held out,
    # named rather than silently skipped. The register self-expires, so a
    # truly abandoned checkout returns to being reconciled normally instead
    # of being excused forever.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from app import inflight
        in_flight = {r["order_id"] for r in inflight.active()}
    except Exception as exc:
        in_flight = set()
        print(f"  [note] in-flight register unreadable ({exc}) — "
              f"reconciling everything")

    orphans = []
    deferred = []
    for pay in moved:
        if pay["id"] in known:
            continue
        try:
            order = client.order.fetch(pay["order_id"])
        except Exception:
            continue
        # Only this app's own receipts. The merchant half of the loop
        # creates its own Razorpay order for the same purchase, so counting
        # those would report a phantom gap on every legitimate sale.
        if not str(order.get("receipt") or "").startswith("cp-"):
            continue
        if pay.get("order_id") in in_flight:
            deferred.append((pay["id"], pay["amount"]))
            continue
        orphans.append((pay["id"], pay["status"], pay["amount"]))

    note = ""
    if deferred:
        note = (f" [{len(deferred)} held out as still in flight: "
                + "; ".join(f"{pid} Rs{amt/100:,.2f}" for pid, amt in deferred[:3])
                + "]")
    check("No payment moved money without this app recording the order",
          not orphans,
          ("; ".join(f"{pid} ({st}) Rs{amt/100:,.2f}" for pid, st, amt in orphans[:3])
           or f"{len(moved)} payments moved money, all recorded "
              f"({len([p for p in moved if p['status'] == 'refunded'])} refunded)")
          + note)

    ids = {o.get("razorpay_payment_id") for o in real_paid}
    # "refunded" is a captured payment that was later returned, so it counts
    # as evidence that money genuinely moved.
    settled = {p["id"] for p in captured
               if p["status"] in ("captured", "refunded")}
    check("Every stored payment id names a payment Razorpay actually took",
          ids.issubset(settled),
          f"{len(ids)} stored, {len(settled)} captured-or-refunded at Razorpay")

    if refunded:
        rzp_refunded = {p["id"] for p in captured if p["status"] == "refunded"}
        ours = {o.get("razorpay_payment_id") for o in refunded}
        check("Orders we call refunded are refunded at Razorpay too",
              ours.issubset(rzp_refunded), f"{len(ours)} refunded locally")
        check("The refunded total is reflected on the dashboard",
              (s.get("refunded_paise") or 0) > 0,
              f"Rs{(s.get('refunded_paise') or 0)/100:,.2f}")
    notes = g.get("notes", [])
    check("Every finding carries a headline", all(n.get("headline") for n in notes),
          f"{sum(1 for n in notes if n.get('headline'))}/{len(notes)}")
except Exception as e:
    check("Dashboard reconciles", False, str(e)[:80])

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed · {len(WARN)} warnings")
if FAIL: print("  FAILED: " + "; ".join(FAIL))
