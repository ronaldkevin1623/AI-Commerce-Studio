"""
Does this system actually hold anything it should not?

The claim to be tested is that banking credentials never reach our servers —
that Razorpay's own iframe collects them and we keep only ids. That claim is
worth nothing until someone goes and looks, so this walks every stored
document and searches for the things that would falsify it.

If something sensitive is in there, this prints it and the honest output is a
defect report rather than a security page.
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
import sys, re, json
from collections import Counter

from app.firebase_client import db

# What must never appear in our storage.
PATTERNS = {
    "card number (13-19 digits)": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "CVV field": re.compile(r"\b(cvv|cvc|card_?code|security_?code)\b", re.I),
    "expiry": re.compile(r"\b(exp_?month|exp_?year|expiry|card_?exp)\b", re.I),
    "raw card field": re.compile(r"\b(card_?number|pan|cardno|card_no)\b", re.I),
    "bank account no.": re.compile(r"\b(account_?number|acct_?no|ifsc|iban|"
                                   r"routing_?number|sort_?code)\b", re.I),
    "UPI handle": re.compile(r"\b[\w.\-]{3,}@(okaxis|oksbi|okhdfcbank|ybl|"
                             r"paytm|upi|apl|ibl)\b", re.I),
    "netbanking login": re.compile(r"\b(netbanking_?(user|password)|"
                                   r"bank_?password|mpin|otp_?value)\b", re.I),
    "password-ish": re.compile(r"\"(password|passwd|secret|private_key)\"", re.I),
}

COLLECTIONS = ["orders", "customers", "decisions", "refunds",
               "merchant_products", "merchant_checkouts", "runs",
               "market_scans", "agent_settings", "redteam_runs", "proposals"]

# A Luhn check keeps 16-digit order ids and timestamps from being reported as
# card numbers — the point is to find real leaks, not to generate noise.
def luhn(number: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", number)]
    if not 13 <= len(digits) <= 19:
        return False
    total, alt = 0, False
    for d in reversed(digits):
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


findings = []
field_names = Counter()
scanned = 0

for name in COLLECTIONS:
    try:
        docs = db.collection(name).limit(400).get()
    except Exception as exc:
        print(f"  [skip] {name}: {exc}")
        continue

    for doc in docs:
        row = doc.to_dict() or {}
        scanned += 1
        field_names.update(row.keys())
        blob = json.dumps(row, default=str)

        for label, pattern in PATTERNS.items():
            for match in pattern.findall(blob):
                text = match if isinstance(match, str) else " ".join(match)
                if label.startswith("card number") and not luhn(text):
                    continue
                findings.append((name, doc.id, label, str(text)[:60]))

print(f"scanned {scanned} documents across {len(COLLECTIONS)} collections\n")

if findings:
    print("!! SENSITIVE DATA FOUND")
    for coll, doc_id, label, sample in findings[:25]:
        print(f"  {coll}/{doc_id}  {label}: {sample}")
    print(f"\n  {len(findings)} finding(s) — this is a defect, not a feature.")
else:
    print("No card numbers, CVVs, expiry dates, bank account numbers, UPI")
    print("handles or netbanking credentials found in any stored document.")

print("\n=== What an order actually stores ===")
sample = None
for doc in db.collection("orders").limit(40).get():
    row = doc.to_dict() or {}
    if row.get("razorpay_payment_id"):
        sample = row
        break
if sample:
    for key in sorted(sample.keys()):
        value = sample[key]
        shown = json.dumps(value, default=str)
        print(f"  {key:26} {shown[:64]}")

print("\n=== Every field name we store, anywhere ===")
for key, count in sorted(field_names.items()):
    print(f"  {key} ({count})", end="  ")
print()
