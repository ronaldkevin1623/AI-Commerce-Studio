"""
Does a direct buy of a store item now reach the seller?

Replicates exactly what the route does after the risk gate and the mandate
chain, for a merchant product, and then asks the settlement path what it
sees. The distinction being tested is precise:

  broken — _settle_with_merchant finds no session id and returns {}. The
           customer is charged, the page says confirmed, the seller is never
           told, and nothing reports a problem.

  fixed  — it finds the session and reports the outcome explicitly. Here that
           outcome is a refusal, because the payment id is invented; a refusal
           that is recorded is the correct answer and the opposite of silence.

Everything this creates is removed at the end.
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
import sys, uuid

PASS, FAIL = [], []
def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

from app.agent import merchant_client
from app.firebase_client import db, save_order, order_by_razorpay_id
from app.merchant import store
from app.routes.payment_routes import _settle_with_merchant

receipt = None
session_id = None

try:
    print("\n=== The store item the agent would have picked ===")
    items = merchant_client.search("braided usb-c cable", 80000)
    product = next((i for i in items if (i.get("price_paise") or 0) == 64900), None)
    check("A payable store product is reachable", product is not None,
          f"{product and product.get('name')}")
    if not product:
        raise SystemExit(1)

    quantity = 1

    # ── exactly what the route now does ─────────────────────────────────
    print("\n=== The direct-buy path, as the route runs it ===")
    checkout_session = merchant_client.open_checkout(
        [{"id": product["id"], "quantity": quantity}],
        {"customer_id": "audit-direct-buy", "name": "Audit", "email": "audit@local"},
        f"agent-{uuid.uuid4().hex}",
    )
    session_id = checkout_session.get("session_id")
    check("The seller opened a checkout session", bool(session_id), session_id)
    check("The seller created the Razorpay order, not us",
          bool(checkout_session.get("razorpay_order_id")),
          checkout_session.get("razorpay_order_id"))
    check("The seller's total is the price the gate approved",
          checkout_session.get("total_paise") == product["price_paise"],
          f"Rs{(checkout_session.get('total_paise') or 0)/100:,.2f}")

    receipt = f"cp-{uuid.uuid4().hex[:16]}"
    save_order(
        order_id=receipt,
        razorpay_order_id=checkout_session["razorpay_order_id"],
        amount_paise=product["price_paise"],
        product_name=product["name"],
        customer_id="audit-direct-buy",
        product=product,
    )
    db.collection("orders").document(receipt).update({
        "source": "merchant",
        "merchant_checkout_session": session_id,
        "merchant_id": product.get("merchant_id"),
        "merchant_name": product.get("merchant_name"),
    })

    stored = order_by_razorpay_id(checkout_session["razorpay_order_id"]) or {}
    check("The order records the session settlement needs",
          stored.get("merchant_checkout_session") == session_id,
          str(stored.get("merchant_checkout_session")))
    check("The order records which venue it came from",
          stored.get("source") == "merchant", str(stored.get("source")))

    print("\n=== What settlement now sees ===")
    result = _settle_with_merchant(checkout_session["razorpay_order_id"],
                                   "pay_INVENTED_FOR_AUDIT")
    check("Settlement no longer returns silence", result != {}, str(result)[:110])
    check("Settlement names the session it acted on",
          result.get("merchant_checkout_session") == session_id)
    check("An unverifiable payment is refused, not assumed",
          result.get("merchant_settled") is False,
          str(result.get("merchant_error"))[:70])

    print("\n=== The seller still holds the goods ===")
    fresh = store.get_product(product["id"]) or {}
    check("Stock was not moved by an unpaid checkout",
          fresh.get("stock") == product.get("stock"),
          f"{product.get('stock')} -> {fresh.get('stock')}")

finally:
    print("\n=== Cleanup ===")
    if receipt:
        db.collection("orders").document(receipt).delete()
        print(f"  removed order {receipt}")
    if session_id:
        db.collection(store.SESSIONS).document(session_id).delete()
        print(f"  removed session {session_id}")

print("\n" + "=" * 62)
print(f"  {len(PASS)} passed · {len(FAIL)} failed")
if FAIL:
    print("  FAILED: " + "; ".join(FAIL))
