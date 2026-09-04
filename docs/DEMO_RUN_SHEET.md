# 5-minute run sheet

Every beat below was executed against the running build on 2026-09-03.
Timings are measured, not estimated.

There is more built than fits in five minutes. The order here is chosen so
that **if you run out of time, the things you drop are the ones you can
afford to drop** — cut from the bottom of each section, never the top.

---

## Before you start

```
start-emulator.cmd
```

Then the backend and frontend. Nothing else to set — the local emulator is
the default. Check `http://localhost:8010/health` says
`{"status":"ok","datastore":"emulator:127.0.0.1:8085"}`.

**Pick a side on the landing page.** Two dashboards sit behind a
**Customer / Merchant** toggle in the top bar. Do the buying beats as
Customer, then switch. The toggle moves you to that side's home rather than
holding your place — there is no merchant equivalent of `/trips`.

**Have ready:** a netbanking test login. Cards and UPI are disabled on this
Razorpay account; netbanking is the only rail that completes and needs you
at the bank page (~40s). If you would rather not risk it live, the captures
that already exist prove the same point.

**Reset between rehearsals:** Ctrl+C the emulator window — *not* the X, or
the save is skipped — then `start-emulator.cmd` again.

**State it starts in:** growth agents **off**, 4 proposals waiting, 1
campaign, 1 abandoned checkout, 1 approval pending, 8 products, 0 live
offers, an empty recovery queue.

---

## 0:00 — 0:25 · The problem

> "An agent that can spend money is only useful if you can say exactly what
> stops it. This is a commerce agent where every bound is enforced in code —
> on both sides of the counter."

Land two ideas: **it transacts for real**, and **it can refuse**.

## 0:25 — 1:10 · Buying, and standing down

As **Customer**, type with no slash:

```
wireless earbuds under 2000
```

**~18s.** Live eBay: *"found 23, set aside 2 that were accessories or a
different product, though Trust flagged 2 as suspect."* The set-aside count
is the point — a funnel, not a filter.

Then:

```
under 500
```

Amber notice: *"Nothing in these results is under ₹500. The cheapest of them
is ₹539. These are still the previous results, unfiltered."* An agent that
quietly widens your budget is the failure everyone expects.

*Cut if short:* the second query.

## 1:10 — 2:10 · `/trip` — the architectural argument

Type `/` and pause on the menu: sectors, from the plug-in registry, not a
hardcoded list. Then just:

```
/trip
```

**The agent changes** — heading, empty box, placeholder *"Where are you
going?"* pulled from the sector's own intent schema, a **Planning a trip**
chip, and the product recommendations disappear. No template menu: you
already know where you are going.

Now talk to it normally:

```
I am planning to go Kolkata for 3 days within 5000
```

> *"Got a trip to Kolkata, 2 nights, under ₹5,000. Flying from?"*

```
Delhi
```

**~50ms.** A full itinerary at **₹4,548**, inside the budget. **It is a
conversation, not a form.**

**The line that matters:**

> "Products ranking picks the best row from a list. A trip is not a row. The
> hotel must be in the city the flight lands in, the meals near the hotel
> that won, and the budget applies to the sum. Those are dependencies
> between choices, and a ranker cannot express one."

**Then the refusal — one of the best 15 seconds you have:**

```
3 days 2 nights Chennai to Chikmagalur under 10000
```

> *"Chikmagalur is not in the supplied datasets… Coverage is Bangalore,
> Chennai, Delhi, Hyderabad, Kolkata, Mumbai — six metros, because that is
> what the data has, not a product decision."*

Say: **"It knows what it does not know."**

*Cut if short:* the refinement turns (`make it 4 nights`, `raise the budget
to 20000`).

## 2:10 — 2:50 · The payable leg

Point at the button, read the label out loud:

> "Real payment captured for a demo-merchant stand-in. This is not a
> booking: no room is held and no hotel is contacted."

Then the part people miss:

> "The browser sends one thing — the hotel's record id. No price. The server
> re-reads that dataset row, re-runs the itinerary, and refuses if this is
> not the hotel that won."

If you have a terminal open:

```bash
cd Cart-Pilot/backend && ./venv/Scripts/python.exe tools_show_last_trip_order.py
```

