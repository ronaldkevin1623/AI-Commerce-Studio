"""
Does the refund path refuse everything it should, before it is trusted to
move money?

Every case here is a refusal. Not one of them issues a refund — the guards
are the part worth proving, and they can all be exercised against the live
API without a rupee moving. The one path that does move money is left for a
deliberate, separate decision.
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
import sys, requests

BASE = "http://127.0.0.1:8010"
PASS, FAIL = [], []
def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

from app.firebase_client import db

orders = [d.to_dict() or {} for d in db.collection("orders").get()]
paid = [o for o in orders
        if o.get("status") == "paid" and o.get("razorpay_payment_id")]
unpaid = [o for o in orders if o.get("status") != "paid"]

print(f"\n{len(paid)} refundable order(s), {len(unpaid)} unpaid")
if not paid:
    print("no captured payment to test against")
    sys.exit(1)

target = paid[0]
OID, PID = target["razorpay_order_id"], target["razorpay_payment_id"]
AMT = int(target.get("amount_paise") or 0)
print(f"target: {OID}  {PID}  Rs{AMT/100:,.2f}")


def post(payload):
    return requests.post(f"{BASE}/refund", json=payload, timeout=40)


print("\n=== A. Refusals ===")
r = post({"payment_id": PID, "order_id": "order_DOES_NOT_EXIST",
          "reason": "audit"})
check("An unknown order is refused", r.status_code == 404, r.text[:70])

if unpaid:
    u = unpaid[0]
    r = post({"payment_id": PID, "order_id": u.get("razorpay_order_id") or "x",
              "reason": "audit"})
    check("An unpaid order cannot be refunded", r.status_code in (404, 409),
          r.text[:80])
else:
    print("  [skip] no unpaid order available")

r = post({"payment_id": "pay_INVENTED", "order_id": OID, "reason": "audit"})
check("An invented payment id is refused, not a 500",
      r.status_code == 402, f"HTTP {r.status_code} {r.text[:60]}")

if len(paid) > 1:
    other = paid[1]
    r = post({"payment_id": other["razorpay_payment_id"], "order_id": OID,
              "reason": "audit"})
    check("A payment from another order is refused",
          r.status_code == 409, r.text[:80])
else:
    print("  [skip] need two captures to test cross-order")

r = post({"payment_id": PID, "order_id": OID, "reason": "audit",
          "amount_paise": AMT * 5})
check("Refunding more than was captured is refused",
      r.status_code == 409, r.text[:90])

r = post({"payment_id": PID, "order_id": OID, "reason": "audit",
          "amount_paise": 0})
check("A zero refund is refused", r.status_code == 400, r.text[:60])

print("\n=== B. The amount is computed, not accepted ===")
r = requests.get(f"{BASE}/refundable/{OID}", timeout=40)
check("Refundable amount is reported", r.status_code == 200, r.text[:110])
if r.ok:
    body = r.json()
    check("It matches what was actually captured",
          body.get("refundable_paise") == AMT - (body.get("already_refunded_paise") or 0),
          f"refundable Rs{(body.get('refundable_paise') or 0)/100:,.2f} "
          f"of Rs{(body.get('captured_paise') or 0)/100:,.2f}")

r = requests.get(f"{BASE}/refundable/order_NOPE", timeout=30)
check("An unknown order reports zero with a reason",
      r.ok and r.json().get("refundable_paise") == 0, r.text[:70])

if unpaid:
    r = requests.get(
        f"{BASE}/refundable/{unpaid[0].get('razorpay_order_id')}", timeout=30)
    check("An unpaid order reports nothing refundable and says why",
          r.ok and r.json().get("refundable_paise") == 0
          and bool(r.json().get("reason")), r.text[:90])

print("\n=== C. Every refusal was written down ===")
blocked = [d.to_dict() or {} for d in db.collection("decisions").get()
           if (d.to_dict() or {}).get("action_type") == "refund_blocked"]
check("Blocked refunds appear in the audit trail", len(blocked) >= 4,
      f"{len(blocked)} refund_blocked entries")
for b in blocked[-3:]:
    print(f"      {str(b.get('reason'))[:78]}")

print("\n=== D. Nothing moved ===")
import razorpay
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
p = client.payment.fetch(PID)
check("The payment is still fully captured, nothing refunded",
      int(p.get("amount_refunded") or 0) == 0,
      f"amount_refunded=Rs{int(p.get('amount_refunded') or 0)/100:,.2f}")

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
