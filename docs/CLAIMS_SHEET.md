# Claims sheet

Every number you might say out loud, with how it was checked. Measured
2026-09-03 against the running build, on the local emulator unless stated.

**Rule of thumb:** if a number is not on this sheet, do not say it.

---

## Safe to say — measured today

| Claim | Value | How it was checked |
|---|---|---|
| Trip datasets | **300,153 flights · 580 hotels · 31,297 restaurants** | loaded and counted, 4.4s |
| Itinerary assembly time | **~50ms** | `took_ms` on `POST /trip/plan` |
| Delhi→Mumbai, 2 nights, ₹20,000 cap | **₹13,007 across 5 legs** | assembler output |
| The stay it picks | **City Stay, Andheri East, 4.6★ from 214 reviews** | assembler output |
| Stay price | **(₹1,229 + ₹370 tax) × 2 = ₹3,198** | re-derived from the dataset row |
| What the flight step considered | **40 fares** | step trace on screen |
| What the hotel step considered | **40 under the nightly cap** | step trace |
| What the meal step considered | **120, placed 3 of 4** | step trace |
| Sectors registered | **2 — `/products`, `/trip`** | `GET /sectors` |
| Growth agents | **5 — cart recovery, cross-sell, discount test, reactivation, bundles** | `GET /growth/agents`; campaigns orchestrate them rather than being one |
| Of those, agents that spend margin | **4 — recovery, discount test, reactivation, bundles** | asserted by roster, not by count, in `audit_24_growth` |
| Merchant-side bounds | **5 — kill switch, per-action cap, daily cap, discount ceiling, evidence floor** | `app/growth/gate.py`, all five exercised in `audit_24_growth` |
| Hive | **23 of 25 specialists live, 9 tunable** | the Hive page header |
| Test suite | **617 assertions passed, 2 failed, 25 suites** | `tests/run_all.py` |
| Merchant catalogue | **8 products; operator sees 8, buying agent sees 7** | `/merchant/products` vs `/merchant/catalog` |
| Recommendation row | **12 cards, 7 of them the store's own products** | `GET /recommendations`; store items reach it now they carry an image |
| Autonomy gates | **6** | `kill_switch, per_order_cap, monthly_cap, category, confidence, already_bought` |
| Payment rail | **netbanking only** | all 9 Razorpay payments are netbanking; cards and UPI disabled on this account |
| Real money moved | **9 payments — 8 captured, 1 refunded, ₹107,363.76 total** | Razorpay API, `payment.all` |
| The refunded order | **₹319.55, fully refunded** | `pay_TVHMFZKgIyImkW`, verified at Razorpay |

## The payable-leg chain — the strongest claim you have

All four links verified by execution:

```
itinerary chose   hotel:mumbai:21  (City Stay)
asserted price    (₹1,229 + ₹370) × 2 = ₹3,198   ← re-read server-side, never sent by the browser
razorpay order    order_TX7qxzJj9XnASw, amount ₹3,198
razorpay notes    hotel_record_id = hotel:mumbai:21   ← read back FROM Razorpay
re-derived from the dataset row alone: ₹3,198 — matches
```

Say: *"the link survives outside our database."* That is literally true — the
record id is in Razorpay's own order notes.

Also verified: booking a **different** hotel against the same request returns
**409** and refuses.

## Architecture claims that are true and checkable

| Claim | Evidence |
|---|---|
| Trip adapters cannot leak into product search | global venue registry is `['ebay','merchant','sponsored']` **before and after** importing the trip sector; trip's own are `['trip-flights','trip-hotels','trip-restaurants']` |
| The `/` menu is not hardcoded | it renders from `GET /sectors`, which reads the registry |
| Products path is unchanged by the sector work | full suite run before and after: identical result |
| Free-text routing asks when unsure | `"something nice"` → no sector, asks. Scores returned for every sector, not just the winner |
| Sponsored placement cannot buy rank | promotion buys candidacy and a labelled complement slot only — `audit_21_sponsored`, 51 assertions |

## Say with the caveat attached

