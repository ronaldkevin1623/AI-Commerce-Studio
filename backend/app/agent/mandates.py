"""
MANDATE CHAIN — an AP2-shaped proof of what the person actually authorised.

AP2 (Agent Payments Protocol) is Google's open standard for agent payments,
announced in September 2025 and donated to the FIDO Alliance in April 2026.
It represents a purchase as a chain of signed mandates: the constraints the
person agreed to, the cart the agent assembled, and the payment that follows —
each cryptographically bound to the one before it, so none can be swapped out
after the fact.

AI Commerce Studio already had the shape of this informally: Intent parses constraints,
the risk gate enforces bounds, and the audit trail records the outcome. What
was missing was proof. A logged row says "we checked"; a verified chain says
"here is the signature, check it yourself".

WHAT THIS CHAIN HONESTLY PROVES:
    The order that reached Razorpay matches the constraints the person
    approved, and neither the constraints nor the cart were altered between
    approval and charge.

WHAT IT DOES NOT PROVE — AND WHY:
    In real AP2 the *merchant* signs the inner checkout JWT with their own
    key, and the agent wraps that signature. AI Commerce Studio has no signing
    relationship with eBay sellers — Browse API is read-only and there is no
    merchant handshake — so AI Commerce Studio signs both roles here. That means the
    chain carries no evidence the seller agreed to anything. It is a
    self-attestation by the agent, not a two-party agreement, and the UI says
    so rather than letting a lock icon imply otherwise.

This is deliberately useful rather than ceremonial: eBay prices are live and
move. The cart mandate binds the price the person saw at approval. If the
price has changed by the time the order is created, the chain fails
verification and the purchase is blocked — a real protection that the
procedural gate alone did not provide.

No new dependencies: PyJWT and cryptography already ship with firebase-admin.
"""
import base64
import hashlib
import json
import os
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ALGORITHM = "ES256"
AGENT_ISSUER = "commerce-studio-agent"
# Named to be self-incriminating on purpose: this is AI Commerce Studio standing in for
# a merchant it has no relationship with, and the name should say that.
MERCHANT_PROXY_ISSUER = "commerce-studio-merchant-proxy"

INTENT_VCT = "mandate.checkout.open.1"
CART_VCT = "mandate.checkout.1"
CHECKOUT_VCT = "checkout.cart.1"

# A run that sits open for hours shouldn't still be chargeable on yesterday's
# price. Short enough to matter, long enough for a person to think.
INTENT_TTL_SECONDS = 30 * 60
CART_TTL_SECONDS = 15 * 60

_KEY_PATH = Path(os.getenv("MANDATE_KEY_PATH", "./mandate_signing_key.pem"))
_key = None


def _load_key():
    """
    Load the signing key, generating one on first run.

    The private key is written next to the service account key and is
    gitignored for the same reason. Losing it only invalidates old mandates;
    it does not lose money or orders.
    """
    global _key
    if _key is not None:
        return _key

    if _KEY_PATH.exists():
        _key = serialization.load_pem_private_key(_KEY_PATH.read_bytes(), password=None)
        return _key

    _key = ec.generate_private_key(ec.SECP256R1())
    _KEY_PATH.write_bytes(
        _key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    print(f"[mandates] generated a new ES256 signing key at {_KEY_PATH}")
    return _key


def _public_pem() -> bytes:
    return _load_key().public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _private_pem() -> bytes:
    return _load_key().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _b64(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).decode().rstrip("=")


def public_jwk() -> dict:
    """The public key, so anyone can verify a mandate without asking us."""
    numbers = _load_key().public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64(numbers.x),
        "y": _b64(numbers.y),
        "alg": ALGORITHM,
        "use": "sig",
    }
    jwk["kid"] = thumbprint()
    return jwk


