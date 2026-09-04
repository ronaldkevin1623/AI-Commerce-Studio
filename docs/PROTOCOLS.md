# Agent protocols: what is implemented, and what is not

Five protocols get mentioned around agentic commerce. This project's honest
position on each, in one place, so nobody has to infer it from a demo.

| Protocol | Status here |
|---|---|
| **UCP** — Universal Commerce Protocol | **Implemented.** Discovery, catalogue, checkout, settlement. |
| **AP2** — Agent Payments Protocol | **Implemented.** ES256 mandate chain, verified before money moves. |
| **ACP** — Agentic Commerce Protocol | **Implemented** for agentic checkout, against the published `spec/2026-04-17`. Delegated payment tokens are **not** supported and the capability says so. |
| **x402** | **Shape implemented, settled over Razorpay.** Not onchain, will not interoperate with USDC facilitators. |
| **NPCI UAP** — Unified Agent Protocol | **Not implemented. No published specification exists.** See below. |

---

## NPCI UAP — why there is nothing to implement yet

NPCI's Unified Agent Protocol is being **unveiled at Global Fintech Fest,
9–11 September 2026**, and requires RBI approval before launch. As this was
written there is no public specification, no endpoint list and no schema.

There is also no rail: **UPI is disabled on this project's Razorpay test
account**, so even the settlement leg could not be exercised.

Anything shipped here labelled "NPCI UAP" would therefore be an invented
protocol attributed to NPCI. That is a worse outcome than the gap, so it has
not been done.

### What UAP is *described* as doing, and where this project already does it

Reporting consistently describes UAP as building on **UPI Circle
delegation**: a user decides in advance *when* an agent may pay, *how much*
it may spend, and *what kind* of purchase it may make. That idea is not new
to UAP, and this project already enforces it — twice, at different layers.

| What UAP is described as providing | Where this project does it today | Evidence |
|---|---|---|
| A user delegates payment authority to an agent | **AP2 intent mandate**, signed ES256 and issued per request | `app/agent/mandates.py:156` |
| …within a pre-set spending limit | `checkout.max_amount_paise` bound into the mandate | measured: `{"checkout.max_amount_paise": 200000, …}` |
| …for a defined kind of purchase | `checkout.category` and `checkout.allowed_marketplaces` in the same constraints | same object |
| …that expires rather than standing forever | mandate `exp` — **1,800 seconds** from issue | measured on a live mandate |
| …and is verified before money moves | `verify_chain(intent, cart, product)` returns `ok` before any charge | `mandates.py:284` |
| Standing authority for low-value, frequent purchases | **Autonomy caps**: `max_order_inr 1500`, `monthly_cap_inr 5000`, `min_confidence_pct 60` | `GET /agent-settings` |
| A user-set rule on when the agent may act unattended | six autonomy gates behind a kill switch, default **off** | `kill_switch, per_order_cap, monthly_cap, category, confidence, already_bought` |

**The claim this supports, and its exact wording:**

> "UAP's published description is delegated payment authority within a
> pre-set limit. That is what the AP2 mandate chain and the autonomy caps
> already enforce here — a signed, expiring grant with an amount ceiling, a
> category, and a verification step before anything is charged. When the
> specification lands, this is what it maps onto."

**The claim this does NOT support:**

> ~~"We support NPCI UAP."~~ There is nothing to support yet.
> ~~"UPI agentic payments work here."~~ UPI is disabled on this account.

---

## ACP — implemented against the real spec

Endpoints from the published OpenAPI (`spec/2026-04-17/openapi/openapi.agentic_checkout.yaml`):

```
POST /acp/checkout_sessions
POST /acp/checkout_sessions/{id}
GET  /acp/checkout_sessions/{id}
POST /acp/checkout_sessions/{id}/complete
POST /acp/checkout_sessions/{id}/cancel
```

Headers, `CheckoutSession` shape, status vocabulary, typed `totals` and
`messages` all follow the spec. Verified end to end:

```
no Authorization        -> 401 unauthorized
empty cart              -> 400 invalid_request
draft product           -> 409 "not published for sale"
create                  -> not_ready_for_payment, ₹1,490
replay Idempotency-Key  -> the SAME session, not a second one
ACP delegated token     -> 422 unsupported_payment_handler
forged payment id       -> 402 payment_not_verified
cancel                  -> canceled
```

**The architectural point:** ACP runs on the same `store.create_session` and
the same settle path as UCP. The draft refusal, the stock check and "the
merchant prices its own goods" are enforced once, for both protocols. Adding
the second protocol required no change to the store — which is the test of
whether the first one had leaked into it.

**Not supported, declared rather than discovered:** `delegated_payment_tokens:
false` on every session. A spec-compliant agent sending a vault token gets a
422 naming what this build does support.

---

## x402 — the shape, over an INR rail

```
GET  /x402/insights                -> 402 + PAYMENT-REQUIRED (base64 JSON)
POST /x402/authorize               -> a Razorpay order to settle it
GET  + PAYMENT-SIGNATURE           -> 200 + PAYMENT-RESPONSE + the resource
```

Canonical x402 settles **onchain in USDC** through a facilitator. There is no
crypto rail here. The scheme is declared `razorpay` on network
`razorpay-test` **deliberately**, so a real x402 client reads it, finds a
scheme it cannot use, and correctly declines rather than being misled.

The normative specification could not be fetched while this was built; field
names follow secondary documentation and may differ in detail from the
current spec.

---

## The agent-readable catalogue

A protocol gets an agent to the door. What it finds inside decides whether
it can act. `GET /merchant/catalog` and `GET /merchant/catalog/{id}` publish
each product in the shape a buying agent actually has to reason over:

```
availability      active AND in stock — two facts, deliberately not merged
inventory         the count, so an agent can size an order
attributes        the merchant's own structured fields
delivery          estimated_days, ships_to        declared_by: merchant
return_policy     days                            declared_by: merchant
purchase          supports_agent_checkout, protocols, payment_handlers,
                  delegated_payment_tokens: false
complements       what the store has OBSERVED going with this product,
                  each carrying its basis
```

Two rules hold this together.

**Observed and declared are marked apart.** Stock and price are facts in the
merchant's records. A returns window is a promise the merchant is making.
Both are legitimate to publish and they are not the same kind of statement,
so every declared field carries `declared_by` and an agent knows which it is
holding the shop to.

**A field with no basis is omitted, never defaulted.** An invented delivery
estimate is the one lie a buying agent would act on immediately.

`requires_user_approval` is the field worth reading twice. It answers "above
the buyer's own spending bound" rather than yes or no, because a merchant
does not get to decide when somebody else's agent needs a person — that is
the buyer's `GET /transaction-policy`, and it is the buyer's gate that
enforces it.

A draft product 404s here, exactly as it 409s in UCP and ACP checkout. One
rule, three surfaces.

---

## The pattern

Three of these are implemented against published specifications. One is
implemented in shape over a different rail, and says so in its own payload.
One is not implemented because it does not exist yet.

Each limit is declared in the thing itself — a capability flag, a scheme
name, an error code — rather than left in a document nobody reads during a
demo. That is the same rule the rest of this project follows: the failure a
system will not admit to is the one that costs somebody money.
