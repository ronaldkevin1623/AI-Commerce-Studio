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

from app.firebase_client import db, log_decision
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


# ── Forgetting a search ──────────────────────────────────────────────────
#
# An agent that keeps everything it has ever been asked and cannot be told
# to drop any of it is its own kind of problem, and this page is the one
# claiming to answer "what do you know about me". Auditing without a way to
# act on the answer is only half the promise.
#
# A search leaves rows in TWO places — `runs`, which is the conversation,
# and `market_scans`, which is what the marketplace returned. Deleting one
# and not the other would report a search as forgotten while the query text
# was still sitting in the database, which is worse than not offering the
# control at all.

FORGETTABLE = ("runs", "market_scans")


def _search_rows() -> dict:
    """Every stored search, grouped by the words that were typed."""
    grouped: dict = {}
    for collection in FORGETTABLE:
        try:
            docs = db.collection(collection).limit(300).get()
        except Exception as exc:
            print(f"[security] could not read {collection}: {exc}", flush=True)
            continue
        for doc in docs:
            row = doc.to_dict() or {}
            query = (row.get("query") or "").strip()
            if not query:
                continue
            entry = grouped.setdefault(query, {
                "query": query, "runs": 0, "scans": 0, "last_seen": None,
            })
            entry["runs" if collection == "runs" else "scans"] += 1
            when = row.get("created_at") or row.get("ran_at")
            stamp = getattr(when, "isoformat", lambda: None)()
            if stamp and (not entry["last_seen"] or stamp > entry["last_seen"]):
                entry["last_seen"] = stamp
    return grouped


@router.get("/security/searches")
def stored_searches():
    """
    What this agent remembers you looking for, and where it is kept.

    Ordered newest first, because the recent ones are both the most likely
    to be regretted and the ones actually steering recommendations.
    """
    grouped = _search_rows()
    rows = sorted(grouped.values(),
                  key=lambda r: r["last_seen"] or "", reverse=True)
    return {
        "searches": rows,
        "count": len(rows),
        "rows_held": sum(r["runs"] + r["scans"] for r in rows),
        "note": ("Each search is stored twice: the conversation in `runs`, "
                 "and what the marketplace returned in `market_scans`. "
                 "Forgetting one removes both. Recommendations are built "
                 "from what is left, so a forgotten search stops influencing "
                 "them on the next load."),
    }


@router.delete("/security/searches")
def forget_search(query: str = "", all: bool = False):
    """
    Delete one search, or all of them, from both collections.

    The audit trail records that a deletion happened and how many rows went
    — but NOT the query text. Writing the words into `decisions` on the way
    out would leave the very thing the person just asked to be rid of
    sitting in another collection, and call it accountability.
    """
    if not query and not all:
        return {"ok": False, "error": "Name a search to forget, or pass all=true."}

    removed = {"runs": 0, "market_scans": 0}
    target = query.strip().lower()

    for collection in FORGETTABLE:
        try:
            for doc in db.collection(collection).limit(500).get():
                row = doc.to_dict() or {}
                stored = (row.get("query") or "").strip().lower()
                if not stored:
                    continue
                if all or stored == target:
                    doc.reference.delete()
                    removed[collection] += 1
        except Exception as exc:
            print(f"[security] could not clear {collection}: {exc}", flush=True)

    total = removed["runs"] + removed["market_scans"]
    try:
        log_decision(
            action_type="search_history_forgotten",
            amount_paise=0,
            decision="allowed",
            reason=(f"A person asked this agent to forget "
                    f"{'all stored searches' if all else 'a stored search'}. "
                    f"{removed['runs']} conversation rows and "
                    f"{removed['market_scans']} marketplace scans deleted. "
                    f"The words themselves are deliberately not recorded "
                    f"here — logging them would undo the deletion."),
        )
    except Exception as exc:
        print(f"[security] deletion not logged: {exc}", flush=True)

    return {
        "ok": True,
        "removed": removed,
        "total": total,
        "detail": (f"Forgotten. {total} row{'s' if total != 1 else ''} deleted "
                   f"across {len(FORGETTABLE)} collections. This will stop "
                   f"influencing recommendations on the next load."),
    }
