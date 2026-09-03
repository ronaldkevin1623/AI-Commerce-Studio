# Datastore selection, and the three guards on it

**The local Firestore emulator is the default. There is nothing to set.**

Run `start-emulator.cmd` once, then start the backend. No environment
variable, no `.env` edit, no switching. The emulator imports
`firebase-export/` on start and writes it back on a clean exit, so demo
data survives restarts.

Real Firestore is opt-in with `CARTPILOT_STORE=real`, and it exists for
exactly one job: reconciling recorded money against the Razorpay account.
That is an occasional check, not a mode to develop in — which is why it is
the case that has to ask. Nothing else in the product needs it: the agent,
the sectors, the recommendations and the merchant loop behave identically
on the emulator, and Razorpay is real either way because it is a separate
service with no quota of its own.

The free tier's daily read quota is the reason for this default. Hitting it
mid-demo takes the whole app down, and it did.

It used to work the other way: `.env` carried `FIRESTORE_EMULATOR_HOST` and
the quota poller rewrote that file. The history below is kept because it is
why the first two guards exist and what they were built against.

Razorpay is real in **both** cases. That asymmetry is the whole problem: a
payment always happens for real, but the record of it goes wherever
Firestore happens to be pointing.

## What can actually go wrong

`db = firestore.client()` is bound at module import
([firebase_client.py](../backend/app/firebase_client.py)), and the library
reads `FIRESTORE_EMULATOR_HOST` when the client is constructed. uvicorn runs
without `--reload`. Two consequences:

- Rewriting `.env` **cannot** re-point a running server. A single checkout —
  order, bank page, capture — runs in one process against one client, so a
  file edit alone cannot split it.
- Two holes remain:
  1. **A restart between the halves.** Order lands in store A, capture in
     store B. The poller doesn't restart anything, but a crash, a deploy, or
     a manual restart does — and netbanking leaves a human on a bank page
     for minutes, which is the widest window there is.
  2. **Stranded writes.** The poller flips `.env` while a server already
     bound to the emulator keeps running. Nothing is split, but everything
     that server writes afterwards goes to a store that is about to be
     treated as non-authoritative — and the emulator is in-memory, so it is
     also not persistent.

Hole 2 is what produced `pay_TX27e4NKLGuuvX` (₹829.17, 2 Sep 09:46).

## Guard 1 — the switch waits, then warns

`backend/app/inflight.py` keeps one marker file per open checkout in
`backend/.inflight/`.

**On disk, not in Firestore, deliberately.** The datastore is the thing being
switched; a marker written into it would be in the store nobody is reading
any more after a switch — circular, and it would fail exactly when needed.

- Opened in `save_order()` and in `/trip/book`, so all seven order-creating
  paths are covered at one hook each rather than seven.
- Closed in `update_order_status()` on `paid`, `failed`, `refunded`,
  `cancelled`. A failed checkout must clear too, or every abandonment blocks
  switching until its TTL expires.
- **TTL 20 minutes.** Longer than a bank page; short enough that a closed tab
  does not hold the system hostage. Stale and unparseable markers are swept
  on read.

`wait_for_inflight()` in the poller polls the register every 20s up to
**8 minutes**, then proceeds with a warning naming the order ids. It waits;
it does not block forever — a poller that never returns because someone
closed a tab is a worse failure than a warned-about one.

Its original job was holding the `.env` switch. There is no switch any more,
so it now serves the reconciliation instead: fewer open checkouts means
fewer captures `audit_3_live` has to hold out.

Measured:

```
clear register, 1s ceiling   -> "no checkouts in flight"        (no hold)
one open, 3s ceiling         -> held for 3s, then:
  "WARNING: switching datastore with 1 checkout(s) in flight:
   order_TESTinflight (3s ago). Waited 3s and they did not settle..."
stale marker past TTL        -> ignored and swept
unparseable marker           -> ignored and swept
```

## Guard 2 — the split becomes visible

Guard 1 is poller-side, so it structurally cannot catch hole 1: the poller
is not involved in a restart. So orders now carry the binding they were
written under.

- `STORE_BINDING` is computed once at import — `real`, or
  `emulator:<host>`. Fixed for the process's lifetime, like the client.
- `save_order()` stamps it on every order.
- `verify-payment` looks the order up **before** doing anything else and
  logs, without blocking the payment:
  - `order_missing_locally` — a capture arrived for an order this datastore
    has no record of.
  - `datastore_binding_changed` — the order was created against one store
    and is being confirmed against another.

It cannot repair a split; the other store may not be reachable. It refuses
to record one silently, which is the difference between a traceable anomaly
and a number that is quietly wrong.

Measured:

```
unknown order            -> order_missing_locally logged
order stamped emulator,
  confirmed against real -> "Order order_SPLITTEST was created against
                            emulator:127.0.0.1:8085 but is being confirmed
                            against real. The two halves of this checkout
                            landed in different datastores."
trip stay order          -> NOT flagged
```

That last line was a real bug caught in testing. Trip stays are stored in
`trips`, not `orders`, so the first version flagged **every** genuine trip
capture. `record_for_razorpay_order()` now spans both collections — a guard
that cries wolf on normal traffic is one people learn to ignore.

## Guard 3 — the store is chosen per process, and ambiguity is fatal

