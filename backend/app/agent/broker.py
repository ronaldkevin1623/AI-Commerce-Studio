"""
PURCHASE BROKER — the single gate, behind two front doors.

AI Commerce Studio's console drives the gate over a WebSocket. An external agent
(Claude, or anything else speaking MCP) drives the same gate through this
module. Both go through identical checks, write to the same audit trail, and
sign the same mandate chain. There is no "API mode" that skips a step.

THE PROPERTY THIS MODULE EXISTS TO PROTECT:
    A caller cannot approve its own purchase.

`propose` evaluates and records a verdict. `confirm` re-evaluates from
scratch — it never trusts the proposal's stored verdict, because a stored
verdict is just a claim, and the caller may have had time to change the
world since. If the re-evaluation escalates, `confirm` refuses and parks the
proposal for a human. The calling agent has no tool that can clear that
state; only a person in AI Commerce Studio's own UI can. That boundary is the whole
point of exposing the agent over MCP at all — an autonomous buyer that could
wave itself through would be a worse thing than no autonomous buyer.
"""
import time
import uuid

from app.agent.catalog import search_catalog
from app.agent.trust_agent import assess as trust_assess
from app.agent.budget_agent import assess as budget_assess
from app.agent.risk_gate import evaluate as risk_evaluate
from app.agent.mandates import issue_intent_mandate, issue_cart_mandate, verify_chain
from app.firebase_client import (
    db,
    get_or_create_customer,
    log_decision,
    save_order,
    adjust_trust_score,
    log_market_scan,
)
from app.razorpay_client import create_order
from app.agent import idempotency
from firebase_admin import firestore

PROPOSALS = "proposals"

# Terminal states a proposal can never leave.
FINAL = {"ordered", "denied", "blocked"}


def _now() -> int:
    return int(time.time())


# ── Search ───────────────────────────────────────────────────────────────

def search(query: str, max_price_inr: int) -> dict:
    """
    Real eBay search with the same trust screening the console applies.

    Read-only and free of side effects apart from the market scan record,
    so an external agent can browse without any gate involvement.
    """
    max_price_paise = int(max_price_inr) * 100
    candidates = search_catalog(query, max_price_paise)
    if not candidates:
        return {"query": query, "count": 0, "products": [], "note": "No listings matched."}

    trust = trust_assess(candidates)
    candidates = trust["candidates"]

    try:
        log_market_scan(query, candidates, trust["flagged"])
    except Exception as exc:
        print(f"[broker] market scan not recorded: {exc}")

    products = [{
        "id": str(c["id"]),
        "name": c["name"],
        "price_inr": round((c.get("price_paise") or 0) / 100, 2),
        "discount_percent": c.get("discount_percent"),
        "condition": c.get("condition"),
        "seller_feedback": c.get("seller_feedback"),
        "delivery_days": c.get("delivery_days"),
        "url": c.get("url"),
        "trust_ok": bool((c.get("trust") or {}).get("ok", True)),
        "trust_flags": (c.get("trust") or {}).get("reasons") or [],
    } for c in candidates[:20]]

    return {
        "query": query,
        "count": len(products),
        "flagged": trust["flagged"],
        "trust_summary": trust["summary"],
        "products": products,
        "disclosure": (
            "Prices converted from USD at a fixed approximate rate — eBay's Browse API "
            "has no India marketplace."
        ),
    }


def _find_product(product_id: str, query: str, max_price_inr: int) -> dict | None:
    """
    Fetch the listing straight from eBay by id.

    The caller supplies only an identifier; the price, condition and seller
    standing are all read from eBay here. An external agent therefore cannot
    understate what something costs to slip it under a spending bound —
    which matters a great deal more when the caller is another agent than
    when it is AI Commerce Studio's own console.
    """
    try:
        from app.agent.ebay_client import get_item
        item = get_item(product_id, category=query)
        if item:
            return item
    except Exception as exc:
        print(f"[broker] item lookup failed, falling back to search: {exc}")

    # Fallback for the static catalog (ids like "p1"), which has no item API.
    candidates = search_catalog(query, int(max_price_inr) * 100)
    return next((c for c in candidates if str(c["id"]) == str(product_id)), None)