Reads the order back **from Razorpay** and re-derives the amount from the
dataset alone:

```
  hotel_record_id  hotel:kolkata:29
  Re-derived from the dataset row alone: Rs1,868.00
  Matches what Razorpay holds          : True
```

*Cut if short:* the terminal command; the label on the card makes the point.

## 2:50 — 3:50 · The merchant side — the same bar, opposite pocket

Switch the toggle to **Merchant**. **Home changes agent.**

> "Both sides of this get an agent. The buyer's turns a sentence into a
> transaction. The merchant's turns a sentence into an analysis of their own
> shop. Same app, opposite ends of the counter."

The heading now reads **"Welcome back — what should I look into?"**. Click
the first chip, or type it:

```
Find me an opportunity to increase revenue
```

**The answer is the beat.** It opens with what it ran — *"I ran 4 proposals
from five growth agents against this store's own orders"* — then leads with a
refusal rather than an opportunity:

> *"No two products have ever been bought together here. Across 39 order
> records, not one contains two of this store's products. That rules out the
> obvious revenue play — a cross-sell learned from real baskets — because
> there are no real baskets to learn from."*

then finds the cheaper win anyway:

> *"Orders are being created and not paid. 5 of 8 orders in this window were
> never paid. Recovering an order that already exists is cheaper than
> creating a new one."*

then lists **what it would do** — each action priced, tagged with its agent
and its observation count, and carrying the gate's own verdict — and closes
with a block headed **What I could not determine**:

> *"No expected-return figure is attached to any of these. This shop has no
> conversion history to project from, so a number like 'expected +₹42,000'
> would be arithmetic on an assumption."*

**The sentence to say:**

> "Every number in that answer is computed. Nothing is phrased by a language
> model — deliberately. Ask an LLM to summarise a growth report and it will
> tell you 'customers who buy X have a 38% chance of buying Y' whether or not
> anything supports it, because that is what the training data looks like. On
> this shop that number would be invented, and it would be the most
> persuasive thing on the screen."

*Also worth one line if asked:* it answers six kinds of question — revenue,
performance, problems, products, customers, and what it can do unattended —
and says so plainly when it does not understand rather than improvising.

Then **Growth** in the sidebar. It is a **section**, not a page: it opens to
**Agents · Campaigns · Attribution · Relationships**, and the Overview
carries three cards with one number each, so you can see what is waiting
before opening anything. Go to **Agents**.

Everything reads **Blocked — growth agents are switched off**. Flip the
switch and re-scan. Now:

```
8% off Braided USB-C Cable — costs ₹51.92 of margin — 1 observation
    Needs you
    Gate: Only 1 observation(s) behind this, below the 3 needed to act on
    it unattended… so a person decides.

Show "Bamboo Monitor Stand" alongside "Warm LED Desk Lamp"
    Within bounds — costs nothing
```

**The sentence to say:**

> "`risk_gate` stops the buying agent overspending the shopper's money. This
> stops the growth agents giving away the merchant's. A discount is a money
> action even though nothing is charged — so it gets a cap, a budget, an
> audit entry, and it cannot approve itself."

Two details worth pointing at:

- **the evidence floor** — one abandoned cart is a case, not a trend, and
  the agent says so rather than spending margin on it
- **cross-sell labels its basis** — *"both filed under home office — no
  order has contained them together"*. Adjacency is not evidence.

**Five agents are registered, not three.** Further down the queue is
**reactivation** — *"10% off the next order for a customer silent 1.5 days"*
— and, when the data supports one, **bundles**. Both spend margin, so both
land on the same gate.

The reactivation one is worth reading aloud, because it argues against
itself: *"Their orders sit about 0.0 hours apart, which is too close
together to read as a rhythm — so the 24-hour floor decided this, not their
own pattern. Weaker evidence than it looks."*

> "Lapsed is not a fixed 90 days. It is computed against that customer's own
> median gap between orders, because a fixed rule on a shop this young finds
> nobody. And a customer with one order is counted separately and never
> proposed against — one purchase is not a rhythm that can be broken."

Then **Attribution** and **Relationships** in the sidebar, which are the
closing half of the loop:

**Attribution.** Margin given away sits beside revenue earned, at the same
size.

