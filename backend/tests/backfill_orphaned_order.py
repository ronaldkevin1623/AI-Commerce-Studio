"""
MOVE ONE ORPHANED ORDER FROM THE EMULATOR EXPORT INTO REAL FIRESTORE.

THE SITUATION

On 2 Sep 2026 at 09:46 a real netbanking payment of Rs829.17 completed:
pay_TX27e4NKLGuuvX, for order_TX27VVXEhtVK4U. This app created that order
and recorded it correctly — order marked `paid`, payment id attached, a
`payment_confirmed` decision row written. All of it went into the FIRESTORE
EMULATOR, because that is where .env pointed at the time. .env was reverted
to real Firestore at 12:38.

Razorpay is real in both cases. So reconciliation against real Firestore
sees a capture with no local record and correctly reports a gap.

WHAT THIS SCRIPT IS, AND WHAT IT IS NOT

It RELOCATES a genuine record. It does not invent one. Every field comes
from emulator-dump.json, which was exported from the emulator on 2 Sep, and
the payment is re-verified against the Razorpay API before anything is
written. The row lands stamped with where it came from, so no later reader
can mistake it for a record that was born in real Firestore.

The alternative — adding this payment to a reconciliation allowlist — was
rejected. That would permanently silence a working check to make one number
green, and the next real orphan would be invisible.

SAFETY

  * Reads from emulator-dump.json, not the live emulator, so it produces
    the same result whether or not the emulator is still running.
  * Refuses unless Razorpay confirms the payment exists, is captured, and
    the amount matches to the paise.
  * Refuses if the order already exists in real Firestore. Idempotent.
  * Refuses to run against anything but the real datastore — backfilling
    into the emulator would be meaningless.
  * Writes NOTHING without --commit. The default is a preview.

    python tests/backfill_orphaned_order.py            # preview only
    python tests/backfill_orphaned_order.py --commit   # actually write
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

DUMP = BACKEND.parent / "emulator-dump.json"

# The single record this script exists for. Named explicitly rather than
# discovered: a script that hunts for "anything that looks orphaned" and
# writes it into production is a much larger and more dangerous tool than
# the one that is actually needed.
ORDER_ID = "order_TX27VVXEhtVK4U"
PAYMENT_ID = "pay_TX27e4NKLGuuvX"
EXPECTED_PAISE = 82917
SOURCE_STORE = "emulator:127.0.0.1:8085"


def fail(message: str) -> int:
    print(f"\nREFUSING: {message}\n")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true",
                        help="actually write. Without this, preview only.")
    args = parser.parse_args()

    # ── 1. this must be the real datastore ──────────────────────────────
    from app.firebase_client import db, store_binding
    if store_binding() != "real":
        return fail(f"datastore is {store_binding()}, not real. "
                    f"Backfilling into the emulator would achieve nothing. "
                    f"Start with CARTPILOT_STORE=real.")

    # ── 2. read the record out of the export, not the live emulator ─────
    if not DUMP.exists():
        return fail(f"{DUMP} not found. It is the source of truth for this "
                    f"record; the emulator is in-memory and may be gone.")
    dump = json.loads(DUMP.read_text(encoding="utf-8"))

    orders = dump.get("orders", {})
    source_doc_id, source = next(
        ((k, v) for k, v in orders.items()
         if v.get("razorpay_order_id") == ORDER_ID), (None, None))
    if not source:
        return fail(f"{ORDER_ID} is not in {DUMP.name}.")

    decisions = [d for d in dump.get("decisions", {}).values()
                 if d.get("order_id") == ORDER_ID]

    # ── 3. re-verify against Razorpay before trusting any of it ─────────
    import razorpay
    from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
    client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    try:
        payment = client.payment.fetch(PAYMENT_ID)
    except Exception as exc:
        return fail(f"Razorpay does not know {PAYMENT_ID}: {exc}")

    if payment.get("status") != "captured":
        return fail(f"{PAYMENT_ID} is {payment.get('status')!r}, not captured.")
    if int(payment.get("amount") or 0) != EXPECTED_PAISE:
        return fail(f"amount mismatch: Razorpay says {payment.get('amount')}, "
                    f"this script expects {EXPECTED_PAISE}.")
    if payment.get("order_id") != ORDER_ID:
        return fail(f"{PAYMENT_ID} belongs to {payment.get('order_id')}, "
                    f"not {ORDER_ID}.")
    if int(source.get("amount_paise") or 0) != EXPECTED_PAISE:
        return fail(f"the exported order says {source.get('amount_paise')} "
                    f"paise; Razorpay says {EXPECTED_PAISE}.")

    # ── 4. never write twice ────────────────────────────────────────────
    try:
        existing = db.collection("orders").where(
            "razorpay_order_id", "==", ORDER_ID).limit(1).get()
    except Exception as exc:
        # Almost always the daily free-tier quota. A stack trace here reads
        # as "the backfill is broken" when the truth is "come back after
        # midnight US/Pacific" — and this script will mostly be run on days
        # the quota is already strained.
        if "RESOURCE_EXHAUSTED" in str(exc) or "Quota exceeded" in str(exc):
            return fail("real Firestore is over its daily read quota, so the "
                        "duplicate check cannot run. Nothing was written. "
                        "Retry after the quota resets (midnight US/Pacific).")
        return fail(f"could not check whether the order already exists: {exc}")
    if existing:
        print(f"\n{ORDER_ID} is already in real Firestore. Nothing to do.\n")
        return 0

    # ── 5. build exactly what would be written ──────────────────────────
    payload = dict(source)
    payload.update({
        "store": SOURCE_STORE,
        "migrated_at": int(time.time()),
        "migrated_from": SOURCE_STORE,
        "migrated_reason": (
            "Recorded by this app into the Firestore emulator on 2026-09-02, "
            "because .env pointed at the emulator when the payment completed. "
            "Razorpay is real in both cases, so the capture existed with no "
            "record in real Firestore. Relocated from emulator-dump.json "
            "after re-verifying the capture against the Razorpay API. Not a "
            "reconstructed or inferred record."),
    })

    note = {
        "action_type": "order_migrated_between_stores",
        "amount_paise": EXPECTED_PAISE,
        "decision": "recorded",
        "reason": (
            f"Order {ORDER_ID} / capture {PAYMENT_ID} (Rs{EXPECTED_PAISE/100:,.2f}) "
            f"was written to {SOURCE_STORE} on 2026-09-02 and is being copied "
            f"into real Firestore so reconciliation reflects money that "
            f"genuinely moved. Source: emulator-dump.json. Verified against "
            f"the Razorpay API: status=captured, amount and order id match. "
            f"The order row carries store={SOURCE_STORE} so its provenance "
            f"stays visible."),
        "order_id": ORDER_ID,
        "customer_id": source.get("customer_id"),
    }

    print("\n" + "=" * 74)
    print(f"  {'WOULD WRITE' if not args.commit else 'WRITING'} to real Firestore")
    print("=" * 74)
    print(f"\n  orders/{source_doc_id}")
    for key in sorted(payload):
        value = str(payload[key])
        print(f"    {key:18} {value[:100]}{'...' if len(value) > 100 else ''}")
    print(f"\n  decisions/<new>  ({len(decisions)} matching row(s) in the export)")
    for key in ("action_type", "decision", "amount_paise", "order_id"):
        print(f"    {key:18} {note[key]}")
    print(f"    {'reason':18} {note['reason'][:100]}...")
    print("\n" + "=" * 74)

    if not args.commit:
        print("  Preview only. Nothing was written. Re-run with --commit.")
        print("=" * 74 + "\n")
        return 0

    db.collection("orders").document(source_doc_id).set(payload)
    from app.firebase_client import log_decision
    log_decision(**note)
    print(f"  Written. {ORDER_ID} now exists in real Firestore, stamped")
    print(f"  store={SOURCE_STORE}.")
    print("=" * 74 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