# ── Propose ──────────────────────────────────────────────────────────────

def propose(product_id: str, query: str, max_price_inr: int,
            customer_email: str = "agent@commerce-studio.dev",
            customer_name: str = "MCP Agent") -> dict:
    """
    Run the full gate over a chosen listing without charging anything.

    Returns the verdict plus a proposal id. Nothing here moves money.
    """
    product = _find_product(product_id, query, max_price_inr)
    if not product:
        return {
            "ok": False,
            "error": f"Listing {product_id} is no longer in the results for '{query}'. "
                     "Search again — live listings come and go.",
        }

    customer = get_or_create_customer(customer_name, customer_email)
    intent = {
        "category": query,
        "max_price_paise": int(max_price_inr) * 100,
        "priority": "price",
    }

    intent_jwt = issue_intent_mandate(intent, customer["id"])
    cart = issue_cart_mandate(intent_jwt, product, customer["id"])

    budget = budget_assess(customer, product["price_paise"])
    # Dry run: proposing must not consume the duplicate window that
    # confirming will then be measured against.
    risk = risk_evaluate(customer, product, record=False)

    # A budget overrun is a block regardless of what the per-order gate says.
    decision = "blocked" if budget["status"] == "exceeded" else risk["decision"]
    reason = budget["summary"] if budget["status"] == "exceeded" else risk["reason"]

    proposal_id = f"prop-{uuid.uuid4().hex[:16]}"
    status = {
        "allowed": "ready",
        "escalated": "awaiting_human",
        "blocked": "blocked",
    }[decision]

    db.collection(PROPOSALS).document(proposal_id).set({
        "product": product,
        "query": query,
        "max_price_inr": int(max_price_inr),
        "customer_id": customer["id"],
        "customer_email": customer_email,
        "customer_name": customer_name,
        "decision": decision,
        "reason": reason,
        "budget": budget,
        "status": status,
        "source": "mcp",
        "intent_jwt": intent_jwt,
        "cart_jwt": cart["cart_jwt"],
        "created_at": firestore.SERVER_TIMESTAMP,
    })

    log_decision(
        action_type="mcp_proposal",
        amount_paise=product["price_paise"],
        decision=decision,
        reason=f"External agent proposed: {product['name'][:80]} — {reason}",
        customer_id=customer["id"],
    )

    if decision == "blocked":
        adjust_trust_score(customer["id"], -5)

    return {
        "ok": decision != "blocked",
        "proposal_id": proposal_id,
        "decision": decision,
        "reason": reason,
        "product": {"id": str(product["id"]), "name": product["name"],
                    "price_inr": round(product["price_paise"] / 100, 2)},
        "budget": budget["summary"],
        "next_step": {
            "allowed": "Call confirm_purchase with this proposal_id to create the order.",
            "escalated": (
                "A human must approve this before it can proceed. Open "
                "http://localhost:5173/approvals in AI Commerce Studio and approve it there, then "
                "call check_approval. You cannot approve this yourself."
            ),
            "blocked": "This purchase is refused and cannot proceed.",
        }[decision],
    }


# ── Confirm ──────────────────────────────────────────────────────────────

def _load(proposal_id: str) -> dict | None:
    doc = db.collection(PROPOSALS).document(proposal_id).get()
    return {"id": doc.id, **doc.to_dict()} if doc.exists else None