`CARTPILOT_STORE` (`real` | `emulator` | `emulator:<host>:<port>`) is read at
launch. `.env` is no longer rewritten by anything.

`app/datastore_guard.py` runs inside `firebase_client.py`, between
`load_dotenv()` and `firestore.client()`. It lives there rather than in
`main.py` because **34 modules import `app.firebase_client` directly** —
every test suite among them — and none go through `main.py`. In the import
path of the client itself, it cannot be skipped by anything that touches
Firestore.

It prints a banner and calls **`os._exit(1)`** — not `SystemExit`, which is
an exception a bare `except:` up the import chain could swallow.

It refuses on:

1. **A leftover `FIRESTORE_EMULATOR_HOST` in `.env`.** Checked in the raw
   file text *and* `os.environ`, because `load_dotenv()` does not override a
   variable already set in the real environment — so an environment-only
   check would miss exactly this case. Commented-out lines do not trip it.
2. **An externally-set host disagreeing with `CARTPILOT_STORE`.**
3. **An unrecognised value** — a typo falling back to real data is the
   accident being prevented.
4. **Another live process on a different store**, via a PID registry in
   `backend/.bindings/` (gitignored). Dead entries are swept; a 24-hour
   backstop covers recycled PIDs.

Verified by execution, all nine paths:

```
CARTPILOT_STORE unset          -> real
CARTPILOT_STORE=emulator       -> emulator:127.0.0.1:8085
CARTPILOT_STORE=prod           -> REFUSED, exit 1
leftover key in .env           -> REFUSED, exit 1
leftover + asking for emulator -> REFUSED, exit 1
commented-out key in .env      -> real (not tripped)
live 'real' proc, want emulator-> REFUSED, names the pid and its file
dead proc's stale entry        -> swept, start allowed
two procs on the SAME store    -> both allowed
```

**What it still does not guarantee**, stated rather than implied:

- Processes on separate filesystems share no registry.
- Two processes starting within the same few milliseconds can both read "no
  conflict" before either writes. Milliseconds against a checkout measured
  in minutes — small, not zero.
- A recycled PID reads as live. That fails **closed** (refuses to start), and
  the banner names the file to delete.

So: **one detectable failure mode instead of two, not zero.** A restart
between an order and its capture, with a changed `CARTPILOT_STORE`, still
splits a checkout — and Guard 2 logs it.

### What changed around it

| piece | change |
|---|---|
| `revert_to_real_data()` | **Deleted.** Kept as a no-op it would have reported `"reverted"` while changing nothing — the next person debugging a wrong-store write would have ruled out the cause. |
| `--revert-only` | Removed. |
| suite subprocess | Launched with `CARTPILOT_STORE=real` in its env. Nothing on disk is mutated, so nothing needs restoring. |
| `wait_for_inflight()` | Repurposed: it no longer guards a switch (there is none), it lets checkouts settle so the reconciliation has fewer to hold out. |
| `audit_3_live` | Holds out captures whose order is still in the in-flight register and **names them**, instead of counting them as unrecorded money. |
| `/health` | Now reports `datastore`. |
| `seed_demo.py` | **Asks the server** instead of reading its own `.env`. It writes through a running server over HTTP, and that server's store is fixed by how *it* launched — the two can disagree, and the seeder would have announced "emulator" while filling real Firestore. Refuses if the server does not report a binding. |
| `.env.realdata.bak` | No longer any script's business. Stays on disk until its owner removes it. |

Dual-client routing — routing the capture write to the store named in the
order's own stamp, the only genuinely structural fix — remains a stretch
goal and is **not** built.

## The unattended post-quota run

`cartpilot-quota-rerun` (daily, 12:40 IST — ten minutes after the free-tier
quota resets at 00:00 US/Pacific) runs
`tests/rerun_when_quota_resets.py --skip-if-done`, which polls until real
Firestore answers and then runs three things in order, writing all of them
to `backend/quota_rerun_report.txt`:

1. **The orphaned-order backfill, PREVIEW ONLY.** Never `--commit`. An
   unattended task at midnight does not get to write a financial record on
   someone's behalf; it shows what it *would* write so a person can compare
   it against what they approved.
2. **`audit_3_live` on its own**, so the money reconciliation stays legible
   even if the quota runs out again during the full suite and buries it.
3. **The full suite.**

The report opens with what still needs a human, because a reader who sees
three green sections and stops reading is exactly the reader it is written
for: the backfill was a preview, nothing was written, and
`.env.realdata.bak` remains pending. A clean preview is not a verification.

The trigger was previously one-time and had **already fired**, so the task
would never have run again — `NextRunTime` was empty. It is now daily, and
`--skip-if-done` stops it repeating once a run finishes cleanly (that gate
correctly ignores `DONE WITH FAILURES`, verified).

## The emulator is in-memory

`firebase emulators:start --only firestore` with no `--import` or
`--export-on-exit` keeps everything in the Java process's heap. Anything
written while pointed at the emulator dies with that process.

Exported 2 Sep to `firebase-export/` (719K, gitignored) plus a readable
`emulator-dump.json`. Contains the ₹829.17 order and 34 others:

```
agent_settings 1 · customers 1 · decisions 61 · market_scans 13
merchant_products 6 · orders 35 · redteam_runs 1 · runs 11
```
