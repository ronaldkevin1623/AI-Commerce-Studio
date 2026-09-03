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

**State it starts in:** growth agents **off**, 3 proposals waiting, 1
campaign, 1 abandoned checkout, 1 approval pending, 8 products.

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

Switch the toggle to **Merchant** → **Growth**.

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

If asked about the rest — the answers are in `docs/PROTOCOLS.md`:

- **AP2** — implemented, ES256 mandate chain, 1,800-second expiry
- **x402** — the shape, settled over Razorpay, **not onchain**
- **NPCI UAP** — **not implemented, no published spec exists.** Unveiled
  9–11 Sept 2026, needs RBI approval. Say what the mandate chain and caps
  already enforce instead.

*Cut if short:* everything after the Storefront line.

## 4:25 — 5:00 · Why you can believe any of it

**Audit trail** — every financial action including the refusals, live:
`growth_refused`, `growth_applied`, `campaign_opened`, `order_missing_locally`.

**Approvals** has a real escalation waiting — an external agent proposing
over MCP, stopped by the gate:

> MSI Mechanical Keyboard + Logitech G502 — **₹6,224.16**
> ⚠ exceeds auto-approve limit of ₹5000.00 · **[Approve and order] [Deny]**

Say: *"The agent cannot approve its own request."* Approving places a real
Razorpay order, so only click it if you mean to.

Close on the honesty:

> "597 assertions pass across 25 suites. Two fail, deliberately: the money
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
