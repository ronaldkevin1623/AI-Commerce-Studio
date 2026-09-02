"""
Part 1 of the end-to-end audit: is the stored data honest, and do the
guards actually hold?

Nothing here is mocked. Every assertion reads live Firestore or calls the
real module. A test that cannot run says so rather than passing vacuously.
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
import json, time

PASS, FAIL, WARN = [], [], []

def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

def warn(name, detail=""):
    WARN.append(name)
    print(f"  [WARN] {name}" + (f" — {detail}" if detail else ""))

from app.firebase_client import db
from app.merchant import store

print("\n=== 1. DATA INTEGRITY: is anything fabricated? ===")

orders = [(d.id, d.to_dict() or {}) for d in db.collection("orders").get()]
ghosts = [o for _, o in orders
          if (o.get("status") or "") == "paid" and not o.get("razorpay_payment_id")]
check("No order marked paid without a Razorpay payment id",
      not ghosts, f"{len(orders)} orders, {len(ghosts)} fabricated")

sessions = [(d.id, d.to_dict() or {}) for d in db.collection(store.SESSIONS).get()]
sghosts = [s for _, s in sessions
           if s.get("status") == "paid" and not s.get("razorpay_payment_id")]
check("No checkout session marked paid without a payment id",
      not sghosts, f"{len(sessions)} sessions, {len(sghosts)} fabricated")

fulfilled_unpaid = [s for _, s in sessions
                    if s.get("fulfilment_state") and s.get("status") != "paid"]
check("No fulfilment history on an unpaid session",
      not fulfilled_unpaid, f"{len(fulfilled_unpaid)} offenders")

prods = store.list_products(include_redteam=True)
planted = [p for p in prods if "redteam" in str(p.get("id", "")).lower()
           or p.get("redteam")]
if planted:
    warn(f"{len(planted)} red-team fixture product(s) still in the store",
         "should be cleared after a run")
else:
    check("No red-team fixtures left in the catalogue", True, f"{len(prods)} real products")

print("\n=== 2. RISK GATE: do all six rules actually fire? ===")
from app.agent.risk_gate import evaluate
from app.agent import settings as agent_settings

buyer = {"id": f"audit-{int(time.time())}", "trust_score": 100, "name": "Audit"}
cheap = {"id": "aud-1", "name": "Audit item", "price_paise": 50000, "stock": 5,
         "source": "merchant"}

r = evaluate(buyer, {**cheap, "id": "aud-oos", "stock": 0}, record=False)
check("Out-of-stock is refused", r["decision"] != "allowed", r["reason"][:60])

r = evaluate({**buyer, "trust_score": 5}, {**cheap, "id": "aud-trust"}, record=False)
check("Low trust score is caught", r["decision"] != "allowed", r["reason"][:60])

huge = {**cheap, "id": "aud-huge", "price_paise": 99_00_00_000}
r = evaluate(buyer, huge, record=False)
check("Spend far above the bound is caught", r["decision"] != "allowed", r["reason"][:60])

# Reads the dial instead of assuming it. The Reseller preset sets this to
# zero on purpose — someone sourcing stock buys the same item repeatedly and
# that is not a mistake — so a fixed expectation here would report the guard
# as broken when it was doing exactly what it was configured to do.
dup_window = agent_settings.get("risk", "duplicate_window_seconds")
if dup_window:
    r1 = evaluate(buyer, {**cheap, "id": "aud-dup"}, record=True)
    r2 = evaluate(buyer, {**cheap, "id": "aud-dup"}, record=True)
    check("Duplicate purchase inside the window is caught",
          r2["decision"] != "allowed",
          f"first={r1['decision']} second={r2['decision']} window={dup_window}s")
else:
    warn("Duplicate window is switched off in the active preset",
         "repeat buys are allowed by configuration, not by failure")

limit = agent_settings.get("risk", "max_purchases_per_window")
if limit:
    vbuyer = {"id": f"audit-vel-{int(time.time())}", "trust_score": 100, "name": "Audit"}
    seen = []
    for n in range(int(limit) + 2):
        seen.append(evaluate(vbuyer, {**cheap, "id": f"aud-v{n}"}, record=True)["decision"])
        if seen[-1] != "allowed":
            break
    check("Velocity limit stops a rapid run",
          seen[-1] != "allowed", f"{seen.count('allowed')} allowed against limit {limit}")
else:
    warn("Velocity limit is switched off", "cannot test")

r = evaluate(buyer, {**cheap, "id": "aud-venue", "source": "somewhere-else"},
             record=False, allowed_venues={"ebay", "merchant"})
check("Purchase outside the approved venues is refused",
      r["decision"] != "allowed", r["reason"][:60])

print("\n=== 3. MANDATE CHAIN: does the signature actually gate anything? ===")
from app.agent import mandates

intent = {"category": "audit widget", "max_price_paise": 500000,
          "priority": "price", "requirements": []}
ij = mandates.issue_intent_mandate(intent, buyer["id"])
product = {"id": "aud-m1", "name": "Audit widget", "price_paise": 400000,
           "source": "merchant", "quantity": 1}
cart = mandates.issue_cart_mandate(ij, product, buyer["id"])
cj = cart["cart_jwt"] if isinstance(cart, dict) else cart

v = mandates.verify_chain(ij, cj, product)
check("A genuine chain verifies", v.get("ok") is True,
      f"{sum(1 for c in v.get('checks', []) if c.get('ok'))}/"
      f"{len(v.get('checks', []))} checks ok")

tampered = {**product, "price_paise": 100}
v2 = mandates.verify_chain(ij, cj, tampered)
check("Repricing the item after signing is detected", v2.get("ok") is False,
      "; ".join(c["name"] for c in v2.get("checks", []) if not c.get("ok"))[:70])

bad = cj[:-6] + ("aaaaaa" if not cj.endswith("aaaaaa") else "bbbbbb")
try:
    v3 = mandates.verify_chain(ij, bad, product)
    ok3 = v3.get("ok") is False
except Exception:
    ok3 = True
check("A forged signature is rejected", ok3)

venues = mandates.allowed_venues(ij)
check("Approved venues are readable from the signed intent",
      bool(venues), str(venues))

print("\n=== 4. FULFILMENT: can an unpaid order be shipped? ===")
unpaid = [(sid, s) for sid, s in sessions if s.get("status") != "paid"]
if unpaid:
    sid = unpaid[0][1].get("id") or unpaid[0][0]
    res = store.advance_fulfilment(sid, "shipped", tracking_reference="AUDIT123")
    check("Unpaid order cannot be advanced", res.get("ok") is False,
          str(res.get("error"))[:70])
    after = store.get_session(sid) or {}
    check("The refused attempt wrote nothing",
          not after.get("fulfilment_state") and not after.get("fulfilment_history"),
          f"state={after.get('fulfilment_state')}")

    paid = [(s2.get("id") or k) for k, s2 in sessions if s2.get("status") == "paid"]
    if paid:
        res2 = store.advance_fulfilment(paid[0], "delivered")
        check("Skipping fulfilment steps is refused", res2.get("ok") is False,
              str(res2.get("error"))[:70])
    else:
        warn("No paid session exists", "cannot test step-skipping (nothing has been paid)")
else:
    warn("No unpaid session available to test the fulfilment guard")

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed · {len(WARN)} warnings")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