def thumbprint() -> str:
    """RFC 7638-style thumbprint over the canonical public key members."""
    numbers = _load_key().public_key().public_numbers()
    canonical = json.dumps(
        {"crv": "P-256", "kty": "EC", "x": _b64(numbers.x), "y": _b64(numbers.y)},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _sign(claims: dict) -> str:
    return jwt.encode(claims, _private_pem(), algorithm=ALGORITHM)


def _decode(token: str) -> dict:
    return jwt.decode(token, _public_pem(), algorithms=[ALGORITHM])


# ── Issuing ──────────────────────────────────────────────────────────────

def issue_intent_mandate(intent: dict, customer_id: str) -> str:
    """
    The constraints the person's request actually established, signed before
    a single listing has been fetched — so the bounds can't be widened later
    to fit whatever the agent happened to find.
    """
    now = int(time.time())
    return _sign({
        "vct": INTENT_VCT,
        "iss": AGENT_ISSUER,
        "sub": customer_id,
        "iat": now,
        "exp": now + INTENT_TTL_SECONDS,
        "cnf": {"jkt": thumbprint()},
        "constraints": {
            "checkout.max_amount_paise": int(intent.get("max_price_paise") or 0),
            "checkout.category": intent.get("category"),
            "checkout.priority": intent.get("priority"),
            # The venues this authorisation covers. Read by the risk gate,
            # which refuses an order against anything not named here — the
            # value used to say EBAY_US only, and nothing enforced it, so it
            # was a claim rather than a control.
            "checkout.allowed_marketplaces": ["ebay", "merchant"],
        },
    })


def allowed_venues(intent_jwt: str) -> set | None:
    """
    The venues an intent mandate authorises, or None if it names none.

    Returned as a set for the gate to test membership against. None means
    "unconstrained" and is deliberately distinct from an empty set, which
    would mean "nothing is allowed" — a mandate issued before this claim
    existed should not retroactively refuse every purchase.
    """
    try:
        claims = _decode(intent_jwt)
    except Exception:
        return None
    venues = (claims.get("constraints") or {}).get("checkout.allowed_marketplaces")
    if not venues:
        return None
    return {str(v).lower() for v in venues}


def issue_cart_mandate(intent_jwt: str, product: dict, customer_id: str) -> dict:
    """
    The specific cart the person chose, bound to the intent that authorised it.

    Returns the outer mandate plus the parts a UI needs to show the chain.
    """
    now = int(time.time())
    amount = int(product.get("price_paise") or 0)

    # A multi-unit line carries its unit price explicitly. Without it the
    # verifier can only see a total, and cannot tell three affordable items
    # from one unaffordable one.
    quantity = max(1, int(product.get("quantity") or 1))
    unit = int(product.get("unit_price_paise") or (amount // quantity if quantity else amount))

    checkout_jwt = _sign({
        "vct": CHECKOUT_VCT,
        "iss": MERCHANT_PROXY_ISSUER,
        "iat": now,
        "exp": now + CART_TTL_SECONDS,
        "line_items": [{
            "id": str(product.get("id")),
            "name": product.get("name"),
            "amount_paise": amount,
            "unit_price_paise": unit,
            "quantity": quantity,
        }],
        "total_paise": amount,
        "unit_price_paise": unit,
        "quantity": quantity,
        "currency": "INR",
    })

    cart_jwt = _sign({
        "vct": CART_VCT,
        "iss": AGENT_ISSUER,
        "sub": customer_id,
        "iat": now,
        "exp": now + CART_TTL_SECONDS,
        "checkout_jwt": checkout_jwt,
        "checkout_hash": digest(checkout_jwt),
        "intent_hash": digest(intent_jwt),
    })

    return {
        "cart_jwt": cart_jwt,
        "checkout_jwt": checkout_jwt,
        "checkout_hash": digest(checkout_jwt),
        "intent_hash": digest(intent_jwt),
        "total_paise": amount,
    }


# ── Verifying ────────────────────────────────────────────────────────────

def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def verify_chain(intent_jwt: str, cart_jwt: str, product: dict = None) -> dict:
    """
    Verify the whole chain, returning every individual check.

    Returning the checks rather than a bare boolean is the point: the UI can
    show which link held and which broke, and a failure names its own reason
    in the audit trail instead of "verification failed".
    """
    checks: list[dict] = []

    try:
        intent = _decode(intent_jwt)
        checks.append(_check("Intent mandate signature", True, f"ES256, issuer {intent.get('iss')}"))
    except jwt.ExpiredSignatureError:
        checks.append(_check("Intent mandate signature", False, "Intent mandate has expired"))
        return {"ok": False, "checks": checks, "reason": "Intent mandate has expired"}
    except Exception as exc:
        checks.append(_check("Intent mandate signature", False, str(exc)))
        return {"ok": False, "checks": checks, "reason": f"Intent mandate invalid: {exc}"}

    try:
        cart = _decode(cart_jwt)
        checks.append(_check("Cart mandate signature", True, f"ES256, issuer {cart.get('iss')}"))
    except jwt.ExpiredSignatureError:
        checks.append(_check("Cart mandate signature", False, "Cart mandate has expired"))
        return {"ok": False, "checks": checks, "reason": "Cart mandate has expired"}
    except Exception as exc:
        checks.append(_check("Cart mandate signature", False, str(exc)))
        return {"ok": False, "checks": checks, "reason": f"Cart mandate invalid: {exc}"}

    # The cart names the intent it came from.
    intent_bound = cart.get("intent_hash") == digest(intent_jwt)
    checks.append(_check(
        "Cart is bound to this intent",
        intent_bound,
        f"sha256(intent) {cart.get('intent_hash', '')[:16]}…",
    ))

    # The inner checkout hasn't been swapped for a different one.
    checkout_jwt = cart.get("checkout_jwt", "")
    hash_bound = cart.get("checkout_hash") == digest(checkout_jwt)
    checks.append(_check(
        "Checkout hash matches",
        hash_bound,
        f"sha256(checkout) {cart.get('checkout_hash', '')[:16]}…",
    ))

    try:
        checkout = _decode(checkout_jwt)
        checks.append(_check("Checkout signature", True, f"issuer {checkout.get('iss')}"))
    except Exception as exc:
        checks.append(_check("Checkout signature", False, str(exc)))
        return {"ok": False, "checks": checks, "reason": f"Checkout JWT invalid: {exc}"}

    # The approved ceiling describes one item, so that is what it is checked
    # against. The basket total is the risk gate's business — it holds the
    # per-order limit and the session ceiling, and escalates to a human when
    # either is exceeded.
    constraints = intent.get("constraints") or {}
    ceiling = int(constraints.get("checkout.max_amount_paise") or 0)
    total = int(checkout.get("total_paise") or 0)
    quantity = max(1, int(checkout.get("quantity") or 1))
    unit = int(checkout.get("unit_price_paise") or (total // quantity if quantity else total))

    within = bool(ceiling) and unit <= ceiling
    detail = f"₹{unit / 100:,.2f} against ₹{ceiling / 100:,.2f}"
    if quantity > 1:
        detail += f" per item · {quantity} x = ₹{total / 100:,.2f}, bounded by the risk gate"
    checks.append(_check("Item within approved ceiling", within, detail))

    # Live marketplace prices move. If the product about to be charged no
    # longer matches the one the mandate was signed over, the chain fails —
    # this is the check that earns the whole mechanism its place.
    if product is not None:
        line_items = checkout.get("line_items") or []
        signed = line_items[0] if line_items else {}
        current = int(product.get("price_paise") or 0)
        same_item = str(signed.get("id")) == str(product.get("id"))
        same_price = int(signed.get("amount_paise") or 0) == current
        checks.append(_check(
            "Item unchanged since approval",
            same_item,
            f"{signed.get('id')} vs {product.get('id')}",
        ))
        checks.append(_check(
            "Price unchanged since approval",
            same_price,
            f"signed ₹{int(signed.get('amount_paise') or 0) / 100:,.2f} vs "
            f"now ₹{current / 100:,.2f}",
        ))

    failed = [c for c in checks if not c["ok"]]
    return {
        "ok": not failed,
        "checks": checks,
        "reason": failed[0]["detail"] if failed else "Full chain verified",
        "failed_check": failed[0]["name"] if failed else None,
    }


def summarise(intent_jwt: str, cart_jwt: str) -> dict:
    """A UI-friendly view of the chain, with the disclosure attached."""
    try:
        intent = _decode(intent_jwt)
        cart = _decode(cart_jwt)
        checkout = _decode(cart.get("checkout_jwt", ""))
    except Exception:
        return {}

    return {
        "algorithm": ALGORITHM,
        "key_id": thumbprint(),
        "links": [
            {
                "vct": intent.get("vct"),
                "label": "Intent mandate",
                "issuer": intent.get("iss"),
                "hash": digest(intent_jwt),
                "issued_at": intent.get("iat"),
                "expires_at": intent.get("exp"),
                "body": intent.get("constraints"),
            },
            {
                "vct": checkout.get("vct"),
                "label": "Checkout",
                "issuer": checkout.get("iss"),
                "hash": cart.get("checkout_hash"),
                "issued_at": checkout.get("iat"),
                "expires_at": checkout.get("exp"),
                "body": {
                    "line_items": checkout.get("line_items"),
                    "total_paise": checkout.get("total_paise"),
                },
            },
            {
                "vct": cart.get("vct"),
                "label": "Cart mandate",
                "issuer": cart.get("iss"),
                "hash": digest(cart_jwt),
                "issued_at": cart.get("iat"),
                "expires_at": cart.get("exp"),
                "body": {
                    "intent_hash": cart.get("intent_hash"),
                    "checkout_hash": cart.get("checkout_hash"),
                },
            },
        ],
        "disclosure": (
            "AI Commerce Studio signs both the agent and the merchant role in this chain. "
            "eBay's Browse API is read-only and there is no merchant handshake, so "
            "this proves the agent kept to the constraints the person approved — "
            "not that the seller agreed to anything."
        ),
    }
