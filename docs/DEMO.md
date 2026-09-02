# Five-minute demo

A running order for the pitch video. Every number below is one this build
actually produces — nothing here is a placeholder to be filled in later, and
nothing is staged. If a step goes differently on the day, say what happened;
the whole argument of this project is that the honest version is the
stronger one.

## Before you record

```bash
# 1 — the model
ollama serve

# 2 — backend  (from Cart-Pilot/backend)
venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010

# 3 — frontend (from Cart-Pilot/frontend)
npm run dev
```

Then, once:

```bash
python tests/run_all.py --offline
```

144 assertions, about 12 seconds, and it needs nothing external — no
network, no Firestore, no model. Worth having the green output on screen
behind you, and worth knowing it passed before you start.

The full run (`python tests/run_all.py`, 24 suites) is the better number to
quote, but it reads live eBay and Firestore, so run it well before you
record rather than during.

**Set up the two pieces of state the demo needs.**

1. **A promotion**, so retail media has something to show. Merchant →
   Products → Promoted placements: promote the *7-in-1 USB-C Hub*, bid ₹2,
   daily budget ₹50.
2. **Purchase history**, so the autonomous run has something to predict
   from. `POST /autonomy/demo/seed` writes orders marked `demo_paid` and
   `demo_seeded: true` — they are labelled as seeded in the data itself,
   which is the point. Clear them afterwards with `/autonomy/demo/clear`.

Leave `autonomy.enabled` **off**. Turning it on during the demo is a better
beat than having it already on.

---

## The five minutes

### 0:00 — The claim, on the landing page (20s)

> "This is an agent that shops for you, and a gate it cannot talk its way
> past. Both sides of the transaction are real — there's a buyer and there's
> a merchant, and they talk to each other over an open protocol."

Do not linger. The landing page is not the argument.

### 0:20 — Where it can shop (20s)

Open the shopper console. Point at the venue strip under the composer:

> "Three venues, three different kinds of entry point — a marketplace, a
> shop, and promoted placements. Two of them can actually ship. And it says
> *3 of 6 channel types built*, because social, in-store and other AI
> platforms are declared in the contract and not built. I'd rather tell you
> that than let you assume."

This lands the multi-channel architecture in one sentence and buys you
credibility for everything after it.

### 0:40 — A real search (60s)

Type: **`mechanical keyboard`**

While it runs, the reasoning stream is doing the work for you. Call out two
things and no more:

- *"20 of 26 listings are the product itself — set aside 6 accessories."*
  The agent knows a keycap set is not a keyboard.
- *"Flagged 2 of 20 as suspect."* Trust screening is statistics over the
  actual result set, not a model's opinion.

Then scroll to the strip below the results:

> "The merchant paid to put that USB-C hub in front of you. Look at where it
> is — *beside* the answer, not in it, and labelled as not being an answer
> to your search. It didn't move a single one of those five keyboards."

**This is the strongest 20 seconds in the demo. Do not rush it.**

If someone asks whether sponsorship could buy rank, the answer is a test:
`audit_21_sponsored` ranks the same candidates with the sponsored flag on
the best item, the worst, the middle, and nothing, and requires an identical
result every time — plus a ₹10,000,000 bid that changes neither sort key.

### 1:40 — The gate (60s)

Open a product, **Buy now**. Walk the mandate chain as it appears:

> "Before it fetched a single listing it signed what you asked for — the
> ceiling, the category, the venues. That's ES256, and you can verify it
> against a published public key without trusting my server. Now it signs
> the cart, and the chain check compares the price it's about to charge
> against the price you approved. Reprice the item after signing and this
> fails."

Then complete it: **Netbanking → Success**.

> "That's a real Razorpay capture. Not a card — this test account rejects
> every card and has UPI disabled, so netbanking is the only rail that
> completes. Six payments have gone through it, ₹93,848."

If the demo store item is the one you bought, say the better version:

> "That one closes the whole loop. Discovered over UCP, gated, signed, paid,
> and the merchant marked it packed. A real order on a real storefront."

### 2:40 — Autonomy (80s)

Go to the autonomy panel. **It is off.** Say so before you turn it on.

> "Everything so far, you asked for. The interesting question is what
> happens when nobody asks."

Turn it on. Run with `days_ahead` set forward.

> "It read this person's actual order history — six purchases of the same
> coffee, roughly every 30 days — and worked out that the next one is due.
> Nobody typed anything."

Then, immediately, the part that matters more:

> "And here are the five gates it had to get through. Every one of them can
> only say *no*. There's no confidence score anywhere in this system that
> can raise a limit — the only thing that raises a limit is a person. Coffee
> and cables replenish. Laptops and phones are never bought unattended at
> any price, and that's a list, not a price test."

Now the honest bit, and it is a strength:

> "The capture is simulated, and it says so in the record — not in a
> tooltip, in the order row. `status = simulated_paid`. The reason is
> netbanking needs a human at the bank's login page, and an unattended run
> can't put one there. Everything before the capture is real: the
> prediction, the live search, the screens, all five gates, the signed
> chain."

Show the audit entry with the sentence in it. A reviewer who finds that
themselves is impressed; a reviewer who is told it up front is convinced.

### 4:00 — Adversarial (40s)

Red team page. Run the corpus.

> "22 probes, all of them indirect prompt injection — hostile text hidden in
> listings the agent has to read. The screening that decides what gets
> bought reads prices, stock counts and seller feedback. It never reads
> seller prose, so there is nothing for that text to hijack."

If a probe is held, show the held count. If one gets through, show that
instead — a demo that admits a miss is worth more than one that doesn't.

### 4:40 — Close (20s)

> "One rule ran through all of it: nothing is faked. Where something can't
> be done for real, the product says so — the eBay listings are labelled
> *search only* because no seller will ship them, the sponsored slot says
> it isn't an answer, and the unattended purchase says its capture was
> simulated. 24 test suites, and the ones worth reading are the ones that
> exist because something went wrong."

---

## If something breaks

| What happens | What to say |
|---|---|
| eBay returns nothing | "That's a live API and it's having a moment — which is why the agent returns nothing rather than inventing filler." Switch to a merchant-store query. |
| Ollama is slow or down | The pipeline still runs; only the final phrasing needs the model. Point at the reasoning stream — those are rules, not generation. |
| The sponsored strip is empty | The promotion's daily budget is spent, or the search landed in a category it can't reach. Both are correct. Show the merchant panel's counters instead — `screened out at relevance` is a good story. |
| The netbanking page hangs | Say what it is: a test-mode simulator. Show a previously captured payment in the orders list. |

## Questions you should expect

**"Is the LLM picking the product?"** No. Two model-based relevance screens
were built and both failed on real data — one discarded an iPhone 12 as
"wrong type" and left 1 listing out of 23; the other scored everything 0.
The ranking is deterministic. `audit_19_engines` proves it by poisoning the
model client and requiring the ranking to still complete.

**"Could a merchant pay for a better position?"** No, and it is tested four
ways. See 0:40 above.

**"What's actually mocked?"** The unattended capture, and nothing else on
the critical path. The demo seed data is labelled `demo_seeded` in the
database. eBay fulfilment doesn't exist and is labelled *search only*
everywhere it appears.

**"Why guardrails if it's fully autonomous?"** Because autonomy is about who
initiates, not about who carries the loss. It's the person's money either
way.
