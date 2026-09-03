"""
AGENTIC COMMERCE PROTOCOL — A SECOND AGENT SURFACE OVER THE SAME STORE.

ACP is the open standard from OpenAI, Stripe and Meta for agent-initiated
checkout. This implements its agentic-checkout endpoints against the SAME
merchant store, the same catalogue and the same stock rules that UCP already
talks to:

    POST   /acp/checkout_sessions
    POST   /acp/checkout_sessions/{id}
    GET    /acp/checkout_sessions/{id}
    POST   /acp/checkout_sessions/{id}/complete
    POST   /acp/checkout_sessions/{id}/cancel

WHY THIS IS WORTH HAVING RATHER THAN A SECOND CODEBASE

The store already had one agent protocol. Adding a second on top of the same
`app.merchant.store` is the test of whether the shop is genuinely
protocol-agnostic or whether UCP had leaked into it. Nothing in the store
changed to add this — the buyer sends ids and quantities, the merchant
prices its own goods, and stock is checked in one place regardless of which
protocol asked.

WHAT IS FAITHFUL AND WHAT IS NOT

Faithful: the paths, the required headers (Authorization, Idempotency-Key,
API-Version), the CheckoutSession shape, the status vocabulary, the `totals`
array with typed entries, and `messages` for anything the buyer needs told.
Taken from the published OpenAPI at spec/2026-04-17.

Not faithful, and labelled in the payload rather than hidden:

  * Payment completes through **Razorpay**, not through ACP's delegated
    payment token flow. `POST .../complete` takes a Razorpay payment id and
    verifies it with the provider. A real ACP agent sending a `payment_data`
    vault token will get a clear error naming what this build supports.
  * Only the fields this store can populate honestly are returned. The spec
    has many optional fields — dimensions, marketplace seller details, tax
    exemption reasons — and emitting empty scaffolding for them would
    suggest support that does not exist.
"""
import time
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.merchant import store

router = APIRouter(prefix="/acp", tags=["acp"])

API_VERSION = "2026-04-17"
CURRENCY = "inr"

# Idempotency-Key -> the session it created. ACP requires that replaying a
# request with the same key does not create a second session; without this
# a retried network call quietly doubles somebody's order.
_IDEMPOTENCY: dict = {}


def _require_headers(authorization: str | None, api_version: str | None):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"type": "error", "code": "unauthorized",
                    "message": "ACP requires an Authorization header."})
    if api_version and api_version != API_VERSION:
        raise HTTPException(
            status_code=400,
            detail={"type": "error", "code": "unsupported_api_version",
                    "message": f"This store speaks ACP {API_VERSION}."})


def _totals(subtotal_paise: int) -> list[dict]:
    """
    The typed totals array ACP expects.

    No tax or fulfilment line is emitted, because this store charges
    neither. Returning a zero tax row would imply tax was computed and
    found to be nothing, which is a different statement from "not charged".
    """
    return [
        {"type": "items_base_amount", "display_text": "Items",
         "amount": subtotal_paise},
        {"type": "subtotal", "display_text": "Subtotal",
         "amount": subtotal_paise},
        {"type": "total", "display_text": "Total", "amount": subtotal_paise},
    ]


def _session_view(session: dict) -> dict:
    """Map the store's own session onto the ACP CheckoutSession shape."""
    subtotal = int(session.get("total_paise") or 0)
    status_map = {
        "awaiting_payment": "ready_for_payment",
        "paid": "completed",
        "cancelled": "canceled",
        "open": "not_ready_for_payment",
    }
    messages = []
    if session.get("status") == "awaiting_payment":
        messages.append({
            "type": "info", "severity": "info",
            "content_type": "text/plain",
            "content": ("Complete this session with a Razorpay payment id. "
                        "This store settles through Razorpay rather than an "
                        "ACP delegated payment token."),
        })
    return {
        "id": session.get("id"),
        "protocol": {"name": "acp", "version": API_VERSION},
        "status": status_map.get(session.get("status"), "incomplete"),
        "currency": CURRENCY,
        "line_items": [{
            "id": item.get("id"),
            "item": {"id": item.get("id"), "name": item.get("name"),
                     "unit_amount": int(item.get("unit_price_paise") or 0)},
            "quantity": int(item.get("quantity") or 1),
            "name": item.get("name"),
            "unit_amount": int(item.get("unit_price_paise") or 0),
            "totals": [{"type": "total", "display_text": "Line total",
                        "amount": int(item.get("amount_paise") or 0)}],
        } for item in (session.get("line_items") or [])],
        "totals": _totals(subtotal),
        "messages": messages,
        "links": [{"type": "terms_of_use",
                   "url": "/merchant/.well-known/ucp"}],
        "created_at": session.get("created_at"),
        "capabilities": {
            "payment_handlers": ["razorpay"],
            "delegated_payment_tokens": False,
            "note": ("Settles through Razorpay. ACP delegated payment tokens "
                     "are not supported by this build."),
        },
        "metadata": {"razorpay_order_id": session.get("razorpay_order_id")},
    }


class LineItemIn(BaseModel):
    id: str
    quantity: int = 1


class CreateSession(BaseModel):
    items: list[LineItemIn] = []
    buyer: dict | None = None