| Claim | Required caveat |
|---|---|
| "It books a trip" | **It does not.** One hotel leg is a real Razorpay capture through a demo-merchant stand-in. No room is held, no hotel is contacted. Production needs direct supplier integration. |
| "Real prices" | Real *values from a supplied dataset snapshot*. No live availability, no live pricing, departure is a window ("Evening") not a time. |
| "It covers India" | **Six metros** — Bangalore, Chennai, Delhi, Hyderabad, Kolkata, Mumbai. That is what the data has. |
| "All tests pass" | 597 pass, **2 fail**. See below — the failure is a feature. |
| "Recommendations are personalised" | From *your own* orders and searches in this datastore. On the emulator that is the demo history, not a stranger's. |

## The merchant side — new, and the strongest answer to "grows revenue"

| Claim | Evidence |
|---|---|
| A discount is gated like a purchase | `growth/gate.py` mirrors `risk_gate`. Same shape, opposite pocket. |
| The gate refuses thin evidence | 1 abandoned cart is below the floor of 3, so a ₹51.92 offer **escalates** rather than applying |
| An agent cannot clear its own proposal | `POST /growth/apply` without `approved_by` returns **409** |
| Cross-sell says which basis it used | "bought together twice" vs "both filed under cables" — labelled per row |
| The discount test refuses to rank noise | "NOT A RESULT YET. 8%, 5% have fewer than 5 outcomes" |
| A campaign can end | four ways: budget spent, window closed, paused, **or the remaining envelope is too small to buy anything** |
| No uplift is claimed | measurement reports counts and sample size; "no control group exists here" |

**Say:** *"The same bar the buying agent passes, the selling agent passes too."*

## The closing half of the loop — attribution

| Claim | Value | How it was checked |
|---|---|---|
| Revenue attributed to growth agents | **whatever `GET /growth/attribution` says today** | counted from orders an applied action is attached to, never "orders after a campaign started" |
| Margin given away | **reported beside it, at the same size** | `margin_spent_paise` in the same payload |
| Conversion rate claimed | **none, at any sample size** | asserted: no `%` appears in the headline or the caveat |

**The sentence that makes this a strength rather than a weakness:**

> "Attribution is the easiest place in a commerce system to lie, because the
> lie is arithmetic rather than invention — count every order after the
> campaign started and you get a large number that would have been almost
> identical with no agent running. This counts only orders an action is
> attached to: the offer went on that cart, and that cart paid."

**Say with the caveat, always:** attributed is not incremental. Some of
those customers would have paid anyway, and separating them needs a holdout
group this build has no traffic for. The payload says so itself.

## The product relationship graph

| Claim | Value | How it was checked |
|---|---|---|
| Edges learned from real orders | **0 today** | `GET /growth/graph` — no two products have yet been bought together |
| Edges from category adjacency | **2** | same call |
| Order records read | **37** | buyer-side `orders` plus `merchant_checkouts` |

**Do NOT say** the graph shows what customers buy together — today it shows
that nothing has been bought together yet, and draws the assumptions
differently for exactly that reason. That refusal is the claim worth making:

> "An assumed edge carries `support: 0`. Not 1 — nothing was observed, and
> writing 1 there would make an assumption indistinguishable from a sale."

## The agent-readable catalogue and the transaction policy

| Claim | Value | How it was checked |
|---|---|---|
| Catalogue fields an agent can act on | **availability, inventory, attributes, delivery, return_policy, purchase, complements** | `GET /merchant/catalog/{id}` |
| Merchant-declared fields | **delivery and returns**, each carrying `declared_by: merchant` | same payload |
| Draft product on the agent catalogue | **404** | verified; matches the 409 UCP and ACP already give |
| Bounds in the transaction policy | **5, each naming the module that enforces it** | `GET /transaction-policy` |
| Behaviours declared | **5**, including `auto_retry_payment: false` | asserted in `audit_24_growth` |
| Policy tracks the live setting | **yes** | asserted: changing the limit changes the document |

**The line for `auto_retry_payment: false`:**

> "That is in the policy because no code path in this project retries a
> charge — not because a flag is switched off. A failed payment's next
> attempt is a fresh action, gated and logged from scratch."

**Do NOT say** the checkout's green tick means the purchase will go through.
It is one of the gate's six checks, and the screen names the five it did not
run.

## Protocols — the one-line answer for each

