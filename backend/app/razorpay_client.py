import razorpay
import hmac
import hashlib
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def create_order(amount_paise: int, receipt: str, notes: dict = None) -> dict:
    return client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "notes": notes or {},
        # Ask for the payment to be captured as soon as it is authorised.
        # Accounts set to manual capture ignore this, which is why
        # verify-payment also captures explicitly rather than trusting it.
        "payment_capture": 1,
    })


def fetch_payment(payment_id: str) -> dict:
    return client.payment.fetch(payment_id)


def capture_payment(payment_id: str, amount_paise: int, currency: str = "INR") -> dict:
    """
    Capture a payment that Razorpay has authorised but not yet settled.

    Only ever called for a payment already authorised against this order —
    it finishes the transaction the person started, and cannot move money
    that was not already committed.
    """
    return client.payment.capture(payment_id, amount_paise, {"currency": currency})


def create_refund(payment_id: str, amount_paise: int = None, notes: dict = None) -> dict:
    payload = {"notes": notes or {}}
    if amount_paise is not None:
        payload["amount"] = amount_paise
    return client.payment.refund(payment_id, payload)


def get_or_create_razorpay_customer(name: str, email: str, contact: str = "") -> dict:
    try:
        existing = client.customer.all({"email": email})
        if existing.get("items"):
            return existing["items"][0]
    except Exception:
        pass
    return client.customer.create({"name": name, "email": email, "contact": contact})


def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    expected_signature = hmac.new(
        key=RAZORPAY_WEBHOOK_SECRET.encode(),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)