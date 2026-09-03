"""
HTTP 402 PAYMENT REQUIRED — THE x402 SHAPE, SETTLED OVER RAZORPAY.

WHAT THIS IS, PRECISELY

x402 is Coinbase's protocol for charging machines over HTTP: a resource
answers 402 with a machine-readable statement of what payment it wants, the
caller pays, retries with proof, and gets the resource. The transport shape
is what makes it useful — an agent can discover the price of something and
settle it without a human, with no prior integration.

This implements that shape with **Razorpay as the payment scheme**:

    GET  /x402/insights                -> 402 + PAYMENT-REQUIRED header
    POST /x402/authorize               -> creates the Razorpay order to pay
    GET  /x402/insights + PAYMENT-SIGNATURE -> 200 + the resource

WHAT THIS IS NOT, AND WILL NOT PRETEND TO BE

Canonical x402 settles onchain — USDC on Base, through a facilitator. There
is no crypto rail in this project and inventing one would be theatre. So:

  * this does NOT interoperate with USDC x402 facilitators or clients;
  * the `scheme` is declared as "razorpay" precisely so a real x402 client
    reads it, finds a scheme it does not support, and correctly declines
    rather than being misled into thinking it can pay;
  * the network field says "razorpay-test", not a chain id.

It is the x402 request/response contract carrying an INR rail. That is a
genuine thing to have built and a smaller claim than "we support x402".

ON THE SCHEMA

The field names follow the widely documented x402 v1 shape — `x402Version`
and an `accepts` array of payment requirements. The normative specification
could not be fetched while this was written, so the shape is taken from
secondary documentation and may differ in detail from the current spec.
Said here rather than left for someone to discover.
"""
import base64
import json
import time

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel

router = APIRouter(prefix="/x402", tags=["x402"])

X402_VERSION = 1

# What the paywalled resource costs. Small on purpose: this is a
# demonstration of the protocol, not a revenue stream.
PRICE_PAISE = 4900
RESOURCE = "/x402/insights"


def _requirements(base_url: str) -> dict:
    return {
        "x402Version": X402_VERSION,
        "accepts": [{
            # Deliberately not an onchain scheme. A real x402 client should
            # read this, not recognise it, and decline — which is the
            # correct outcome, not a bug.
            "scheme": "razorpay",
            "network": "razorpay-test",
            "maxAmountRequired": str(PRICE_PAISE),
            "asset": "INR",
            "assetDecimals": 2,
            "resource": RESOURCE,
            "description": ("Storefront analytics computed from this store's "
                            "own decision log — funnel, abandonment stages "
                            "and block reasons."),
            "mimeType": "application/json",
            "payTo": "razorpay:acct_test",
            "maxTimeoutSeconds": 600,
            "extra": {
                "authorize": "/x402/authorize",
                "settlement": "Razorpay order + payment verification",
                "note": ("This is the x402 request/response shape carrying an "
                         "INR rail. It does not settle onchain and will not "
                         "interoperate with USDC x402 facilitators."),
            },
        }],
        "error": "payment_required",
    }


def _encode(payload: dict) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _decode(header_value: str) -> dict:
    try:
        return json.loads(base64.b64decode(header_value).decode())
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"PAYMENT-SIGNATURE must be base64-encoded JSON: {exc}")


@router.get("/insights")
def paid_insights(response: Response,
                  payment_signature: str = Header(None, alias="PAYMENT-SIGNATURE")):
    """
    A resource that costs money, and says so in a way a machine can act on.

    Without proof of payment this answers 402 and describes what it wants.
    With proof, it verifies against Razorpay — never against the header
    alone, because a caller that can assert its own payment can assert
    anything.
    """
    requirements = _requirements("")

    if not payment_signature:
        body = dict(requirements)
        body["message"] = (
            f"₹{PRICE_PAISE / 100:,.2f} required for {RESOURCE}. POST to "
            f"/x402/authorize to get a Razorpay order, pay it, then retry "
            f"this request with a PAYMENT-SIGNATURE header.")
        return Response(
            status_code=402,
            media_type="application/json",
            content=json.dumps(body),
            headers={"PAYMENT-REQUIRED": _encode(requirements)},
        )

    proof = _decode(payment_signature)
    payment_id = proof.get("razorpay_payment_id")
    order_id = proof.get("razorpay_order_id")
    if not payment_id or not order_id:
        raise HTTPException(
            status_code=400,
            detail="PAYMENT-SIGNATURE needs razorpay_payment_id and "
                   "razorpay_order_id.")

    # VERIFIED WITH THE PROVIDER, NOT WITH THE CALLER.
    from app.razorpay_client import fetch_payment
    try:
        payment = fetch_payment(payment_id)
    except Exception as exc:
        raise HTTPException(status_code=402,
                            detail=f"That payment could not be verified with "
                                   f"Razorpay: {exc}")

    if payment.get("status") != "captured":
        raise HTTPException(
            status_code=402,
            detail=f"Payment {payment_id} is {payment.get('status')!r}, not "
                   f"captured. The resource stays behind the paywall.")
    if payment.get("order_id") != order_id:
        raise HTTPException(status_code=402,
                            detail="That payment belongs to a different order.")
    if int(payment.get("amount") or 0) < PRICE_PAISE:
        raise HTTPException(
            status_code=402,
            detail=f"₹{int(payment.get('amount') or 0) / 100:,.2f} is less "
                   f"than the ₹{PRICE_PAISE / 100:,.2f} required.")

    from app.firebase_client import log_decision
    log_decision(
        action_type="x402_settled",
        amount_paise=int(payment.get("amount") or 0),
        decision="allowed",
        reason=(f"x402-shaped request for {RESOURCE} settled with Razorpay "
                f"payment {payment_id} against order {order_id}. Verified "
                f"with the provider, not from the caller's header."),
        order_id=order_id,
    )

    from app.routes.growth_routes import growth_insights  # the real payload
    try:
        data = growth_insights()
    except Exception:
        data = {"note": "Insights could not be computed right now."}

    settlement = {"success": True, "transaction": payment_id,
                  "network": "razorpay-test", "payer": payment.get("email")}
    response.headers["PAYMENT-RESPONSE"] = _encode(settlement)
    return {"resource": RESOURCE, "paid_paise": int(payment.get("amount") or 0),
            "data": data}


class AuthorizeRequest(BaseModel):
    resource: str = RESOURCE


@router.post("/authorize")
def authorize(body: AuthorizeRequest):
    """
    Create the Razorpay order that settles the 402.

    The amount comes from this server's own price for the resource — the
    caller names what it wants, never what it will pay.
    """
    if body.resource != RESOURCE:
        raise HTTPException(status_code=404,
                            detail=f"Nothing priced at {body.resource!r}.")
    from app.razorpay_client import create_order
    try:
        order = create_order(PRICE_PAISE, f"x402-{int(time.time())}",
                             notes={"protocol": "x402-shape",
                                    "scheme": "razorpay",
                                    "resource": RESOURCE})
    except Exception as exc:
        raise HTTPException(status_code=502,
                            detail=f"Razorpay order could not be created: {exc}")
    return {
        "razorpay_order_id": order.get("id"),
        "amount_paise": PRICE_PAISE,
        "then": ("Pay this order, then retry the resource with a "
                 "PAYMENT-SIGNATURE header containing base64 JSON of "
                 "{razorpay_payment_id, razorpay_order_id}."),
    }