| Asked about | Say |
|---|---|
| **UCP** | Implemented — discovery, catalogue, checkout, settlement. |
| **AP2** | Implemented — ES256 mandate chain, `verify_chain` before money moves, 1,800-second expiry. |
| **ACP** | Implemented for agentic checkout against the published `spec/2026-04-17`. Delegated payment tokens are not supported and the session says so. |
| **x402** | The shape, settled over Razorpay. Not onchain. Will not interoperate with USDC facilitators. |
| **NPCI UAP** | **Not implemented — no published spec exists.** It is unveiled 9–11 Sept 2026 and needs RBI approval. UPI is also disabled on this Razorpay account. |

On UAP, the honest and defensible line:

> "UAP's published description is delegated payment authority within a
> pre-set limit. That is what the AP2 mandate chain and the autonomy caps
> already enforce — a signed, expiring grant with an amount ceiling, a
> category, and verification before anything is charged. When the spec
> lands, this maps onto it."

Never say "we support UAP". Full detail in `docs/PROTOCOLS.md`.

## x402 — say this precisely or not at all

Implemented: the x402 **request/response shape** — `402` + `PAYMENT-REQUIRED`
(base64 JSON, `x402Version` + `accepts`), retry with `PAYMENT-SIGNATURE`,
`PAYMENT-RESPONSE` on settlement. Verified: no payment → 402; forged proof →
refused against the Razorpay API; malformed header → 400.

**Not implemented, and do not imply otherwise:** canonical x402 settles
onchain in USDC through a facilitator. There is no crypto rail here. The
scheme is declared `razorpay` on network `razorpay-test` **on purpose**, so a
real x402 client reads it, finds a scheme it cannot use, and correctly
declines rather than being misled.

If asked: *"It speaks the x402 contract over an INR rail. It will not
interoperate with USDC facilitators, and it says so in the payload."*

Also note: the normative spec could not be fetched while this was built, so
the field names follow secondary documentation and may differ in detail.

## The 2 failing assertions — how to talk about them

They are the money reconciliation, and they are **currently failing on purpose-ish**:

```
[FAIL] Every rupee reported as captured is confirmed by Razorpay
       dashboard ₹829.17 vs Razorpay ₹107,044.21
[FAIL] No payment moved money without this app recording the order
       pay_TX8LiKwOLpTxNh ₹12,367.00; pay_TW2fdpNWnRIwA4 ₹87,057.87; ...
```

**What is actually true:** Razorpay is real in every configuration, but the
app's records live in whichever datastore it was started with. Running on the
local emulator, the emulator holds a handful of orders while the Razorpay
account holds every payment ever made in test mode. The check compares the two
and correctly reports the gap.

**The strong version to say out loud:**

> "This check compares what the app claims it captured against what Razorpay
> actually holds. Right now it fails, because I am running on a local
> datastore and the payment provider is the real one. I have left it failing
> rather than special-casing it — a reconciliation you can silence is not a
> reconciliation."

Do **not** say "there is a bug in payments". There is not. No money is
unaccounted for; the records are in a different store, and there is an
exported snapshot of it.

## Numbers NOT to quote

- **Any latency other than the ~50ms trip assembly and ~18s product search.**
  Everything else varies with eBay.
- **"14 pipeline stages" / "15 routes."** 21 routers are registered; I have not
  re-counted stages today. Say "the trace shows every stage" and open it.
- **Anything about production readiness, throughput, or concurrency.** Never
  measured.
- **Any claim that the emulator data is the same as real Firestore.** It is not.

## Known gaps — if asked, say these plainly

- **No product photography** for the demo store's own catalogue. Each product
  carries a generated flat **illustration** instead — a category glyph, the
  product name, and the words "ILLUSTRATION · NOT A PRODUCT PHOTO" on the tile
  itself. Stamped `image_kind: generated_illustration` in the record. A stock
  photo of a similar-looking cable was rejected: that is a picture of someone
  else's product presented as this store's inventory. eBay items have real
  photographs, and the two are visually distinguishable on sight.
  **If asked:** *"The store has no photography, so it shows an illustration
  that says it is one."*
- **One orphaned record.** A ₹829.17 netbanking payment on 2 Sep was recorded
  into the emulator because that is where the app pointed at the time. It is
  exported and traceable; a reviewable backfill script exists and has not been
  run.
- **Flights and restaurants are not payable at all.** `can_fulfil = False` on
  all three trip adapters. Only the hotel leg has a rail, and it is a stand-in.
- **Six metros only.**
- **Cards and UPI do not work** on this Razorpay test account. Netbanking is
  the only rail that completes, and it needs a human at the bank page.
