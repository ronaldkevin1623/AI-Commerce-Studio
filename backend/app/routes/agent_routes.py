"""
The main pipeline endpoint. Uses a WebSocket so the frontend's
"reasoning stream" panel can show each step as it actually happens,
not just a final result.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.ollama_agent import parse_intent, rank_candidates
from app.agent.catalog import search_catalog
from app.agent.risk_gate import evaluate as risk_evaluate
from app.firebase_client import get_or_create_customer, log_decision, save_order, adjust_trust_score
from app.razorpay_client import create_order

router = APIRouter()


@router.websocket("/ws/agent")
async def agent_pipeline(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        user_text = data["message"]
        customer_email = data.get("email", "demo@cartpilot.dev")
        customer_name = data.get("name", "Demo User")

        await _send(websocket, "step", "Parsing intent into category, budget and priority")
        intent = parse_intent(user_text)

        await _send(websocket, "step",
                     f"Matching catalog under ₹{intent['max_price_paise'] / 100:.0f}")
        candidates = search_catalog(intent["category"], intent["max_price_paise"])

        if not candidates:
            await _send(websocket, "error", "No products matched — try relaxing your budget")
            await websocket.close()
            return

        # Show the top real candidates (with clickable links) before narrowing
        # to one — this is what the "top matching products" panel renders
        top_candidates = sorted(
            candidates,
            key=lambda p: (-(p.get("discount_percent") or 0), -p.get("rating", 0), p["price_paise"]),
        )[:5]
        await _send(websocket, "candidates", top_candidates)

        await _send(websocket, "step",
                     f"Ranking {len(candidates)} candidates by {intent['priority']}")
        result = rank_candidates(candidates, intent["priority"])
        product = result["product"]

        await _send(websocket, "match", {
            "product": product,
            "reason": result["reason"],
        })

        customer = get_or_create_customer(customer_name, customer_email)

        await _send(websocket, "step", "Running risk check before order creation")
        risk_result = risk_evaluate(customer, product)

        log_decision(
            action_type="purchase_attempt",
            amount_paise=product["price_paise"],
            decision=risk_result["decision"],
            reason=risk_result["reason"],
            customer_id=customer["id"],
        )

        await _send(websocket, "risk_gate", risk_result)

        if risk_result["decision"] == "blocked":
            adjust_trust_score(customer["id"], -5)
            await websocket.close()
            return

        if risk_result["decision"] == "escalated":
            # Frontend shows a real Approve/Deny UI and sends back a decision
            approval = await websocket.receive_json()
            if not approval.get("approved"):
                await _send(websocket, "step", "Human denied the escalated purchase")
                await websocket.close()
                return

        await _send(websocket, "step", "Creating Razorpay order")
        razorpay_order = create_order(
            amount_paise=product["price_paise"],
            receipt=f"cartpilot-{product['id']}-{customer['id']}",
            notes={"customer_id": customer["id"], "product_id": product["id"]},
        )

        save_order(
            order_id=razorpay_order["receipt"],
            razorpay_order_id=razorpay_order["id"],
            amount_paise=product["price_paise"],
            product_name=product["name"],
            customer_id=customer["id"],
        )

        adjust_trust_score(customer["id"], 2)

        await _send(websocket, "order_created", {
            "razorpay_order_id": razorpay_order["id"],
            "amount_paise": product["price_paise"],
            "product_name": product["name"],
            "customer_id": customer["id"],
        })
        # Frontend now opens Razorpay Checkout.js with this order_id.
        # Payment confirmation arrives separately via the webhook route.

    except WebSocketDisconnect:
        pass


async def _send(ws: WebSocket, event_type: str, payload):
    await ws.send_json({"type": event_type, "payload": payload})