@router.post("/checkout_sessions")
def create_session(body: CreateSession,
                   authorization: str = Header(None),
                   idempotency_key: str = Header(None, alias="Idempotency-Key"),
                   api_version: str = Header(None, alias="API-Version")):
    _require_headers(authorization, api_version)
    if not body.items:
        raise HTTPException(
            status_code=400,
            detail={"type": "error", "code": "invalid_request",
                    "message": "A checkout session needs at least one item."})

    # A replayed key returns the SAME session rather than a second one.
    if idempotency_key and idempotency_key in _IDEMPOTENCY:
        existing = store.get_session(_IDEMPOTENCY[idempotency_key])
        if existing:
            return _session_view(existing)

    # The SAME function UCP checkout uses. Stock, pricing and the refusal
    # to sell a draft are enforced once, in the store, for both protocols.
    result = store.create_session(
        [{"id": i.id, "quantity": i.quantity} for i in body.items],
        buyer=(body.buyer or {"name": "ACP agent",
                              "email": "agent@acp.local"}))
    if not result.get("ok"):
        raise HTTPException(
            status_code=409,
            detail={"type": "error", "code": "unavailable",
                    "message": result.get("error", "Cannot open that cart.")})

    session_id = result["session"]["id"]
    if idempotency_key:
        _IDEMPOTENCY[idempotency_key] = session_id
    session = store.get_session(session_id) or {}
    from app.firebase_client import log_decision
    log_decision(
        action_type="acp_session_opened",
        amount_paise=int(session.get("total_paise") or 0),
        decision="allowed",
        reason=(f"ACP {API_VERSION} checkout session {session_id} opened over "
                f"the same store UCP uses. The buyer sent ids and quantities; "
                f"the merchant priced it."),
    )
    return _session_view(session)


@router.get("/checkout_sessions/{session_id}")
def read_session(session_id: str,
                 authorization: str = Header(None),
                 api_version: str = Header(None, alias="API-Version")):
    _require_headers(authorization, api_version)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404,
                            detail={"type": "error", "code": "not_found",
                                    "message": "No such checkout session."})
    return _session_view(session)


class UpdateSession(BaseModel):
    items: list[LineItemIn] | None = None


@router.post("/checkout_sessions/{session_id}")
def update_session(session_id: str, body: UpdateSession,
                   authorization: str = Header(None),
                   api_version: str = Header(None, alias="API-Version")):
    """
    ACP allows a session to be updated. This store does not re-price an
    open session, so it says so rather than silently ignoring the change.
    """
    _require_headers(authorization, api_version)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404,
                            detail={"type": "error", "code": "not_found",
                                    "message": "No such checkout session."})
    if body.items:
        view = _session_view(session)
        view["messages"] = view.get("messages", []) + [{
            "type": "error", "code": "not_supported", "severity": "error",
            "content_type": "text/plain",
            "content": ("This store cannot re-price an open session. Cancel "
                        "it and open a new one with the items you want."),
        }]
        return view
    return _session_view(session)


class CompleteSession(BaseModel):
    # ACP's own field. Accepted so a spec-compliant agent gets a precise
    # error rather than a schema rejection it cannot interpret.
    payment_data: dict | None = None
    razorpay_payment_id: str | None = None


@router.post("/checkout_sessions/{session_id}/complete")
def complete_session(session_id: str, body: CompleteSession,
                     authorization: str = Header(None),
                     idempotency_key: str = Header(None, alias="Idempotency-Key"),
                     api_version: str = Header(None, alias="API-Version")):
    _require_headers(authorization, api_version)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404,
                            detail={"type": "error", "code": "not_found",
                                    "message": "No such checkout session."})

    if body.payment_data and not body.razorpay_payment_id:
        raise HTTPException(
            status_code=422,
            detail={"type": "error", "code": "unsupported_payment_handler",
                    "message": ("This store settles through Razorpay and does "
                                "not accept ACP delegated payment tokens. "
                                "Send razorpay_payment_id instead. The "
                                "capability is declared as false on the "
                                "session rather than left to be discovered "
                                "here.")})
    if not body.razorpay_payment_id:
        raise HTTPException(
            status_code=400,
            detail={"type": "error", "code": "payment_required",
                    "message": "razorpay_payment_id is required to complete."})

    # Settled through the store's existing path — the same verification a
    # UCP checkout gets, because it is literally the same function.
    # Delegated to the UCP settle handler rather than reimplemented: the
    # payment is verified with Razorpay, the order id is checked against the
    # session, and stock is released — identically for both protocols,
    # because it is the same code path.
    from app.routes.merchant_store_routes import Settle
    from app.routes.merchant_store_routes import settle as ucp_settle
    try:
        ucp_settle(session_id, Settle(razorpay_payment_id=body.razorpay_payment_id))
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"type": "error", "code": "payment_not_verified",
                    "message": str(exc.detail)})
    return _session_view(store.get_session(session_id) or {})


@router.post("/checkout_sessions/{session_id}/cancel")
def cancel_session(session_id: str,
                   authorization: str = Header(None),
                   api_version: str = Header(None, alias="API-Version")):
    _require_headers(authorization, api_version)
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404,
                            detail={"type": "error", "code": "not_found",
                                    "message": "No such checkout session."})
    if session.get("status") == "paid":
        raise HTTPException(
            status_code=409,
            detail={"type": "error", "code": "already_completed",
                    "message": "A paid session cannot be cancelled. Refund it."})
    session["status"] = "cancelled"
    store.db.collection(store.SESSIONS).document(session_id).set(session)
    return _session_view(session)
