"""
commerce-studio-demo-store — the merchant half of the loop.

The track asks for a merchant "transactable by an AI buyer end to end".
AI Commerce Studio was only ever the buyer: it searched eBay, which is a marketplace
it has no relationship with and cannot actually transact against. Nothing on
the seller's side of the handshake existed.

This is that side. A small first-party merchant with its own inventory, its
own UCP discovery document, and a checkout backed by Razorpay — so AI Commerce Studio
can discover it, be gated against it, and genuinely pay it.

ON THE INVENTORY BEING REAL:
These products are operator-declared, which is what a merchant's catalogue
always is — a shop's stock list is its own assertion, not an observation of
someone else's data. They are labelled throughout as the AI Commerce Studio Demo
Store's own goods. What would be dishonest is dressing them up as scraped
market data or implying a storefront that isn't ours; the UI and the
discovery document both name it as a demo store operated by this project.

ONE REAL LIMITATION, DISCLOSED:
Buyer and merchant share a single Razorpay test account here. A genuine
merchant would hold its own, and the money would move between two parties.
It does not — this proves the protocol and the gate, not settlement between
strangers.
"""
import time
import uuid

from firebase_admin import firestore

from app.firebase_client import db

PRODUCTS = "merchant_products"
SESSIONS = "merchant_checkouts"

MERCHANT_ID = "commerce-studio-demo-store"
MERCHANT_NAME = "Commerce Studio Demo Store"

# Ceiling for an inline product image. Firestore documents cap at 1 MiB and
# the catalogue endpoint reads every product on every agent search, so this
# is kept well below the hard limit rather than at it.
MAX_IMAGE_CHARS = 200_000

# Operator-declared stock. Prices in paise, INR.
SEED = [
    {
        "id": "cds-desk-lamp",
        "name": "Warm LED Desk Lamp, 3 brightness levels",
        "category": "home office",
        "price_paise": 149000,
        "stock": 24,
        "condition": "New",
        "description": "A dimmable desk lamp with a weighted base and a USB-C pass-through port.",
        "attributes": {"power": "9W", "colour_temperature": "2700K–4000K", "warranty_months": 12},
    },
    {
        "id": "cds-mech-keyboard",
        "name": "65% Mechanical Keyboard, hot-swappable",
        "category": "computer accessories",
        "price_paise": 489000,
        "stock": 11,
        "condition": "New",
        "description": "A compact 68-key board with hot-swap sockets, PBT keycaps and USB-C.",
        "attributes": {"layout": "65%", "switches": "linear", "connection": "USB-C", "warranty_months": 24},
    },
    {
        "id": "cds-usbc-hub",
        "name": "7-in-1 USB-C Hub with HDMI and card reader",
        "category": "computer accessories",
        "price_paise": 219000,
        "stock": 40,
        "condition": "New",
        "description": "HDMI 4K, two USB-A, USB-C power delivery, SD and microSD, and Ethernet.",
        "attributes": {"ports": 7, "hdmi": "4K30", "power_delivery_w": 100, "warranty_months": 12},
    },
    {
        "id": "cds-monitor-stand",
        "name": "Bamboo Monitor Stand with drawer",
        "category": "home office",
        "price_paise": 129000,
        "stock": 18,
        "condition": "New",
        "description": "A solid bamboo riser with a pull-out stationery drawer and cable slot.",
        "attributes": {"material": "bamboo", "max_load_kg": 20, "warranty_months": 6},
    },
    {
        "id": "cds-noise-earbuds",
        "name": "Active Noise Cancelling Earbuds, 30h case",
        "category": "audio",
        "price_paise": 349000,
        "stock": 15,
        "condition": "New",
        "description": "Hybrid ANC with transparency mode, USB-C charging and IPX5 splash resistance.",
        "attributes": {"anc": True, "battery_hours": 30, "water_resistance": "IPX5", "warranty_months": 12},
    },
    {
        "id": "cds-laptop-sleeve",
        "name": "Felt Laptop Sleeve, 14 inch",
        "category": "bags",
        "price_paise": 79000,
        "stock": 52,
        "condition": "New",
        "description": "Wool-blend felt sleeve with a magnetic closure and a front document pocket.",
        "attributes": {"fits_inches": 14, "material": "wool felt", "warranty_months": 3},
    },
]