> "Every dashboard like this shows the revenue large and the cost in a
> footnote, and the number reads as profit. This counts only orders an
> action is actually attached to — the offer went on *that* cart and *that*
> cart paid — and it prints no conversion rate at any sample size."

**Relationships.** The graph the cross-sell and bundle agents reason over,
drawn so the basis can be checked rather than trusted.

> "Solid green means bought in the same order. Dashed grey means only filed
> under the same category. Right now every edge on this store is dashed, and
> the graph says so itself rather than letting you assume otherwise."

*Cut if short:* Relationships; Attribution carries the argument.

## The closed loop — if you have 45 seconds spare

The one beat that shows both agents in the same sentence. On **Agents**,
flip the switch on and click **Approve and apply** on a cross-sell.

Then switch to **Customer**, open the anchor product from the
recommendation row, and scroll the drawer:

```
FROM THE MERCHANT
    Bamboo Monitor Stand with drawer          ₹1,290    [ Add ]

    Bamboo Monitor Stand with drawer (₹1,290) is filed alongside this
    one. Nobody has bought the two together yet — this is the shop's
    suggestion, not a pattern.

    Shown because the merchant approved a cross-sell for this product.
    It changes no price. Offer go-…, approved by merchant.
```

> "That is the merchant's agent and the buyer's agent meeting. The merchant
> approved it thirty seconds ago and it is on the buyer's screen now,
> carrying the offer id so the audit trail can be read back to the approval."

**The line that matters most is the second paragraph.** A retail cross-sell
would say *"frequently bought together"* here. Nobody has bought these two
together, so it says that instead — the wording is chosen by the server
from the evidence, not by the component.

And when one converts, **only the recommended line is counted**: a shopper
who was buying a ₹1,490 lamp anyway and added a ₹1,290 stand generated
₹1,290 of agent revenue, not ₹2,780. Counting the basket is how every
cross-sell ends up looking transformative.


Click **Approve and apply** on the escalated one → *"Applied — offer go-…"*.

Then scroll to **Campaigns**: a goal, an envelope, a window. **Tick.**

> "The envelope sits inside the gate rather than replacing it, so whichever
> binds first wins. And it can end four ways — budget spent, window closed,
> paused, or the remaining envelope is too small to buy anything. An
> orchestrator that cannot stop itself is a scheduler with a marketing name."

*Cut if short:* the campaign; the queue alone carries the argument.

## 3:50 — 4:25 · Protocols

**Storefront** → the one-line seller beat:

> "The operator sees 8 products including a draft. The buying agent sees 7 —
> drafts are invisible to it. Same database, two views, enforced server-side."

Then, without leaving the page:

> "The store speaks **UCP** and **ACP** over the same catalogue and the same
> stock rules. Adding the second protocol required no change to the store —
> which is the test of whether the first one had leaked into it. A draft
> product is refused with a 409 either way."

Then open `/merchant/catalog/cds-desk-lamp` in a tab if there is time:

> "A price and a name are enough for a person looking at a page and nowhere
> near enough for an agent buying on someone's behalf. Availability and
> inventory are separate fields, delivery and returns are marked
> `declared_by: merchant` because a returns window is a promise rather than
> a measurement, and `requires_user_approval` answers *'above the buyer's
> own spending bound'* — because a shop does not get to decide when somebody
> else's agent needs a person."

And `/transaction-policy` beside it:

> "Every bound the buying agent is under, in one document, read live from
> the same settings the gate reads — and each line names the module that
> enforces it. `auto_retry_payment: false` is in there because no code path
> retries a charge, not because a flag is switched off."

If asked about the rest — the answers are in `docs/PROTOCOLS.md`:

- **AP2** — implemented, ES256 mandate chain, 1,800-second expiry
- **x402** — the shape, settled over Razorpay, **not onchain**
- **NPCI UAP** — **not implemented, no published spec exists.** Unveiled
  9–11 Sept 2026, needs RBI approval. Say what the mandate chain and caps
  already enforce instead.

*Cut if short:* everything after the Storefront line.

## 4:25 — 5:00 · Why you can believe any of it

### The failure — real, not simulated

The brief asks for one failure handled gracefully, and this account provides
one on request: **cards are rejected here, every time.** So buy anything and
pay by **card**. Razorpay refuses it for real.

Then open **Failure recovery**. The item is waiting there:

