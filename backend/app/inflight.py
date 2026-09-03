"""
WHICH CHECKOUTS ARE MID-FLIGHT RIGHT NOW.

A checkout is not one moment. An order is created, a human then sits on a
bank page for anything up to several minutes, and only then does
verify-payment run. Both halves have to land in the same datastore or the
result is an order in one store and a capture in another, with neither
store holding a complete record.

The datastore is exactly what the switching mechanism changes, so this
register is kept on DISK rather than in Firestore. Writing "a checkout is
in progress" into the store whose identity is in question would be
circular: after a switch, the marker would be in the store nobody is
reading any more, which is the same failure it exists to prevent.

One file per open checkout, named for the Razorpay order id. Creating and
deleting a file is atomic enough for this — the reader only ever asks "is
anything open", and a marker that is a few milliseconds stale changes
nothing about the answer.

STALENESS IS DELIBERATE, NOT A BUG. A marker is ignored once it is older
than TTL_SECONDS. Checkouts are abandoned all the time — a browser is
closed, a bank page is left open — and without a TTL a single abandoned
one would block every future environment switch forever. Twenty minutes is
comfortably longer than a netbanking page takes and short enough that a
dead marker does not hold the system hostage.
"""
import json
import os
import time
from pathlib import Path

DIR = Path(__file__).resolve().parents[1] / ".inflight"

# Longer than a bank page realistically takes, short enough that an
# abandoned checkout stops mattering the same working session.
TTL_SECONDS = 20 * 60


def _path(order_id: str) -> Path:
    # Razorpay ids are alphanumeric with an underscore, but this is a
    # filename built from something that arrived over HTTP, so it is
    # constrained here rather than trusted.
    safe = "".join(c for c in str(order_id) if c.isalnum() or c in "_-")
    return DIR / f"{safe}.json"


def open_checkout(order_id: str, *, store: str = "", detail: str = "") -> None:
    """Record that money is about to move against this order."""
    if not order_id:
        return
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        _path(order_id).write_text(json.dumps({
            "order_id": order_id,
            "store": store,
            "detail": detail,
            "opened_at": time.time(),
        }), encoding="utf-8")
    except Exception as exc:
        # Never fail a checkout because bookkeeping about the checkout
        # failed. A missing marker degrades the guard; a raised exception
        # here would break the thing the guard is protecting.
        print(f"[inflight] could not mark {order_id}: {exc}", flush=True)


def close_checkout(order_id: str) -> None:
    """The order reached a terminal state — captured, failed, whatever."""
    if not order_id:
        return
    try:
        _path(order_id).unlink(missing_ok=True)
    except Exception as exc:
        print(f"[inflight] could not clear {order_id}: {exc}", flush=True)


def active(ttl_seconds: int = TTL_SECONDS) -> list[dict]:
    """
    Checkouts opened recently enough to still be believable.

    Sweeps expired markers as it goes, so an abandoned checkout stops
    being reported without anyone having to remember to clean up.
    """
    if not DIR.exists():
        return []
    now = time.time()
    live = []
    for entry in DIR.glob("*.json"):
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except Exception:
            # Unreadable marker: it cannot be reasoned about, so it is not
            # allowed to block a switch indefinitely either.
            entry.unlink(missing_ok=True)
            continue
        age = now - float(data.get("opened_at") or 0)
        if age > ttl_seconds:
            entry.unlink(missing_ok=True)
            continue
        data["age_seconds"] = int(age)
        live.append(data)
    return sorted(live, key=lambda d: d["age_seconds"])


def describe() -> str:
    """One line, for a log or a warning."""
    rows = active()
    if not rows:
        return "no checkouts in flight"
    parts = ", ".join(f"{r['order_id']} ({r['age_seconds']}s ago)" for r in rows)
    return f"{len(rows)} checkout(s) in flight: {parts}"
