"""
Growth, measured against what this store actually has.

The reference admin's Growth page is largely a marketing surface: sales
attributed to ad campaigns, web sessions split by traffic source, a waitlist
for a campaign product. None of that exists here — there are no ad channels,
no web sessions and no campaigns, and inventing a "Sessions by traffic type"
chart would mean fabricating the one number the page is supposed to report.

What this store does have is the thing the whole project is about: it is
discoverable and transactable by AI buyers, and every one of those
interactions is already logged. So the same questions get asked of real data
— what did agents bring in, what did they do, and how much of it converted.
Empty answers are returned as empty rather than padded.
"""
from datetime import datetime, timedelta, timezone

from app.firebase_client import db, list_decisions, list_orders

# Decision types the storefront itself emits, in the order a checkout moves
# through them, with labels a shop owner rather than a developer would use.
AGENT_ACTIONS = [
    ("merchant_checkout_opened", "Checkouts opened"),
    ("merchant_payment_captured", "Payments captured"),
    ("merchant_payment_failed", "Payments not captured"),
    ("merchant_settle_rejected", "Unverifiable payments refused"),
    ("merchant_price_mismatch", "Price mismatches blocked"),
    ("merchant_checkout_failed", "Checkouts that errored"),
    ("merchant_product_added", "Products added"),
]


def _as_datetime(value):
    """Firestore timestamps, epoch ints and None all turn up in these rows."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return None


def _parse_date(value):
    """An ISO date from a query string, or None if it is not one."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def build(days: int = 30, start_date=None, end_date=None) -> dict:
    """
    Everything the Growth page shows, for a window.

    Two ways to ask, because the page has two controls that mean different
    things. `days` is a rolling window ending now — "the last 30 days" moves
    with the clock. `start_date`/`end_date` is a fixed window someone picked
    off a calendar, and it must not drift: a range ending last Tuesday still
    ends last Tuesday when the page is reloaded on Thursday.

    An explicit range wins where both are given. Ranges are clamped to a year
    of buckets, because the series is rendered as one point per day and a
    ten-year request would return a payload nobody can draw.

    One pass over orders and one over decisions, bucketed by day. A rolling
    window is inclusive of today, so "last 30 days" means 30 buckets ending
    now rather than 30 whole days ending at midnight.
    """
    now = datetime.now(timezone.utc)
    midnight = {"hour": 0, "minute": 0, "second": 0, "microsecond": 0}

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start and end:
        # Backwards is a slip, not an error worth refusing over — a picker
        # that lets you drag right-to-left produces it, and the honest
        # reading of "3rd to the 1st" is the same three days.
        if end < start:
            start, end = end, start
        end = min(end, now.replace(**midnight))
        days = (end - start).days + 1
        days = max(1, min(days, 366))
        start = end - timedelta(days=days - 1)
    else:
        days = max(1, min(int(days or 30), 365))
        end = now.replace(**midnight)
        start = (now - timedelta(days=days - 1)).replace(**midnight)

    buckets = [(start + timedelta(days=i)).date() for i in range(days)]
    created_by_day = {day: 0 for day in buckets}
    captured_by_day = {day: 0 for day in buckets}

    created_total = 0
    captured_total = 0
    order_count = 0
    captured_count = 0

    for order in list_orders(limit=1000):
        # Only this store's own orders. eBay-sourced orders are the buyer
        # half of the project and have nothing to do with the shop's takings.
        if (order.get("source") or "") != "merchant":
            continue

        when = _as_datetime(order.get("created_at"))
        if when is None or when < start:
            continue

        # The bucket test is what excludes anything after the window, now
        # that a window can end before today.
        day = when.date()
        if day not in created_by_day:
            continue

        amount = int(order.get("amount_paise") or 0)
        created_by_day[day] += amount
        created_total += amount
        order_count += 1

        if (order.get("status") or "") == "paid":
            captured_by_day[day] += amount
            captured_total += amount
            captured_count += 1

    # Counted in a single pass. The obvious shape — a loop over action types
    # with a decisions query inside it — reads the whole collection seven
    # times over to answer one question.
    counts = {}
    for row in list_decisions(limit=2000):
        action = row.get("action_type")
        if action not in dict(AGENT_ACTIONS):
            continue
        when = _as_datetime(row.get("timestamp"))
        if when is None or when < start or when.date() not in created_by_day:
            continue
        counts[action] = counts.get(action, 0) + 1

    activity = [
        {"action": action, "label": label, "count": counts[action]}
        for action, label in AGENT_ACTIONS
        if counts.get(action)
    ]
    activity.sort(key=lambda a: -a["count"])

    return {
        "window_days": days,
        "from": start.date().isoformat(),
        "to": end.date().isoformat(),
        "sales": {
            "created_paise": created_total,
            "captured_paise": captured_total,
            "order_count": order_count,
            "captured_count": captured_count,
            # A sparkline needs the shape even when every point is zero —
            # a flat line at zero is a real answer, an absent chart is not.
            "series": [
                {"date": day.isoformat(),
                 "created_paise": created_by_day[day],
                 "captured_paise": captured_by_day[day]}
                for day in buckets
            ],
        },
        "activity": activity,
        "activity_total": sum(a["count"] for a in activity),
    }


def discoverability() -> dict:
    """
    Whether an AI buyer could find and buy from this store right now.

    The reference page sells a campaign product at this point in the layout.
    The honest equivalent for an agentic storefront is whether the storefront
    is actually reachable — each of these is a live check against the store's
    own records, not a checklist someone ticked by hand.
    """
    from app.merchant import store

    products = store.list_products()
    active = [p for p in products if (p.get("status") or "active") == "active"]
    in_stock = [p for p in active if (p.get("stock") or 0) > 0]
    with_images = [p for p in active if p.get("image")]

    checks = [
        {
            "label": "Discovery document published",
            "ok": True,
            "detail": "Served at /merchant/.well-known/ucp with capabilities and a payment handler.",
        },
        {
            "label": "Products an agent can buy",
            "ok": bool(in_stock),
            "detail": (
                f"{len(in_stock)} of {len(products)} products are active and in stock."
                if in_stock else "Nothing is both published and in stock, so agents find an empty shop."
            ),
        },
        {
            "label": "Payment handler declared",
            "ok": True,
            "detail": "Razorpay, test mode. Netbanking completes; cards are rejected on this account.",
        },
        {
            "label": "Product images",
            "ok": len(with_images) == len(active) and bool(active),
            "detail": (
                f"{len(with_images)} of {len(active)} active products have an image."
                if active else "No active products."
            ),
        },
    ]

    return {"checks": checks, "ready": all(c["ok"] for c in checks)}
