"""
Idempotency for operations that move money.

UCP makes `idempotency-key` a mandatory request header, and the reason is
concrete rather than ceremonial: without it, a retried checkout creates a
second Razorpay order. AI Commerce Studio had one narrow guard against this — the risk
gate's duplicate window — which only catches a repeat of the *same product by
the same customer inside sixty seconds*. A cart checkout retried after a
network timeout, or an MCP client retrying `confirm_purchase`, sailed straight
past it.

THE CLAIM IS ATOMIC, NOT CHECK-THEN-ACT.

The obvious implementation — read the key, see nothing, then write — has a
race exactly where it matters: two concurrent retries both read "not seen",
both proceed, and both charge. Firestore's `create()` fails if the document
already exists, and that failure is atomic at the server, so the first caller
wins and every other caller gets the conflict. Whoever wins the create is the
only one who executes.

A failed operation releases its key so the caller can genuinely retry. A
completed one keeps its stored response forever and replays it.
"""
import hashlib

from google.api_core.exceptions import AlreadyExists
from google.cloud.exceptions import Conflict

from app.firebase_client import db
from firebase_admin import firestore

COLLECTION = "idempotency"


class InProgress(Exception):
    """Another caller holds this key and hasn't finished yet."""


def derive_key(operation: str, *parts) -> str:
    """
    A deterministic key for operations that should only ever happen once.

    Used where the operation itself is naturally unique — confirming a given
    proposal, for instance, should produce exactly one order no matter how
    many times it's called. Not suitable where a repeat is legitimate: buying
    the same cart twice is a thing people do, so cart checkout takes a key
    from the caller instead of deriving one from its contents.
    """
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]
    return f"{operation}:{digest}"


def claim(key: str, operation: str, agent: str = None, request_id: str = None):
    """
    Try to take ownership of this key.

    Returns None if the caller now owns it and should execute. Returns the
    stored response dict if this key already completed — replay it rather
    than executing again. Raises InProgress if someone else holds it.
    """
    ref = db.collection(COLLECTION).document(key)

    try:
        ref.create({
            "operation": operation,
            "status": "in_progress",
            "ucp_agent": agent,
            "request_id": request_id,
            "created_at": firestore.SERVER_TIMESTAMP,
        })
        return None
    except (AlreadyExists, Conflict):
        pass

    existing = ref.get()
    if not existing.exists:
        # Vanished between the failed create and the read — treat as ours.
        return None

    data = existing.to_dict() or {}
    if data.get("status") == "completed":
        return data.get("response") or {}
    raise InProgress(f"Operation {operation} with this key is already running")


def complete(key: str, response: dict) -> None:
    db.collection(COLLECTION).document(key).set({
        "status": "completed",
        "response": response,
        "completed_at": firestore.SERVER_TIMESTAMP,
    }, merge=True)


def release(key: str) -> None:
    """
    Drop the key so a failed operation can be retried.

    Deliberately a delete rather than a "failed" marker: if the work didn't
    happen, the caller should be able to try again with the same key and get
    a real attempt, not a replayed error.
    """
    try:
        db.collection(COLLECTION).document(key).delete()
    except Exception as exc:
        print(f"[idempotency] could not release {key}: {exc}")