def _place_order(proposal: dict) -> dict:
    """Create the real Razorpay order. Only reached after every check passes."""
    product = proposal["product"]
    receipt = f"cp-{uuid.uuid4().hex[:16]}"

    order = create_order(
        amount_paise=product["price_paise"],
        receipt=receipt,
        notes={"customer_id": proposal["customer_id"], "source": "mcp"},
    )

    save_order(
        order_id=order["receipt"],
        razorpay_order_id=order["id"],
        amount_paise=product["price_paise"],
        product_name=product["name"],
        customer_id=proposal["customer_id"],
        product=product,
        mandates={
            "intent_jwt": proposal["intent_jwt"],
            "cart_jwt": proposal["cart_jwt"],
            "verified_at": _now(),
        },
    )

    db.collection(PROPOSALS).document(proposal["id"]).update({
        "status": "ordered",
        "order_id": order["receipt"],
        "razorpay_order_id": order["id"],
    })

    log_decision(
        action_type="mcp_order_created",
        amount_paise=product["price_paise"],
        decision="allowed",
        reason=f"External agent order created for {product['name'][:80]}",
        order_id=order["id"],
        customer_id=proposal["customer_id"],
    )
    adjust_trust_score(proposal["customer_id"], 2)

    return {
        "ok": True,
        "status": "ordered",
        "order_id": order["receipt"],
        "razorpay_order_id": order["id"],
        "amount_inr": round(product["price_paise"] / 100, 2),
        "checkout_note": (
            "The order exists in Razorpay test mode. Payment must be completed by a "
            "person at the checkout — an agent cannot complete it."
        ),
    }


def confirm(proposal_id: str, ucp_agent: str = None, request_id: str = None) -> dict:
    """
    Re-run every check and, only if they all pass, create the order.

    The stored verdict is deliberately ignored. Prices move, budgets move,
    and trust scores move; the only verdict worth acting on is one computed
    against the world as it is at the moment money would be committed.

    Idempotent by construction. The key is derived from the proposal rather
    than taken from the caller, because a proposal should yield exactly one
    order however many times an agent retries — and an MCP client retrying a
    timed-out call is ordinary behaviour. The status check below is not
    enough on its own: two concurrent confirms could both read "ready" and
    both charge, which is precisely the race an atomic claim removes.
    """
    key = idempotency.derive_key("confirm-purchase", proposal_id)
    try:
        replay = idempotency.claim(key, "confirm-purchase", agent=ucp_agent, request_id=request_id)
    except idempotency.InProgress:
        return {
            "ok": False,
            "status": "in_progress",
            "error": "This proposal is already being confirmed. Poll check_approval instead of retrying.",
        }
    if replay is not None:
        return {**replay, "idempotent_replay": True}

    try:
        result = _confirm_inner(proposal_id)
    except Exception:
        idempotency.release(key)
        raise

    # Only a created order is worth replaying. A refusal should be
    # re-evaluated on the next call, because the thing that caused it —
    # a budget, a price, a pending human decision — may have changed.
    if result.get("status") == "ordered":
        idempotency.complete(key, result)
    else:
        idempotency.release(key)
    return result


