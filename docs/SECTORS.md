# Sectors

`/` used to open straight into product templates. That quietly asserted
that products were the only kind of commerce the agent does. Now `/` opens
the list of **sectors**, and a sector's own templates are one level down.

The list is served by `GET /sectors`, which reads the registry. Nothing in
the front end names a sector. Registering one makes it appear in the menu.

---

## What a sector supplies

`backend/app/sectors/base.py` defines the contract. Five members:

| member | why it differs per sector |
|---|---|
| `intent_schema()` | what has to be known before searching. A products search can run on a phrase; a trip with no destination is not an under-specified search, it is not a search. |
| `adapters()` | where candidates come from. **Per sector, never the global venue registry.** |
| `evaluation_criteria()` | what "better" means here, named and weighted, as data the UI can show. |
| `templates()` | the second-level `/` menu. **May be empty.** Products has templates because browsing is a real starting point; trip returns none, because by the time you open it you know where you are going and a canned "3 nights in Kolkata" is a wrong answer to clear, not a shortcut. A sector returning nothing here is the cheapest proof that sectors are not required to look alike. |
| `assemble()` | *optional.* How candidates combine into one answer. |

`assemble` is the honest reason this interface exists. Products has none:
the best row **is** the answer. A trip must have one, because a flight, a
hotel and three meals are only an answer once they fit each other. Without
it, this would have been a naming convention.

---

## Real vs. stand-in, stated plainly

**Products — unchanged.** Live eBay search, live merchant catalogue, real
Razorpay orders and captures. The sector refactor added nothing to it and
removed nothing from it. `/deal` and `/premium` are exactly the templates
they were, now under `/products`.

**Trip — real numbers, snapshot data, one payable leg.**

| | status |
|---|---|
| fares, nightly rates, taxes, meal costs | **real** — every value comes from the supplied datasets (300,153 flights, 580 hotels, 31,297 restaurants) |
| assembly, totals, ranking, shrinkage | **real work** over those numbers |
| availability on a date | **not asserted.** No provider is called. Prices do not move. Departure is a window ("Evening"), never a time |
| flight booking | **not built.** `can_fulfil = False` |
| restaurant reservation | **not built.** `can_fulfil = False` |
| hotel stay | **payable — through a demo-merchant stand-in** |

### The payable leg

A real Razorpay capture happens, and it is **not a booking**. No room is
held; no hotel is contacted. Production would require direct hotel-supplier
integration. That sentence is on the card in the UI, not only here.

What makes the charge meaningful rather than decorative is that it is tied
to the specific hotel the itinerary chose:

1. The client posts **only** `hotel_record_id`. It sends no price.
2. `POST /trip/book` re-reads that row and derives
   `(nightly + tax) x nights` server-side. A tampered or stale price in the
   browser cannot become the amount charged. An unknown id is a 404 — no
   price can be derived, so no order is created.
3. The Razorpay order carries `hotel_record_id` in its **notes**, so the
   link survives outside this app's database and can be read back from the
   Razorpay API.
4. `verify-payment` reads those notes back and writes the record id, the
   asserted amount and the capture id into **one** audit row — so the chain
   is readable without a join.

Verified end to end:

```
itinerary  -> hotel:mumbai:21  City Stay, Andheri East, 4.6* (214 reviews)
asserted   -> (Rs1,229 + Rs370 tax) x 2 nights = Rs3,198
razorpay   -> order_TX7qxzJj9XnASw, amount Rs3,198
notes      -> hotel_record_id=hotel:mumbai:21   (read back from Razorpay)
re-derived from the dataset row alone: Rs3,198 — matches
```

---

## Isolation

Trip adapters are returned by `TripSector.adapters()` and registered
nowhere else. If they ever reached `app.adapters.registry`, a search for
earbuds would start returning flights. Measured, not asserted:

```
global venue adapters BEFORE importing trip: ['ebay', 'merchant', 'sponsored']
global venue adapters AFTER  importing trip: ['ebay', 'merchant', 'sponsored']
trip adapters: ['trip-flights', 'trip-hotels', 'trip-restaurants']  (none leaked)
```

Products stays the default runtime path. With no `/` prefix, `handleSend`
makes the same call it always did — the default does not route through new
code, which is the only way to actually keep that promise.

Full suite before and after the sector work: **577 assertions passed, 2
failed, 24 suites** — identical both times. Both failures are the money
reconciliation and predate this work (see below).

---

## Adding a third sector

Four steps, none of them in the front end.

1. Write `backend/app/sectors/<name>.py` with a class satisfying `Sector`.
2. Give it adapters — plain objects with `name`, `kind`, `can_fulfil`,
   `available()`, `search()`. Return them from `adapters()`. Do **not**
   register them globally.
3. Write `classify(text) -> 0.0..1.0`. Each sector scores its own claim;
   there is no central vocabulary map, because that map is exactly the
   thing that would need editing every time a sector is added.
4. Add one line to `registry.bootstrap()`.

The `/` menu, the intent classifier, the audit trail and the spend cap all
pick it up with no further change.

### Classification, and when it refuses

`registry.classify()` returns the winner **and every loser's score**, so
"why did my trip run as a product search" is answerable later. It asks
rather than guesses when confidence < 0.30 or the margin < 0.15.

```
"wireless earbuds under 2000 fast delivery"  -> products  [products=0.95 trip=0.00]
"2 nights in Mumbai from Delhi under 20000"  -> trip      [products=0.42 trip=0.80]
"cheap flight to Kolkata"                    -> trip      [products=0.37 trip=0.68]
"something nice"                             -> asks      [products=0.00 trip=0.00]
```

Coverage is six metros — Bangalore, Chennai, Delhi, Hyderabad, Kolkata,
Mumbai — because that is what the data has. "weekend in Goa" says so by
name rather than asking "where are you going?" to someone who just said.

---

## Known open item

The two failing reconciliation assertions are **not** caused by the sector
work. A real netbanking purchase (`pay_TX27e4NKLGuuvX`, Rs829.17, 2 Sep
09:46) was recorded correctly — order `paid`, payment id linked,
`payment_confirmed` decision row — but into the **Firestore emulator**,
because that is where `.env` pointed at the time. `.env` was reverted to
real Firestore at 12:38. Razorpay is real in both cases, so the real-data
reconciliation sees a capture it has no local record of. The record is not
lost; it is in the other store.
