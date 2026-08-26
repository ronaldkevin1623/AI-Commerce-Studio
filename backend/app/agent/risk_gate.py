import time
from app.config import AUTO_APPROVE_LIMIT_PAISE

_recent_orders: dict[str, float] = {}
DUPLICATE_WINDOW_SECONDS = 60


def evaluate(customer: dict, product: dict) -> dict:
    amount = product["price_paise"]
    customer_id = customer["id"]

    if product["stock"] <= 0:
        return _result("blocked", "Product is out of stock")

    key = f"{customer_id}:{product['id']}"
    now = time.time()
    last_ordered = _recent_orders.get(key)
    if last_ordered and (now - last_ordered) < DUPLICATE_WINDOW_SECONDS:
        return _result(
            "blocked",
            f"Duplicate of an order placed {int(now - last_ordered)}s earlier"
        )

    if customer.get("trust_score", 100) < 40:
        return _result(
            "blocked",
            "Customer trust score too low for autonomous purchase"
        )

    if amount > AUTO_APPROVE_LIMIT_PAISE:
        return _result(
            "escalated",
            f"Amount ₹{amount / 100:.2f} exceeds auto-approve limit "
            f"of ₹{AUTO_APPROVE_LIMIT_PAISE / 100:.2f}"
        )

    _recent_orders[key] = now
    return _result("allowed", "Within spending bound, stock verified")


def _result(decision: str, reason: str) -> dict:
    return {"decision": decision, "reason": reason}