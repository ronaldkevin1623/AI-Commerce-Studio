import firebase_admin
from firebase_admin import credentials, firestore
from app.config import FIREBASE_CREDENTIALS_PATH

cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()


def log_decision(action_type: str, amount_paise: int, decision: str,
                  reason: str, order_id: str = None, customer_id: str = None):
    doc_ref = db.collection("decisions").document()
    doc_ref.set({
        "action_type": action_type,
        "amount_paise": amount_paise,
        "decision": decision,
        "reason": reason,
        "order_id": order_id,
        "customer_id": customer_id,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })
    return doc_ref.id


def get_or_create_customer(name: str, email: str) -> dict:
    customers = db.collection("customers").where("email", "==", email).limit(1).get()
    if customers:
        doc = customers[0]
        return {"id": doc.id, **doc.to_dict()}

    doc_ref = db.collection("customers").document()
    data = {
        "name": name,
        "email": email,
        "trust_score": 100,
        "total_spend_paise": 0,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    doc_ref.set(data)
    return {"id": doc_ref.id, **data}


def adjust_trust_score(customer_id: str, delta: int):
    customer_ref = db.collection("customers").document(customer_id)
    customer_ref.update({"trust_score": firestore.Increment(delta)})


def save_order(order_id: str, razorpay_order_id: str, amount_paise: int,
               product_name: str, customer_id: str, status: str = "created"):
    db.collection("orders").document(order_id).set({
        "razorpay_order_id": razorpay_order_id,
        "amount_paise": amount_paise,
        "product_name": product_name,
        "customer_id": customer_id,
        "status": status,
        "created_at": firestore.SERVER_TIMESTAMP,
    })


def update_order_status(razorpay_order_id: str, status: str):
    orders = db.collection("orders").where(
        "razorpay_order_id", "==", razorpay_order_id).limit(1).get()
    if orders:
        orders[0].reference.update({"status": status})


def log_refund(refund_id: str, order_id: str, amount_paise: int, reason: str):
    db.collection("refunds").document(refund_id).set({
        "order_id": order_id,
        "amount_paise": amount_paise,
        "reason": reason,
        "timestamp": firestore.SERVER_TIMESTAMP,
    })