def seed(force: bool = False) -> int:
    """Write the operator-declared catalogue. Idempotent unless forced."""
    written = 0
    for item in SEED:
        ref = db.collection(PRODUCTS).document(item["id"])
        if force or not ref.get().exists:
            ref.set({**item, "merchant_id": MERCHANT_ID,
                     "updated_at": firestore.SERVER_TIMESTAMP})
            written += 1
    return written


def _slug(text: str) -> str:
    """A readable document id, in the same shape as the seeded ones."""
    import re
    base = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:48]
    return f"cds-{base or uuid.uuid4().hex[:8]}"


def create_product(fields: dict) -> dict:
    """
    Add a product to the store's own catalogue.

    Validation lives here rather than in the route because these are the
    merchant's rules about its own goods: a price of zero or a negative stock
    count is not a formatting problem, it is a thing the shop will not sell.

    A draft is written but stays out of `search`, so it is never discoverable
    or purchasable by an agent until the operator publishes it. That is the
    whole point of having a status — a half-finished product that agents can
    already buy would be worse than no draft state at all.
    """
    name = (fields.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "A product needs a name."}

    try:
        price_paise = int(fields.get("price_paise") or 0)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Price must be a number."}
    if price_paise <= 0:
        return {"ok": False, "error": "Price must be more than zero."}

    try:
        stock = int(fields.get("stock") or 0)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Stock must be a whole number."}
    if stock < 0:
        return {"ok": False, "error": "Stock cannot be negative."}

    status = (fields.get("status") or "active").lower()
    if status not in ("active", "draft"):
        return {"ok": False, "error": "Status must be active or draft."}

    # Images are stored inline as data URIs, since this store has no file
    # storage. A Firestore document caps at 1 MiB, so an oversized picture has
    # to be refused here with a readable reason — otherwise the write fails
    # deep in the client library and the operator sees a stack trace instead
    # of "that image is too big".
    image = (fields.get("image") or "").strip()
    if len(image) > MAX_IMAGE_CHARS:
        return {
            "ok": False,
            "error": f"Image is {len(image) // 1024}KB, over the "
                     f"{MAX_IMAGE_CHARS // 1024}KB a product record can hold.",
        }

    product_id = (fields.get("id") or "").strip() or _slug(name)
    if db.collection(PRODUCTS).document(product_id).get().exists:
        # Two products of the same name are legitimate; silently overwriting
        # the first one is not.
        product_id = f"{product_id}-{uuid.uuid4().hex[:6]}"

    record = {
        "id": product_id,
        "name": name,
        "category": (fields.get("category") or "").strip() or None,
        "price_paise": price_paise,
        "stock": stock,
        "status": status,
        "condition": (fields.get("condition") or "New").strip(),
        "description": (fields.get("description") or "").strip() or None,
        "image": image or None,
        "attributes": fields.get("attributes") or {},
        "merchant_id": MERCHANT_ID,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection(PRODUCTS).document(product_id).set(record)

    return {"ok": True, "product": {**record, "updated_at": None}}


def list_products(include_redteam: bool = True) -> list[dict]:
    rows = [d.to_dict() for d in db.collection(PRODUCTS).get()]
    if include_redteam:
        return rows
    return [r for r in rows if not r.get("redteam")]


def get_product(product_id: str) -> dict | None:
    doc = db.collection(PRODUCTS).document(product_id).get()
    return doc.to_dict() if doc.exists else None


def search(query: str = "", max_price_paise: int = 0) -> list[dict]:
    """
    Keyword match, weighted so a product's identity outranks its prose.

    The obvious version of this — "return anything whose text contains any
    query word" — reads fine and behaves badly. Searching "usb-c hub"
    returned the desk lamp, the keyboard and the earbuds too, because every
    one of them mentions USB-C somewhere in its description: the lamp has a
    pass-through port, the earbuds charge over it. Each match was real and
    each result was useless.

    So a word found in the name or category counts for more than the same
    word buried in a description, and when anything matches on identity the
    description-only matches are dropped entirely. With six products the
    whole rule is verifiable by eye, which is the point — a ranking model
    here would be unfalsifiable decoration over a list this short.
    """
    needle = (query or "").strip().lower()
    words = [w for w in needle.split() if len(w) > 1]
    priced = [
        item for item in list_products()
        # Seeded products predate the status field, so a missing status means
        # active — otherwise adding drafts would silently empty the shop.
        if (item.get("status") or "active") == "active"
        # Red-team fixtures carry hostile text designed to hijack a shopping
        # agent. They live in the same collection so the harness exercises the
        # real pipeline, but a person shopping the store must never meet one —
        # so they are excluded here and only the harness opts them in.
        and not item.get("redteam")
        and not (max_price_paise and (item.get("price_paise") or 0) > max_price_paise)
    ]

    if not words:
        return sorted(priced, key=lambda i: i.get("price_paise") or 0)

    strong, weak = [], []
    for item in priced:
        # `or ""` rather than a .get default: these keys exist and hold None
        # for anything saved without a category or description, so a default
        # never fires and the join dies on a NoneType. That took out the whole
        # buyer-facing catalogue the moment a product was added without a
        # description — which the product form allows.
        identity = f"{item.get('name') or ''} {item.get('category') or ''}".lower()
        prose = " ".join([
            item.get("description") or "",
            " ".join(f"{k} {v}" for k, v in (item.get("attributes") or {}).items()),
        ]).lower()

        hits = sum(1 for w in words if w in identity)
        if hits:
            strong.append((hits, item))
        elif any(w in prose for w in words):
            weak.append(item)

    if strong:
        strong.sort(key=lambda pair: (-pair[0], pair[1].get("price_paise") or 0))
        return [item for _, item in strong]

    return sorted(weak, key=lambda i: i.get("price_paise") or 0)


# ── Checkout sessions ────────────────────────────────────────────────────

def create_session(line_items: list[dict], buyer: dict = None) -> dict:
    """
    A UCP-shaped checkout session.

    Stock is checked here, on the merchant's own record, rather than trusted
    from the buyer's request — the buyer names ids and quantities, and the
    merchant decides what those cost and whether they exist.
    """
    resolved = []
    total = 0

    for line in line_items or []:
        product = get_product(str(line.get("id")))
        if not product:
            return {"ok": False, "error": f"No such product: {line.get('id')}"}

        # Hiding drafts from search is not enough on its own — an agent that
        # already knows an id could otherwise check one out directly. The
        # shop refuses to sell what it has not published.
        if (product.get("status") or "active") != "active":
            return {"ok": False, "error": f"{product['name']} is not published for sale."}

        quantity = max(1, int(line.get("quantity") or 1))
        if quantity > (product.get("stock") or 0):
            return {
                "ok": False,
                "error": f"{product['name']}: only {product.get('stock', 0)} in stock, "
                         f"{quantity} requested",
            }

        amount = product["price_paise"] * quantity
        total += amount
        resolved.append({
            "id": product["id"],
            "name": product["name"],
            "quantity": quantity,
            "unit_price_paise": product["price_paise"],
            "amount_paise": amount,
        })

    if not resolved:
        return {"ok": False, "error": "No line items."}

    session_id = f"cs-{uuid.uuid4().hex[:16]}"
    session = {
        "id": session_id,
        "merchant_id": MERCHANT_ID,
        "status": "open",
        "currency": "INR",
        "line_items": resolved,
        "total_paise": total,
        "buyer": buyer or {},
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection(SESSIONS).document(session_id).set(session)

    return {"ok": True, "session": {**session, "created_at": int(time.time())}}


def get_session(session_id: str) -> dict | None:
    doc = db.collection(SESSIONS).document(session_id).get()
    return doc.to_dict() if doc.exists else None


def attach_order(session_id: str, razorpay_order_id: str) -> None:
    db.collection(SESSIONS).document(session_id).update({
        "razorpay_order_id": razorpay_order_id,
        "status": "awaiting_payment",
    })


def mark_paid(session_id: str, payment_id: str) -> None:
    """Confirm payment and decrement the merchant's own stock."""
    ref = db.collection(SESSIONS).document(session_id)
    session = ref.get().to_dict() or {}

    ref.update({
        "status": "paid",
        "razorpay_payment_id": payment_id,
        "paid_at": firestore.SERVER_TIMESTAMP,
    })

    for line in session.get("line_items", []):
        db.collection(PRODUCTS).document(line["id"]).update({
            "stock": firestore.Increment(-int(line.get("quantity") or 1))
        })


# ── Fulfilment ───────────────────────────────────────────────────────────

# Forward only, and only after the money arrived. A shop cannot ship what
# has not been paid for, and un-shipping an order is not a state change —
# it is a return, which is a different record with a refund attached.
FULFILMENT_FLOW = ["paid", "packed", "shipped", "delivered"]

FULFILMENT_LABELS = {
    "packed": "Packed and ready to hand over",
    "shipped": "Handed to the carrier",
    "delivered": "Delivered",
}


def advance_fulfilment(session_id: str, to_state: str, carrier: str = None,
                       tracking_reference: str = None) -> dict:
    """
    Move an order one step along, recording who said so and when.

    Refuses anything that is not the next step. Skipping straight to
    delivered would leave a tracking history that never happened, and the
    whole point of writing these down is that they are a record rather than
    a status field somebody set.
    """
    session = get_session(session_id)
    if not session:
        return {"ok": False, "error": f"No checkout session {session_id}"}

    to_state = (to_state or "").lower()
    if to_state not in FULFILMENT_FLOW[1:]:
        return {"ok": False, "error": f"Not a fulfilment state: {to_state}"}

    current = session.get("fulfilment_state") or (
        "paid" if session.get("status") == "paid" else None
    )
    if current is None:
        return {"ok": False, "error": "This order has not been paid for yet."}

    expected = FULFILMENT_FLOW[FULFILMENT_FLOW.index(current) + 1:
                               FULFILMENT_FLOW.index(current) + 2]
    if to_state not in expected:
        return {
            "ok": False,
            "error": f"Order is {current}; the next step is "
                     f"{expected[0] if expected else 'nothing — it is already delivered'}.",
        }

    if to_state == "shipped" and not (tracking_reference or "").strip():
        # A shipment with no reference is not trackable, and saying "shipped"
        # without one tells the buyer nothing they can act on.
        return {"ok": False, "error": "A shipment needs a tracking reference."}

    history = list(session.get("fulfilment_history") or [])
    entry = {
        "state": to_state,
        "at": int(time.time()),
        "by": MERCHANT_NAME,
        "note": FULFILMENT_LABELS.get(to_state, to_state),
    }
    if to_state == "shipped":
        entry["carrier"] = (carrier or "").strip() or "Not stated"
        entry["tracking_reference"] = tracking_reference.strip()
    history.append(entry)

    update = {"fulfilment_state": to_state, "fulfilment_history": history}
    if to_state == "shipped":
        update["carrier"] = entry["carrier"]
        update["tracking_reference"] = entry["tracking_reference"]

    db.collection(SESSIONS).document(session_id).update(update)
    return {"ok": True, "state": to_state, "history": history}


def fulfilment_for_order(razorpay_order_id: str) -> dict | None:
    """The seller's fulfilment record behind a Razorpay order, if any."""
    rows = db.collection(SESSIONS).where(
        "razorpay_order_id", "==", razorpay_order_id).limit(1).get()
    if not rows:
        return None
    session = rows[0].to_dict() or {}
    if not session.get("fulfilment_history") and session.get("status") != "paid":
        return None
    return {
        "session_id": session.get("id"),
        "state": session.get("fulfilment_state") or "paid",
        "history": session.get("fulfilment_history") or [],
        "carrier": session.get("carrier"),
        "tracking_reference": session.get("tracking_reference"),
        "merchant": MERCHANT_NAME,
    }


# ── The agent-readable view ──────────────────────────────────────────────
#
# A price and a name are enough for a person looking at a page and nowhere
# near enough for an agent deciding on someone's behalf. "Running shoes under
# ₹3,000, black, size 9, delivered within 3 days" is four constraints, and a
# catalogue that publishes only name and price forces the agent to guess at
# three of them — or to fetch the product page and read prose, which is
# scraping with extra steps.
#
# So the store publishes what it can actually assert about its own goods.
# The split below is the important part:
#
#   OBSERVED    stock, price, status — facts in the merchant's own records
#   DECLARED    delivery window, returns window, whether agents may check out
#
# Declared is not weaker, it is different: a shop's returns policy is a
# promise it is making, not a measurement it took. Every declared field
# carries `declared_by` so an agent reading this knows it is holding the
# merchant to a statement rather than to an observation. A field the store
# has no basis for is omitted rather than defaulted — an invented delivery
# estimate is the one lie a buying agent would act on immediately.

# The store's own standing terms. Merchant-level rather than per-product
# because that is how this shop actually operates: one fulfilment process,
# one returns window. A product may override either.
STORE_TERMS = {
    "delivery": {
        "estimated_days": 3,
        "ships_to": ["IN"],
        "declared_by": "merchant",
        "note": ("The merchant's standing fulfilment window. Not a carrier "
                 "quote and not tracked against actual deliveries."),
    },
    "returns": {
        "days": 7,
        "declared_by": "merchant",
        "note": "The merchant's standing returns window.",
    },
}


def agent_view(product: dict) -> dict:
    """
    One product as a buying agent needs to read it.

    Everything here is either in the record or in the store's declared
    terms. Nothing is estimated, and the `purchase` block describes the
    gate this project actually applies rather than a capability claim.
    """
    price_paise = int(product.get("price_paise") or 0)
    stock = int(product.get("stock") or 0)
    status = (product.get("status") or "active").lower()

    view = {
        "product_id": product.get("id"),
        "name": product.get("name"),
        "category": product.get("category"),
        "price_paise": price_paise,
        "price": round(price_paise / 100, 2),
        "currency": "INR",
        # Two separate facts that are easy to conflate: a draft product is in
        # stock and still not for sale.
        "availability": status == "active" and stock > 0,
        "inventory": stock,
        "status": status,
        "condition": product.get("condition"),
        "description": product.get("description"),
        "attributes": product.get("attributes") or {},
        "delivery": dict(STORE_TERMS["delivery"]),
        "return_policy": dict(STORE_TERMS["returns"]),
        "purchase": {
            "supports_agent_checkout": True,
            "protocols": ["ucp", "acp"],
            # The single most important field for an agent to read before it
            # commits to anything: this store will take an agent's order and
            # a person still has to clear it above the bound.
            "requires_user_approval": "above the buyer's own spending bound",
            "approval_note": (
                "This store accepts agent checkout. Whether a person must "
                "approve is decided by the BUYER's policy, not this "
                "merchant's — see GET /transaction-policy on the buying "
                "agent. The merchant does not get to lower somebody else's "
                "spending limit."
            ),
            "payment_handlers": ["razorpay"],
            "delegated_payment_tokens": False,
        },
        "merchant": {"id": MERCHANT_ID, "name": MERCHANT_NAME},
    }

    # Said out loud, because an agent choosing between listings on a photo
    # would otherwise be comparing a photograph against a drawing.
    if product.get("image_kind") == "generated_illustration":
        view["image_kind"] = "generated_illustration"
        view["image_note"] = ("A generated illustration, not a product "
                              "photograph. This store has no product "
                              "photography.")
    return view

def live_offer(product_id: str) -> dict | None:
    """
    The growth offer standing against this product, if one was approved.

    THIS IS THE STEP THAT CLOSES THE LOOP.

    Before this, a merchant could approve a cross-sell and the buyer would
    never see it: the offer went into `growth_offers` and no customer-facing
    surface read that collection. The whole chain — agent proposes, gate
    rules, merchant approves — ended in a database row nobody acted on.

    Resolved rather than raw: the offer stores a complement id, and an agent
    or a screen that has to make a second call to find out what that id is
    will sometimes not bother. The complement's real name, price and stock
    travel with it, read from the catalogue at the moment of asking so a
    sold-out complement cannot be recommended.
    """
    try:
        from app.growth import registry
    except Exception:
        return None
    for offer in registry.offers_for(product_id):
        params = offer.get("params") or {}
        complement_id = params.get("complement_id")
        if not complement_id:
            continue
        complement = get_product(complement_id)
        # A draft or an out-of-stock complement is not a recommendation, it
        # is a dead end with a price on it.
        if not complement or (complement.get("status") or "active") != "active":
            continue
        if int(complement.get("stock") or 0) <= 0:
            continue
        return {
            "offer_id": offer.get("offer_id"),
            "agent": offer.get("agent"),
            "kind": offer.get("kind"),
            "basis": params.get("basis"),
            "approved_by": offer.get("approved_by"),
            "product": {
                "id": complement["id"],
                "name": complement["name"],
                "price_paise": complement["price_paise"],
                "image": complement.get("image"),
                "stock": complement.get("stock"),
            },
            # The sentence a buyer sees, and it must not overstate the basis.
            # "Frequently bought together" on a pair nobody has ever bought
            # together is the exact lie the relationship graph exists to
            # prevent, so the wording changes with the evidence.
            "message": (
                f"Customers buying this also bought {complement['name']} "
                f"(₹{complement['price_paise'] / 100:,.0f})."
                if params.get("basis") == "co_purchase" else
                f"{complement['name']} (₹{complement['price_paise'] / 100:,.0f}) "
                f"is filed alongside this one. Nobody has bought the two "
                f"together yet — this is the shop's suggestion, not a pattern."
            ),
            "disclosure": ("Shown because the merchant approved a cross-sell "
                           "for this product. It changes no price."),
        }
    return None
