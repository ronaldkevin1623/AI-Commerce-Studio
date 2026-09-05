"""
ANALYTICS: THE SHOP'S OWN NUMBERS, AND A PERIOD TO COMPARE THEM TO.

The reference admin's analytics page is about thirty cards. Most of them —
sessions by landing page, sessions by social referrer, performance by
referring channel, customer cohort retention — are answers to questions
about WEB TRAFFIC, and this shop has none: there is no storefront theme, no
visitor, no referrer. Drawing those cards would mean either inventing the
numbers or shipping a page that is mostly "No data for this date range",
and the second teaches a merchant to stop reading the page at all.

So this computes the subset the data can actually answer, and each of those
properly — with a comparison period, which is the thing that turns a number
into information. ₹8,433 means nothing. ₹8,433, up 592% on the same length
of time before it, means something.

THE COMPARISON IS THE PRECEDING WINDOW OF EQUAL LENGTH

Not "the same days last month", which is a different number of weekends and
therefore not comparable for a shop. Seven days compares against the seven
before them. If that earlier window has nothing in it, the delta is reported
as None rather than as an infinite percentage — "up ∞%" from zero is the
single most common lie in commerce dashboards.

WHAT IS DELIBERATELY ABSENT FROM THE BREAKDOWN

Taxes and return fees. This store charges neither, and a "Taxes ₹0.00" row
says tax was computed and found to be nothing, which is a different
statement from "no tax is charged here". That is the same reasoning the ACP
totals already use, and it should not disagree with itself across two
surfaces of the same shop.
"""
import collections
from datetime import datetime, timedelta, timezone

CONSOLE = "Agent console"
UCP = "Storefront · UCP"
ACP = "Storefront · ACP"
TRIPS = "Trip sector"

# An order in any of these states took money. `demo_paid` and
# `simulated_paid` are seeded and simulated respectively, and both are
# counted here — but the payload says how many of the total were real, so
# nothing on the page can be read as more settled than it is.
PAID = ("paid", "demo_paid", "simulated_paid")
REAL_PAID = ("paid",)


def _as_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if hasattr(value, "timestamp"):
        try:
            return datetime.fromtimestamp(value.timestamp(), tz=timezone.utc)
        except Exception:
            return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _delta(now_value, before_value):
    """
    Percentage change, or None where the honest answer is "no comparison".

    Growth from zero is not a percentage. Every dashboard that prints one is
    choosing a large number over a true one.
    """
    if not before_value:
        return None
    return round(((now_value - before_value) / before_value) * 100, 1)