def _confirm_inner(proposal_id: str) -> dict:
    proposal = _load(proposal_id)
    if not proposal:
        return {"ok": False, "error": f"No proposal {proposal_id}"}

    if proposal["status"] == "ordered":
        return {"ok": True, "status": "ordered", "order_id": proposal.get("order_id"),
                "note": "Already ordered — this proposal was not charged twice."}
    if proposal["status"] in FINAL:
        return {"ok": False, "status": proposal["status"],
                "error": f"This proposal is {proposal['status']} and cannot proceed."}

    product = proposal["product"]
    customer = get_or_create_customer(
        proposal.get("customer_name", "MCP Agent"),
        proposal.get("customer_email", "agent@commerce-studio.dev"),
    )

    # Fresh evaluation — not the stored one.
    budget = budget_assess(customer, product["price_paise"])
    risk = risk_evaluate(customer, product)

    if budget["status"] == "exceeded":
        db.collection(PROPOSALS).document(proposal_id).update({"status": "blocked"})
        log_decision(action_type="mcp_confirm_blocked", amount_paise=product["price_paise"],
                     decision="blocked", reason=budget["summary"],
                     customer_id=proposal["customer_id"])
        return {"ok": False, "status": "blocked", "error": budget["summary"]}

    if risk["decision"] == "blocked":
        db.collection(PROPOSALS).document(proposal_id).update({"status": "blocked"})
        log_decision(action_type="mcp_confirm_blocked", amount_paise=product["price_paise"],
                     decision="blocked", reason=risk["reason"],
                     customer_id=proposal["customer_id"])
        return {"ok": False, "status": "blocked", "error": risk["reason"]}

    # Escalation is a hard stop for the caller. It cannot self-approve, and
    # there is no tool that lets it try.
    if risk["decision"] == "escalated" and proposal.get("human_decision") != "approved":
        db.collection(PROPOSALS).document(proposal_id).update({"status": "awaiting_human"})
        return {
            "ok": False,
            "status": "awaiting_human",
            "error": risk["reason"],
            "action_required": (
                "A human must approve this in AI Commerce Studio at http://localhost:5173/approvals. "
                "You cannot approve it yourself. Poll check_approval afterwards."
            ),
        }

    # The mandate chain is the last gate, and it catches the thing the
    # procedural checks cannot: the listing changing under us.
    chain = verify_chain(proposal["intent_jwt"], proposal["cart_jwt"], product)
    if not chain["ok"]:
        db.collection(PROPOSALS).document(proposal_id).update({"status": "blocked"})
        log_decision(action_type="mandate_rejected", amount_paise=product["price_paise"],
                     decision="blocked",
                     reason=f"{chain['failed_check']}: {chain['reason']}",
                     customer_id=proposal["customer_id"])
        return {"ok": False, "status": "blocked",
                "error": f"Mandate chain failed — {chain['failed_check']}: {chain['reason']}"}

    return _place_order(proposal)


# ── Human decision (from AI Commerce Studio's own UI, never from a tool) ───────────

def decide(proposal_id: str, approved: bool, note: str = None) -> dict:
    proposal = _load(proposal_id)
    if not proposal:
        return {"ok": False, "error": f"No proposal {proposal_id}"}
    if proposal["status"] in FINAL:
        return {"ok": False, "error": f"Proposal is already {proposal['status']}."}

    db.collection(PROPOSALS).document(proposal_id).update({
        "human_decision": "approved" if approved else "denied",
        "human_note": note,
        "status": "ready" if approved else "denied",
        "decided_at": firestore.SERVER_TIMESTAMP,
    })

    log_decision(
        action_type="escalation_resolved",
        amount_paise=(proposal["product"].get("price_paise") or 0),
        decision="allowed" if approved else "blocked",
        reason=f"Human {'approved' if approved else 'denied'} an external agent's purchase"
               + (f" — {note}" if note else ""),
        customer_id=proposal["customer_id"],
    )
    return {"ok": True, "status": "ready" if approved else "denied"}


def status(proposal_id: str) -> dict:
    proposal = _load(proposal_id)
    if not proposal:
        return {"ok": False, "error": f"No proposal {proposal_id}"}
    return {
        "ok": True,
        "proposal_id": proposal_id,
        "status": proposal["status"],
        "decision": proposal.get("decision"),
        "reason": proposal.get("reason"),
        "human_decision": proposal.get("human_decision"),
        "order_id": proposal.get("order_id"),
        "product": {
            "name": proposal["product"].get("name"),
            "price_inr": round((proposal["product"].get("price_paise") or 0) / 100, 2),
        },
        "next_step": (
            "Approved by a human — call confirm_purchase to create the order."
            if proposal.get("human_decision") == "approved" and proposal["status"] == "ready"
            else "Still waiting on a human decision at http://localhost:5173/approvals."
            if proposal["status"] == "awaiting_human"
            else None
        ),
    }


def pending(limit: int = 40) -> list[dict]:
    """Proposals a person still has to rule on."""
    docs = db.collection(PROPOSALS).where("status", "==", "awaiting_human").limit(limit).get()
    rows = [{"id": d.id, **d.to_dict()} for d in docs]
    return sorted(rows, key=lambda r: r.get("created_at") or 0, reverse=True)


def recent(limit: int = 40) -> list[dict]:
    docs = (
        db.collection(PROPOSALS)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .get()
    )
    return [{"id": d.id, **d.to_dict()} for d in docs]