```
⚠ Payment could not be completed                      BAD_REQUEST_ERROR

 [img]  Braided USB-C Cable, 2 metre
        ₹649   order_demo_card

 Your payment could not be completed as this business accepts domestic
 (Indian) card payments only. Try another payment method. Netbanking is
 the only rail with a capture behind it here. (failed at: payment_authentication)

     A failed payment is never retried automatically…
     Enforced by: absence — no retry exists to disable

 [ Try again ]  [ Change payment method ]  [ Cancel ]
```

**The three sentences to say:**

> "A card rejected inside Razorpay's own modal never reaches the success
> handler, so the most common failure on this account used to be the one
> nothing recorded. It subscribes to Razorpay's `payment.failed` event now,
> and the record keeps the product — because 'your payment failed' is not
> actionable and 'your payment for the USB-C cable failed because this
> account rejects foreign cards' is."

> "That reason is Razorpay's own words, quoted. This page and the Razorpay
> dashboard cannot end up describing the same failure differently."

> "And it did not retry. Three retries against a card that will never work is
> three attempts on somebody's account — it stopped, named the bound, and
> handed the decision back."

Then **Try again**, and scroll to **Can it succeed at all**:

```
Payment rails on this account                   from 13 real payments
  ⊖ UPI          UNTRIED     never attempted on this account
  ⊘ Card         REJECTED    4 attempts, none captured — "this business
                             accepts domestic (Indian) card payments only"
  ✓ Netbanking   WORKS  ⚠ needs a person      9 payments captured
  ⊖ Wallet       UNTRIED     never attempted on this account
```

> "Every verdict is read from what this account has actually done — a rail is
> 'works' only if money has been captured on it, never because somebody wrote
> it in a list. It resolved to netbanking and then stopped, because netbanking
> puts a person on the bank's page."

**Do not say "the agent retries until it succeeds."** It resolves, and hands
over where a person is genuinely required. Knowing which door is locked
before pulling the handle is most of what separates an agent from a retry
loop.

**Audit trail** — every financial action including the refusals, live:
`growth_refused`, `growth_applied`, `campaign_opened`, `order_missing_locally`.

**Approvals** has a real escalation waiting — an external agent proposing
over MCP, stopped by the gate:

> MSI Mechanical Keyboard + Logitech G502 — **₹6,224.16**
> ⚠ exceeds auto-approve limit of ₹5000.00 · **[Approve and order] [Deny]**

Say: *"The agent cannot approve its own request."* Approving places a real
Razorpay order, so only click it if you mean to.

Close on the honesty:

> "617 assertions pass across 25 suites. Two fail, deliberately: the money
> reconciliation compares what this app recorded against what Razorpay
> actually holds, and it is currently reporting a real mismatch I have not
> hidden. That check is the reason I trust the rest."

---

## If something breaks

| symptom | cause | do this |
|---|---|---|
| "Recommendations are unavailable" | on real Firestore and over quota | wrong store — restart the backend with nothing set |
| Backend refuses to start, banner about the emulator | emulator not running | `start-emulator.cmd` |
| "another process bound to a different datastore" | two backends running | stop the other; the banner names the pid |
| eBay returns nothing / 429 | rate limit or network | skip to `/trip` and the merchant side — **neither touches the network** |
| Netbanking page hangs | test-bank flakiness | abandon; the audit trail shows the abandonment, which is itself a beat |
| Growth queue all "Blocked" | agents switched off | that is the default — flip the switch on the panel |

## Do not say

- **"We support NPCI UAP."** No published spec exists. See `docs/PROTOCOLS.md`.
- **"We support x402."** The shape, over Razorpay. Not onchain, no USDC.
- **"ACP delegated payment tokens work."** They do not — the session
  declares `delegated_payment_tokens: false` and a token gets a 422.
- **"It books your trip."** One hotel leg is a real charge through a
  stand-in merchant. Nothing is reserved.
- **"Live prices."** The trip datasets are a snapshot.
- **"These are product photos."** The store's own catalogue carries
  generated illustrations, labelled as such on the tile.
- **"All tests pass."** 597 pass, 2 fail, on purpose. Say why — it is a
  better line.
- **Any conversion or uplift number.** The samples are single digits and
  there is no control group. The build says so itself.
