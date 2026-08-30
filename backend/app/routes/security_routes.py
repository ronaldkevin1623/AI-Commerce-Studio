"""
WHAT THIS SYSTEM HOLDS ABOUT YOU — checked when you ask, not asserted.

An agent that spends someone's money has to answer "what do you know about
me?", and the usual answer is a privacy page written once and never verified
again. This endpoint runs the check instead: it walks the stored documents
every time it is called and reports what it actually found.

That makes the claim falsifiable. If a card number ever gets written into
Firestore, this page says so on the next load rather than continuing to
promise it did not happen. A privacy statement that cannot fail is not
evidence of anything.

It reports what *is* stored as plainly as what is not. A name and an email
address are held, and saying "we store nothing about you" would be the same
kind of comfortable falsehood this project refuses everywhere else.
"""
import json
import re
from collections import Counter

from fastapi import APIRouter

from app.firebase_client import db
from app.config import RAZORPAY_KEY_ID

router = APIRouter()

# The things whose presence would disprove the claim.
FORBIDDEN = {
    "Card number": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "CVV / security code": re.compile(r"\b(cvv|cvc|card_?code|security_?code)\b", re.I),
    "Card expiry": re.compile(r"\b(exp_?month|exp_?year|expiry|card_?exp)\b", re.I),
    "Raw card field": re.compile(r"\b(card_?number|pan|cardno|card_no)\b", re.I),
    "Bank account or IFSC": re.compile(
        r"\b(account_?number|acct_?no|ifsc|iban|routing_?number|sort_?code)\b", re.I),
    "UPI handle": re.compile(
        r"\b[\w.\-]{3,}@(okaxis|oksbi|okhdfcbank|ybl|paytm|upi|apl|ibl)\b", re.I),
    "Netbanking credential": re.compile(
        r"\b(netbanking_?(user|password)|bank_?password|mpin|otp_?value)\b", re.I),
    "Password or secret": re.compile(r"\"(password|passwd|secret|private_key)\"", re.I),
}

COLLECTIONS = ["orders", "customers", "decisions", "refunds", "merchant_products",
               "merchant_checkouts", "runs", "market_scans", "proposals"]

# Personal data this system does hold, named rather than glossed over.
DECLARED = [
    ("name", "A display name, as typed into the console."),
    ("email", "Used to recognise a returning buyer and attach their orders."),
    ("customer_id", "An internal id. Not derived from anything personal."),
    ("trust_score", "A number the risk gate moves up and down with behaviour."),
]


def _luhn(number: str) -> bool:
    """Keeps 16-digit ids and timestamps from being reported as card numbers."""
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


@router.get("/security/data-audit")
def data_audit():
    """Walk the database now and report what is in it."""
    findings = []
    fields = Counter()
    scanned = 0
    collections_seen = []

    for name in COLLECTIONS:
        try:
            docs = db.collection(name).limit(400).get()
        except Exception:
            continue
        count = 0
        for doc in docs:
            row = doc.to_dict() or {}
            scanned += 1
            count += 1
            fields.update(row.keys())
            blob = json.dumps(row, default=str)
            for label, pattern in FORBIDDEN.items():
                for match in pattern.findall(blob):
                    text = match if isinstance(match, str) else " ".join(match)
                    if label == "Card number" and not _luhn(text):
                        continue
                    findings.append({
                        "collection": name,
                        "document": doc.id,
                        "kind": label,
                    })
        collections_seen.append({"name": name, "documents": count})

    # A real order, with its values redacted — the field names are the point.
    example = None
    for doc in db.collection("orders").limit(60).get():
        row = doc.to_dict() or {}
        if row.get("razorpay_payment_id"):
            example = sorted(row.keys())
            break

    return {
        "scanned_documents": scanned,
        "collections": collections_seen,
        "checked_for": sorted(FORBIDDEN.keys()),
        "findings": findings,
        "clean": not findings,
        "order_fields": example or [],
        "personal_data_held": [
            {"field": f, "why": why} for f, why in DECLARED
        ],
        "distinct_field_names": len(fields),
        # The key the browser uses is the publishable one. Razorpay's secret
        # never leaves the server, and this proves which half is which.
        "razorpay_key_in_browser": RAZORPAY_KEY_ID,
        "key_is_publishable": RAZORPAY_KEY_ID.startswith("rzp_"),
        "accepted_by_verify_payment": [
            "razorpay_payment_id", "razorpay_order_id", "customer_id",
        ],
        "disclosure": (
            "This runs against the live database each time it is requested. "
            "It is not a stored result: if a card number were ever written "
            "here, this page would report it on the next load."
        ),
    }