class _Window:
    """One period, its buckets, and everything that fell inside it."""

    def __init__(self, start, end, hourly):
        self.start = start
        self.end = end
        self.hourly = hourly
        if hourly:
            hours = int((end - start).total_seconds() // 3600) + 1
            self.keys = [start + timedelta(hours=i) for i in range(hours)]
        else:
            days = (end.date() - start.date()).days + 1
            self.keys = [start + timedelta(days=i) for i in range(days)]
        self.sales = {self._key(k): 0 for k in self.keys}
        self.orders = {self._key(k): 0 for k in self.keys}

    def _key(self, when):
        return when.strftime("%Y-%m-%dT%H") if self.hourly else when.strftime("%Y-%m-%d")

    def holds(self, when):
        return when is not None and self._key(when) in self.sales

    def add(self, when, amount_paise):
        key = self._key(when)
        if key in self.sales:
            self.sales[key] += int(amount_paise or 0)
            self.orders[key] += 1

    def series(self):
        return [{"at": key, "sales_paise": self.sales[key], "orders": self.orders[key]}
                for key in (self._key(k) for k in self.keys)]

    def total_paise(self):
        return sum(self.sales.values())

    def order_count(self):
        return sum(self.orders.values())


def _collect():
    """
    Every sale this shop can see, normalised into one shape.

    Four sources, because the shop genuinely has four ways in and a report
    that read only one of them would understate the business rather than
    simplify it.
    """
    rows = []
    try:
        from app.firebase_client import db
    except Exception as exc:
        print(f"[analytics] datastore unreachable: {exc}", flush=True)
        return rows

    def safe(collection):
        try:
            return [d.to_dict() or {} for d in db.collection(collection).stream()]
        except Exception as exc:
            print(f"[analytics] could not read {collection}: {exc}", flush=True)
            return []

    for row in safe("orders"):
        status = (row.get("status") or "").lower()
        items = [{"name": i.get("name") or row.get("product_name") or "Unnamed",
                  "amount_paise": int(i.get("price_paise") or 0) * int(i.get("quantity") or 1)}
                 for i in (row.get("items") or [])]
        if not items:
            items = [{"name": row.get("product_name") or "Unnamed",
                      "amount_paise": int(row.get("amount_paise") or 0)}]
        rows.append({
            "at": _as_datetime(row.get("created_at")),
            "amount_paise": int(row.get("amount_paise") or 0),
            "shipping_paise": int(row.get("shipping_cost_paise") or 0),
            "paid": status in PAID,
            "settled_for_real": status in REAL_PAID,
            "refunded": status == "refunded",
            "channel": CONSOLE,
            "customer": str(row.get("customer_id") or ""),
            "items": items,
        })

    for row in safe("merchant_checkouts"):
        status = (row.get("status") or "").lower()
        buyer = row.get("buyer") or {}
        rows.append({
            "at": _as_datetime(row.get("created_at")),
            "amount_paise": int(row.get("total_paise") or 0),
            "shipping_paise": 0,
            "paid": status == "paid",
            "settled_for_real": status == "paid",
            "refunded": status == "refunded",
            "channel": ACP if str(buyer.get("name")) == "ACP agent" else UCP,
            "customer": str(buyer.get("customer_id") or buyer.get("email") or ""),
            "items": [{"name": i.get("name") or i.get("id") or "Unnamed",
                       "amount_paise": int(i.get("amount_paise") or 0)}
                      for i in (row.get("line_items") or [])],
        })

    for row in safe("trips"):
        status = (row.get("status") or "").lower()
        stay = ((row.get("itinerary") or {}).get("stay") or {})
        rows.append({
            "at": _as_datetime(row.get("created_at")),
            "amount_paise": int(row.get("amount_paise") or 0),
            "shipping_paise": 0,
            "paid": status in PAID,
            "settled_for_real": status in REAL_PAID,
            "refunded": status == "refunded",
            "channel": TRIPS,
            "customer": str(row.get("customer_id") or ""),
            "items": [{"name": stay.get("name") or "Hotel stay",
                       "amount_paise": int(row.get("amount_paise") or 0)}],
        })

    return [r for r in rows if r["at"] is not None]


def _decisions():
    try:
        from app.firebase_client import db
        return [d.to_dict() or {} for d in db.collection("decisions").stream()]
    except Exception as exc:
        print(f"[analytics] could not read decisions: {exc}", flush=True)
        return []


def _scans():
    try:
        from app.firebase_client import db
        return [d.to_dict() or {} for d in db.collection("market_scans").stream()]
    except Exception as exc:
        print(f"[analytics] could not read market_scans: {exc}", flush=True)
        return []


def _month_key(when):
    return f"{when.year:04d}-{when.month:02d}"


def _month_label(key):
    year, month = key.split("-")
    return f"{_MONTHS[int(month) - 1]} {year}"


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _cohorts(sales, end, months_back: int = 8) -> dict:
    """
    Retention by the month a customer first bought.

    A row is everyone whose FIRST paid order landed in that month; the cells
    are the share of them who bought again in each following month. The grid
    is triangular because a cohort cannot have a result for a month that has
    not happened yet — an empty cell and a 0% cell are different facts and
    the shape is what keeps them apart.

    THE COHORT SIZE IS PRINTED ON EVERY ROW, AND THAT IS NOT DECORATION.

    Retention is a percentage, and a percentage over one customer is 0% or
    100% with nothing in between. On a shop this size the whole grid is
    therefore a coin toss rendered as a heatmap, and it is the most
    authoritative-looking card on the page. The size beside each row is what
    stops "100%" being read as a finding. This is the same reason the
    returning-customer tile carries "over 1 customer".
    """
    # Which months are columns at all: `months_back` ending with the window.
    months = []
    year, month = end.year, end.month
    for _ in range(months_back):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    months.reverse()
    index = {key: i for i, key in enumerate(months)}

    # Every month each customer bought in, and the first of them.
    active = {}
    for row in sales:
        if not row["paid"] or not row["customer"]:
            continue
        active.setdefault(row["customer"], set()).add(_month_key(row["at"]))

    rows = []
    for cohort_key in months:
        members = [c for c, seen in active.items() if min(seen) == cohort_key]
        if not members:
            # Kept rather than skipped: a month with no new customers is a
            # real and useful thing to see in a retention grid, and dropping
            # it would silently close the gap and misalign the diagonal.
            rows.append({"cohort": cohort_key, "label": _month_label(cohort_key),
                         "size": 0, "cells": []})
            continue

        cells = []
        for offset in range(len(months) - index[cohort_key]):
            target = months[index[cohort_key] + offset]
            count = sum(1 for c in members if target in active[c])
            cells.append({
                "offset": offset,
                "count": count,
                "pct": round((count / len(members)) * 100, 1),
            })
        rows.append({"cohort": cohort_key, "label": _month_label(cohort_key),
                     "size": len(members), "cells": cells})

    sizes = [r["size"] for r in rows if r["size"]]
    biggest = max(sizes) if sizes else 0

    # WHERE THE MONTHS IN THIS GRID CAME FROM.
    #
    # A retention grid is the most authoritative-looking thing on an
    # analytics page: five consecutive 100% cells reads as five months of a
    # real customer coming back. Here that row is one seeded customer whose
    # orders were written with backdated timestamps, and the page said so
    # only in a different card about payments. Somebody reading the grid on
    # its own would take the shape at face value, and the shape is the
    # seed's rather than the shop's.
    #
    # The sample-size caveat below was already honest about `n`. This is the
    # other half: honest about the calendar.
    paid_rows = [r for r in sales if r.get("paid")]
    real_rows = [r for r in paid_rows if r.get("settled_for_real")]
    seeded = len(paid_rows) - len(real_rows)
    provenance = (
        f" {seeded} of the {len(paid_rows)} orders behind this grid are "
        f"seeded or simulated history with backdated dates, and "
        f"{len(real_rows)} settled through Razorpay for real \u2014 so the "
        f"months shown are the seed's, not a trading record."
        if seeded else ""
    )

    return {
        "months": months,
        "month_labels": [_month_label(m) for m in months],
        "rows": rows,
        "customers": len(active),
        "note": (
            f"Cohorts are built from first paid order. The largest here has "
            f"{biggest} customer{'' if biggest == 1 else 's'}, so every "
            f"percentage in the grid is one customer's decision — read it as "
            f"a shape, not a rate." + provenance
            if biggest and biggest < 5 else
            "Each row is everyone whose first paid order landed in that month, "
            "and each cell is the share of them who bought again." + provenance
        ),
    }


def build(days: int = 30, start_date=None, end_date=None) -> dict:
    """
    Everything the analytics page shows, for a window and the window before it.
    """
    now = datetime.now(timezone.utc)
    midnight = {"hour": 0, "minute": 0, "second": 0, "microsecond": 0}

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start and end:
        if end < start:
            start, end = end, start
        end = min(end, now.replace(**midnight))
        span = max(1, min((end - start).days + 1, 366))
        start = end - timedelta(days=span - 1)
    else:
        span = max(1, min(int(days or 30), 365))
        end = now.replace(**midnight)
        start = end - timedelta(days=span - 1)

    # A day or two is read hour by hour, the way the reference does — a
    # two-point line for "today vs yesterday" is not a chart, it is a slope.
    hourly = span <= 2
    end_of_window = end.replace(hour=23, minute=59, second=59) if not hourly else \
        (end.replace(hour=23, minute=0) if end.date() < now.date() else now)

    current = _Window(start, end_of_window, hourly)
    prior_end = start - timedelta(seconds=1)
    prior_start = start - timedelta(days=span)
    previous = _Window(prior_start, prior_end, hourly)

    sales = _collect()

    gross = prior_gross = 0
    shipping = 0
    reversals = 0
    order_count = prior_orders = 0
    paid_count = 0
    # Everything that reached this window, paid or not. Only used for the
    # "never paid" note — it is the denominator of a disclosure, not of a
    # revenue figure.
    placed_count = 0
    real_settled = 0
    by_channel = collections.Counter()
    by_product = collections.Counter()
    product_units = collections.Counter()
    customers = collections.Counter()

    # ONLY PAID ROWS BECOME SALES.
    #
    # `_collect` carries a `paid` flag on every row precisely so this can be
    # decided here, and for a long time it was computed and then ignored:
    # gross, order count, channels and products all counted everything that
    # reached the window. The result was a "Total sales" figure containing
    # abandoned carts, a CANCELLED checkout and an unpaid trip — 65% of the
    # headline, on a dashboard whose footnote sat directly underneath
    # saying "4 of 7 orders in this window were never paid".
    #
    # An unpaid checkout is a thing that might become a sale. It is not one
    # yet, and a report that counts it has stopped being a report. The
    # abandonment is not lost by this — it is exactly what the recovery
    # agent reads, and the note below still counts it.
    for row in sales:
        when = row["at"]
        if current.holds(when):
            placed_count += 1
            if not row["paid"]:
                continue
            current.add(when, row["amount_paise"])
            gross += row["amount_paise"]
            shipping += row["shipping_paise"]
            order_count += 1
            paid_count += 1
            if row["refunded"]:
                reversals += row["amount_paise"]
            if row["customer"]:
                customers[row["customer"]] += 1
            if row["settled_for_real"]:
                real_settled += 1
            by_channel[row["channel"]] += row["amount_paise"]
            for item in row["items"]:
                by_product[item["name"]] += item["amount_paise"]
                product_units[item["name"]] += 1
        elif previous.holds(when):
            # The comparison window is filtered the same way, or the delta
            # would measure a change in how sales are counted rather than a
            # change in the business.
            if not row["paid"]:
                continue
            previous.add(when, row["amount_paise"])
            prior_gross += row["amount_paise"]
            prior_orders += 1

    # MARGIN GIVEN AWAY IS THIS SHOP'S ONLY DISCOUNT — BUT ONLY ONCE TAKEN.
    #
    # This used to sum every `growth_applied` decision in the window, which
    # counted an offer the moment it was APPLIED. An applied offer is
    # committed margin, not a discount on a sale: the agents say so when
    # they propose one — "costing X of margin if it is taken, and nothing
    # if it is not". Offers sitting on carts nobody has paid for were being
    # subtracted from net sales, and a run of the test suite could drag the
    # headline down by thousands of rupees for discounts that never
    # happened.
    #
    # Redeemed margin is attributed to the window the SALE fell in, not the
    # window the offer was created in, because that is when the money moved.
    # What was merely committed still has a home — the growth section's
    # budget view, where "spent today" is exactly the right question.
    from app.growth import attribution
    discounts = attribution.redeemed_between(
        current.start.timestamp(), current.end.timestamp())
    prior_discounts = attribution.redeemed_between(
        previous.start.timestamp(), previous.end.timestamp())

    funnel_counts = collections.Counter()
    for row in _decisions():
        when = _as_datetime(row.get("timestamp"))
        if current.holds(when):
            funnel_counts[row.get("action_type")] += 1

    searches = sum(1 for s in _scans() if current.holds(_as_datetime(s.get("timestamp"))))

    net = gross - discounts - reversals
    total = net + shipping
    prior_net = prior_gross - prior_discounts
    prior_total = prior_net

    aov = round(gross / order_count) if order_count else 0
    prior_aov = round(prior_gross / prior_orders) if prior_orders else 0

    repeat = sum(1 for c in customers.values() if c > 1)
    returning_rate = round((repeat / len(customers)) * 100, 1) if customers else None

    # The funnel this shop actually has. Not a conversion rate: there are no
    # sessions to divide by, and calling checkout-to-capture "conversion"
    # would invite it to be read as a storefront conversion rate, which is a
    # different and much larger denominator.
    opened = funnel_counts.get("merchant_checkout_opened", 0)
    captured = funnel_counts.get("merchant_payment_captured", 0) + \
        funnel_counts.get("payment_confirmed", 0)
    refused = funnel_counts.get("merchant_settle_rejected", 0)
    failed = funnel_counts.get("payment_failed", 0)
    abandoned = funnel_counts.get("run_abandoned", 0)

    funnel = [
        {"stage": "Searches run", "count": searches,
         "note": "an agent looked for something"},
        {"stage": "Orders created", "count": order_count,
         "note": "a Razorpay order was opened"},
        {"stage": "Paid", "count": paid_count,
         "note": f"{real_settled} of them settled for real; the rest are seeded or simulated"},
        {"stage": "Abandoned by the person", "count": abandoned,
         "note": "a run the buyer ended themselves"},
    ]

    def pct(part, whole):
        return round((part / whole) * 100, 1) if whole else None

    return {
        "window": {"from": start.date().isoformat(), "to": end.date().isoformat(),
                   "days": span, "granularity": "hour" if hourly else "day"},
        "compare": {"from": prior_start.date().isoformat(),
                    "to": prior_end.date().isoformat(), "days": span},
        "currency": "INR",
        "kpis": [
            {"key": "total_sales", "label": "Total sales", "unit": "paise",
             "value": total, "delta_pct": _delta(total, prior_total)},
            {"key": "orders", "label": "Orders", "unit": "count",
             "value": order_count, "delta_pct": _delta(order_count, prior_orders)},
            {"key": "aov", "label": "Average order value", "unit": "paise",
             "value": aov, "delta_pct": _delta(aov, prior_aov)},
            {"key": "returning", "label": "Returning customer rate", "unit": "percent",
             "value": returning_rate, "delta_pct": None,
             # Said on the tile, because a rate computed over one customer is
             # a number with no information in it and looks authoritative.
             "note": (f"over {len(customers)} customer{'' if len(customers) == 1 else 's'}"
                      if customers else "no paying customers in this window")},
        ],
        "sales_over_time": {
            "series": current.series(),
            "compare_series": previous.series(),
        },
        "breakdown": [
            {"label": "Gross sales", "value": gross, "delta_pct": _delta(gross, prior_gross)},
            {"label": "Discounts", "value": -discounts,
             "delta_pct": _delta(discounts, prior_discounts),
             "note": "margin given away by the growth agents"},
            {"label": "Sales reversals", "value": -reversals, "delta_pct": None,
             "note": "refunds recorded against an order in this window"},
            {"label": "Net sales", "value": net, "delta_pct": _delta(net, prior_net)},
            {"label": "Shipping charges", "value": shipping, "delta_pct": None,
             "note": "carried on the listing; this shop adds none of its own"},
            {"label": "Total sales", "value": total, "delta_pct": _delta(total, prior_total),
             "strong": True},
        ],
        # Named rather than silently missing, so nobody wonders whether the
        # page forgot them.
        "breakdown_omitted": [
            {"label": "Taxes", "why": ("Not charged. A zero row would say tax was "
                                       "computed and came to nothing, which is a "
                                       "different statement.")},
            {"label": "Return fees", "why": "This shop has no return fee to charge."},
        ],
        "by_channel": [
            {"label": label, "value": value, "pct": pct(value, gross)}
            for label, value in by_channel.most_common()
        ],
        "by_product": [
            {"label": label, "value": value, "units": product_units[label],
             "pct": pct(value, sum(by_product.values()))}
            for label, value in by_product.most_common(6)
        ],
        "funnel": funnel,
        # Deliberately NOT limited to the window: a retention grid clipped to
        # thirty days would be one column wide and could not show retention
        # at all. It ends at the window so the control still moves it.
        "cohorts": _cohorts(sales, end),
        "payments": {
            "refused_unverifiable": refused,
            "failed": failed,
            "captured": captured,
        },
        "notes": [
            note for note in [
                (f"{placed_count - paid_count} of {placed_count} checkouts in "
                 f"this window were never paid, so they are not counted as "
                 f"sales above.") if placed_count > paid_count else None,
                (f"Only {real_settled} of {paid_count} paid orders settled through "
                 f"Razorpay for real; the rest are seeded or simulated and are "
                 f"labelled as such rather than filtered out.")
                if paid_count and real_settled < paid_count else None,
                ("There is no web traffic here — no theme, no visitors, no referrers "
                 "— so sessions, conversion rate and landing-page reports are absent "
                 "rather than empty.") if True else None,
            ] if note
        ],
    }
