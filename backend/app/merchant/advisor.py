"""
THE MERCHANT'S SIDE OF THE CONVERSATION.

The buying agent takes a sentence from a shopper and turns it into a
transaction. This takes a sentence from a shop owner and turns it into an
analysis: they ask "give me a structured report of revenue growth this week"
and get one, computed from this shop's own orders, checkouts and decision
log.

HOW A QUESTION BECOMES AN ANSWER

    1. the WINDOW is parsed by rule      "this week" -> a real date range
    2. the INTENT is routed              rules first, then the local model
    3. the REPORT is computed            deterministic, from the datastore
    4. the PROSE is composed             from what step 3 found

THE MODEL ROUTES. IT NEVER NARRATES, AND IT NEVER SEES A NUMBER.

This is the important line and it is the same one the buying agent draws.
Ask a language model to summarise a growth report and it will produce
"customers who buy X have a 38% chance of buying Y" whether or not anything
supports it, because that is what the training data looks like. So the model
is given the question and a list of report names, and returns one of those
names and a window. If it returns anything else the answer is discarded.
Every figure below it is arithmetic over Firestore.

That split is what lets this answer an open-ended question honestly: the
flexible part is understanding what was asked, and the rigid part is what
gets said back.
"""
import json
import re
from datetime import datetime, timedelta, timezone

# ── Windows ──────────────────────────────────────────────────────────────
#
# Parsed by rule rather than by the model, for the same reason the buying
# agent parses budgets by rule: a window is the denominator of every number
# in the answer, and a model that can be talked into widening it can be
# talked into changing every figure at once.

_TODAY = r"\btoday\b"
_YESTERDAY = r"\byesterday\b"
_THIS_WEEK = r"\bthis week\b|\bpast week\b|\bthe week\b"
_LAST_WEEK = r"\blast week\b|\bprevious week\b"
_THIS_MONTH = r"\bthis month\b|\bmonth to date\b|\bmtd\b"
_LAST_MONTH = r"\blast month\b|\bprevious month\b"
_LAST_N = r"\blast\s+(\d{1,3})\s*(day|days|week|weeks|month|months)\b"
_QUARTER = r"\bthis quarter\b|\bquarter\b|\bqtd\b"
_YEAR = r"\bthis year\b|\byear to date\b|\bytd\b"


def parse_window(text: str) -> dict:
    """
    The date range the question is about, and how it was read.

    `label` is what the answer will call it. Saying "over the last 7 days"
    when somebody asked for "this week" is a small lie that makes every
    number in the report slightly untrustworthy.
    """
    blob = (text or "").lower()
    today = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)

    def span(start, end, label):
        return {"from": start.date().isoformat(), "to": end.date().isoformat(),
                "days": (end.date() - start.date()).days + 1, "label": label}

    if re.search(_YESTERDAY, blob):
        day = today - timedelta(days=1)
        return span(day, day, "yesterday")
    if re.search(_TODAY, blob):
        return span(today, today, "today")
    if re.search(_LAST_WEEK, blob):
        # Weeks start Monday, which is what a shop means by "last week".
        this_monday = today - timedelta(days=today.weekday())
        start = this_monday - timedelta(days=7)
        return span(start, this_monday - timedelta(days=1), "last week")
    if re.search(_THIS_WEEK, blob):
        start = today - timedelta(days=today.weekday())
        return span(start, today, "this week")
    if re.search(_LAST_MONTH, blob):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return span(last_prev.replace(day=1), last_prev, "last month")
    if re.search(_THIS_MONTH, blob):
        return span(today.replace(day=1), today, "this month")
    if re.search(_YEAR, blob):
        return span(today.replace(month=1, day=1), today, "this year so far")
    if re.search(_QUARTER, blob):
        first_month = 3 * ((today.month - 1) // 3) + 1
        return span(today.replace(month=first_month, day=1), today,
                    "this quarter so far")

    found = re.search(_LAST_N, blob)
    if found:
        count = max(1, int(found.group(1)))
        unit = found.group(2)
        days = count * (7 if unit.startswith("week")
                        else 30 if unit.startswith("month") else 1)
        days = min(days, 365)
        return span(today - timedelta(days=days - 1), today,
                    f"the last {count} {unit}")

    return span(today - timedelta(days=29), today, "the last 30 days")


# ── Intents ──────────────────────────────────────────────────────────────

INTENTS = [
    # The three most specific first. Each of these was previously swallowed
    # by a broader pattern below and answered as a different report — "how
    # much did I spend on discounts" matched `revenue` and came back with
    # proposals to spend more.
    ("discounts", r"\b(discount\w*|margin|gave away|given away|giving away|"
                  r"offers? cost|cost of (the )?offers?|coupon\w*|"
                  r"promo(tion)?s? cost)\b"),
    ("conversion", r"\b(conversion|convert\w*|abandon\w* rate|"
                   r"checkout rate|close rate|how many .*(paid|bought)|"
                   r"drop[- ]?off)\b"),
    ("restock", r"\b(restock\w*|re-?order|stock more|running (low|out)|"
                r"out of stock|reorder|replenish\w*|days of cover|"
                r"what should i (stock|buy|order))\b"),
    # First, deliberately. "Compare this month to last month" also contains
    # words the report and performance patterns match, and an explicit
    # request to COMPARE is more specific than either — it names the shape
    # of the answer, not just the subject.
    ("compare", r"\b(compare\w*|comparison|versus|vs\.?|month[- ]over[- ]month|"
                r"mom|against last (month|week)|better or worse|up or down|"
                # "Am I growing or shrinking" is a comparison question, and
                # it used to match `revenue` on the word "growing" — which
                # answered it with proposals rather than with the trend.
                r"growing or shrinking|shrink\w*|trending|trend)\b"),
    ("report", r"\b(report|breakdown|detailed|detail|structured|full picture|"
               r"deep dive|summar(y|ise|ize)|overview|how did we do|"
               r"performance report)\b"),
    ("revenue", r"\b(opportunit\w*|grow\w*|increase\w*|upsell\w*|"
                r"cross[- ]?sell\w*|bundle\w*|make more|more sales|"
                r"boost|improve)\b"),
    ("problems", r"\b(problem\w*|wrong|broken|fail\w*|lost|losing|leak\w*|"
                 r"abandon\w*|refus\w*|block\w*|risk\w*|issue\w*)\b"),
    ("agents", r"\b(agent\w*|automat\w*|autonom\w*|what can you|who are you|"
               r"capabilit\w*)\b"),
    ("customers", r"\b(customer\w*|buyer\w*|retention|repeat\w*|returning|"
                  r"cohort\w*|churn\w*|lapsed)\b"),
    ("products", r"\b(product\w*|stock\w*|inventor\w*|catalogue\w*|catalog\w*|"
                 r"item\w*|sell\w*|seller\w*|sku\w*)\b"),
    ("performance", r"\b(how am i|performance|doing|sales|order\w*|revenue|"
                    r"number\w*|aov|average order|channel\w*|traffic)\b"),
]

ROUTES = [i for i, _ in INTENTS]

# The patterns whose match is evidence on its own. See `ask` for why the
# other three are not on this list: each of them matches a single word that
# is ordinary English about a shop, and each produced a measured mis-route.
TRUSTED_RULES = {"discounts", "conversion", "restock", "compare", "report",
                 "customers", "problems", "agents"}

CAN_ANSWER = [
    "Compare this month to last month",
    "Give me a detailed report of revenue growth this week",
    "Find me an opportunity to increase revenue",
    "How much have I spent on discounts?",
    "What is my checkout conversion rate?",
    "What should I stock more of?",
    "How is the shop doing this month?",
    "What is going wrong?",
    "Who are my customers?",
    "Set the price of the desk lamp to 1200",
    "Publish the prototype stand",
]


def classify(text: str) -> str:
    blob = (text or "").lower()
    for intent, pattern in INTENTS:
        if re.search(pattern, blob):
            return intent
    return "unknown"


def classify_all(text: str) -> list[str]:
    """
    Every intent this question touches, in the order the rules declare them.

    `classify` answers "which report is this" and returns the FIRST match,
    which is right for a single question and wrong for a compound one. A
    merchant who asks for "a detailed report on revenue growth AND what can
    be done to increase revenue" is asking two things; the first-match rule
    silently answered the first and dropped the second, and because the
    report it returned was correct and detailed, nothing on screen said
    that half the question had been ignored.
    """
    blob = (text or "").lower()
    return [intent for intent, pattern in INTENTS if re.search(pattern, blob)]


def route_with_model(text: str) -> str | None:
    """
    Ask the local model which report answers this, when the rules cannot tell.

    It is given the question and the list of report names and asked for one
    of them. Nothing it returns is shown to anybody: an unrecognised answer
    is dropped and the question falls through to the "I could not tell"
    reply. The model widens what can be UNDERSTOOD; it cannot widen what
    gets SAID.
    """
    try:
        from app.agent.ollama_agent import _client
        from app.config import OLLAMA_MODEL
    except Exception:
        return None

    # THE MODEL IS ASKED WHETHER A REPORT ANSWERS THE QUESTION, NOT WHICH
    # ONE IS CLOSEST.
    #
    # Asked to pick the nearest report, a model always finds one — and the
    # result is a confident answer to a DIFFERENT question, carrying real
    # computed figures, which is far harder for a merchant to catch than a
    # refusal. Observed: "how much did I spend on discounts?" routed to
    # `revenue` and came back with proposals to spend more; "what is my
    # best day of the week?" routed to `performance` and returned the
    # week's total. Both true, neither an answer.
    #
    # `none` already falls through to the honest "I could not tell", so the
    # only change needed is to make it the expected answer rather than the
    # last resort. Widening what can be UNDERSTOOD was always the point;
    # widening what gets CLAIMED was not.
    prompt = (
        "A shop owner asked a question. Decide whether one of the reports "
        "below ANSWERS it \u2014 not which one is closest to its subject.\n\n"
        "Reply with JSON only, of the form {\"report\": \"<name>\"}.\n\n"
        "Reports:\n"
        "  compare     \u2014 this month against last month, same number of days\n"
        "  discounts   \u2014 margin committed to and redeemed from growth offers\n"
        "  conversion  \u2014 how many opened checkouts were paid\n"
        "  restock     \u2014 what is selling fast against the stock held\n"
        "  report      \u2014 a full structured breakdown of the shop's numbers\n"
        "  revenue     \u2014 opportunities the growth agents propose, to increase revenue\n"
        "  problems    \u2014 what is failing or losing money\n"
        "  performance \u2014 totals for a period: sales, orders, average order value, channels\n"
        "  products    \u2014 what is selling and what is in stock\n"
        "  customers   \u2014 who buys, and whether they come back\n"
        "  agents      \u2014 what the automated agents can and cannot do\n"
        "  none        \u2014 no report above answers this question\n\n"
        "Answer none unless the report would genuinely answer what was "
        "asked. A report on a related subject is not an answer: a question "
        "about money already spent is not answered by proposals to spend "
        "more, and a question about which single day sells best is not "
        "answered by a total for the week. none is correct far more often "
        "than it looks, and is always better than a report that misses the "
        "question.\n\n"
        f"Question: {text}"
    )
    try:
        reply = _client.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0, "num_predict": 40},
        )
        raw = (reply.get("message") or {}).get("content") or ""
    except Exception as exc:
        print(f"[advisor] model routing unavailable: {exc}", flush=True)
        return None

    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        choice = json.loads(match.group(0)).get("report")
    except Exception:
        return None
    # THREE OUTCOMES, AND THEY ARE NOT THE SAME.
    #
    #   a report name  the model says this report answers the question
    #   "none"         the model says no report does — a DECISION
    #   None           the model was not reachable, or improvised
    #
    # These used to collapse into two: `none` fell through the membership
    # test and came back as None, indistinguishable from Ollama being down.
    # That was harmless while the rules ran first and the model was a last
    # resort. It is not harmless now that the model routes, because the
    # caller has to know whether to fall back to the rules — and falling
    # back on a `none` would reinstate the mis-route the model just refused.
    if choice == "none":
        return "none"
    return choice if choice in ROUTES else None


# ── Helpers ──────────────────────────────────────────────────────────────

def _inr(paise) -> str:
    return f"₹{(int(paise or 0) / 100):,.2f}"


def _pct(value) -> str:
    if value is None:
        return "—"
    return f"{'+' if value >= 0 else ''}{value}%"


def _numbers(window: dict):
    from app.merchant import analytics
    return analytics.build(start_date=window["from"], end_date=window["to"])


def _metrics(rows):
    return {"kind": "metrics", "rows": rows}


def _table(title, columns, rows, note=""):
    return {"title": title, "kind": "table", "columns": columns,
            "rows": rows, "note": note}


# ── The reports ──────────────────────────────────────────────────────────

def _report(text: str, window: dict) -> dict:
    """
    The full structured breakdown — the answer to "give me a detailed report".

    Sections in the order a shop owner reads them: the headline, where it
    came from, what it was made of, what moved it, and what is not in it.
    """
    numbers = _numbers(window)
    kpis = {k["key"]: k for k in numbers["kpis"]}
    growth = _growth_state()

    sections = [{
        "title": f"Headline — {window['label']}",
        "note": (f"{numbers['window']['from']} to {numbers['window']['to']}, "
                 f"against {numbers['compare']['from']} to "
                 f"{numbers['compare']['to']} — the window immediately before "
                 f"it, of equal length."),
        **_metrics([
            {"label": "Total sales", "value": _inr(kpis["total_sales"]["value"]),
             "delta": _pct(kpis["total_sales"]["delta_pct"])},
            {"label": "Orders", "value": str(kpis["orders"]["value"]),
             "delta": _pct(kpis["orders"]["delta_pct"])},
            {"label": "Average order value", "value": _inr(kpis["aov"]["value"]),
             "delta": _pct(kpis["aov"]["delta_pct"])},
            {"label": "Returning customers",
             "value": ("—" if kpis["returning"]["value"] is None
                       else f"{kpis['returning']['value']}%"),
             "delta": "—", "note": kpis["returning"].get("note", "")},
        ]),
    }]

    if numbers["by_channel"]:
        sections.append(_table(
            "Where it came from",
            ["Channel", "Value", "Share"],
            [[c["label"], _inr(c["value"]), f"{c['pct']}%"]
             for c in numbers["by_channel"]],
            "This shop has four ways in and they are all real routes.",
        ))

    sections.append(_table(
        "What the total is made of",
        ["Line", "Value", "Change"],
        [[b["label"], _inr(b["value"]), _pct(b["delta_pct"])]
         for b in numbers["breakdown"]],
        "Taxes and return fees are absent rather than zero: this shop charges "
        "neither, and a zero row would say tax was computed and came to "
        "nothing, which is a different statement.",
    ))

    if numbers["by_product"]:
        sections.append(_table(
            "What sold",
            ["Product", "Value", "Units"],
            [[p["label"], _inr(p["value"]), str(p["units"])]
             for p in numbers["by_product"]],
        ))

    sections.append(_table(
        "What the agents did to margin",
        ["Measure", "Value"],
        [["Proposals waiting", str(growth["waiting"])],
         ["Refused by the gate", str(growth["blocked"])],
         ["Applied", str(growth["applied"])],
         # Committed and redeemed, not "given away": an offer nobody has
         # taken has cost the merchant nothing yet.
         ["Margin committed to live offers", _inr(growth["spent"])],
         ["Margin actually redeemed", _inr(growth["redeemed"])],
         ["Revenue traced back to an action", _inr(growth["attributed"])]],
        growth["caveat"],
    ))

    direction = kpis["total_sales"]["delta_pct"]
    summary = (
        f"{window['label'].capitalize()}: {_inr(kpis['total_sales']['value'])} "
        f"in total sales across {kpis['orders']['value']} orders"
        + (f", {'up' if direction >= 0 else 'down'} {abs(direction)}% on the "
           f"window before it." if direction is not None else
           ", with nothing in the window before it to compare against.")
    )

    return {
        "intent": "report",
        "summary": summary,
        "sections": sections,
        "findings": [],
        "actions": [],
        "limits": numbers["notes"] + [
            "Every figure is computed from this shop's own records. Nothing "
            "in this report was written by a language model.",
        ],
        "links": [{"label": "Open analytics", "to": "/merchant"}],
    }


def _growth_state() -> dict:
    from app.growth import attribution, registry
    try:
        proposals = registry.scan()
    except Exception:
        proposals = []
    try:
        traced = attribution.build(days=30)
    except Exception:
        traced = {}
    return {
        "waiting": sum(1 for p in proposals if p["verdict"] == "escalated"),
        "blocked": sum(1 for p in proposals if p["verdict"] == "blocked"),
        "proposals": len(proposals),
        "applied": traced.get("actions_applied", 0),
        "spent": traced.get("margin_spent_paise", 0),
        "redeemed": traced.get("margin_redeemed_paise", 0),
        "attributed": traced.get("attributed_revenue_paise", 0),
        "caveat": traced.get("caveat", ""),
    }


def _revenue(text: str, window: dict) -> dict:
    from app.growth import graph, registry
    try:
        proposals = registry.scan()
    except Exception:
        proposals = []
    picture = graph.build()
    numbers = _numbers(window)

    observed = picture["basis_counts"]["co_purchase"]
    costed = [p for p in proposals if p["cost_paise"] > 0]
    free = [p for p in proposals if p["cost_paise"] == 0]
    blocked = [p for p in proposals if p["verdict"] == "blocked"]

    findings = []
    if observed:
        findings.append({
            "headline": f"{observed} product pair"
                        f"{'' if observed == 1 else 's'} bought together",
            "detail": ("Cross-sell and bundle proposals built on these stand "
                       "on observed orders rather than category adjacency."),
            "evidence": f"{picture['orders_read']} order records read",
            "strength": "observed",
        })
    else:
        findings.append({
            "headline": "No two products have ever been bought together here",
            "detail": (f"Across {picture['orders_read']} order records, not "
                       f"one contains two of this store's products. That rules "
                       f"out the obvious play — a cross-sell learned from real "
                       f"baskets — because there are no real baskets to learn "
                       f"from."),
            "evidence": (f"{picture['orders_read']} orders, "
                         f"{picture['basis_counts']['category_adjacency']} "
                         f"adjacency edges, 0 observed"),
            "strength": "observed",
        })

    unpaid = next((n for n in numbers["notes"] if "never paid" in n), None)
    if unpaid:
        findings.append({
            "headline": "Orders are being created and not paid",
            "detail": (f"{unpaid} Recovering an order that already exists is "
                       f"cheaper than creating a new one."),
            "evidence": f"order records, {window['label']}",
            "strength": "observed",
        })

    return {
        "intent": "revenue",
        "summary": (
            f"I ran {len(proposals)} proposal"
            f"{'' if len(proposals) == 1 else 's'} from five growth agents "
            f"against this store's own orders. {len(costed)} would cost margin "
            f"— {_inr(sum(p['cost_paise'] for p in costed))} in total — and "
            f"{len(free)} {'costs' if len(free) == 1 else 'cost'} nothing."
            if proposals else
            "I ran every growth agent against this store's own orders and none "
            "found an action worth proposing. That is a real answer rather "
            "than a failure: there is not yet enough history to justify "
            "spending margin on anything."),
        "sections": [],
        "findings": findings,
        "actions": [{
            "headline": p["headline"], "detail": p["detail"],
            "cost_paise": p["cost_paise"], "agent": p["agent"],
            "verdict": p["verdict"], "verdict_reason": p["verdict_reason"],
            "evidence_note": p["evidence_note"], "sample_size": p["sample_size"],
        } for p in (costed + free)[:6]],
        "limits": [
            "No expected-return figure is attached to any of these. This shop "
            "has no conversion history to project from, so a number like "
            "'expected +₹42,000' would be arithmetic on an assumption.",
            "Ranking is by cost and evidence, not by predicted lift.",
        ] + ([f"{len(blocked)} cannot be applied at all right now — growth "
              f"agents are switched off."] if blocked else []),
        "links": [{"label": "Review the queue", "to": "/merchant/growth/agents"},
                  {"label": "See the evidence", "to": "/merchant/growth/relationships"}],
    }


def _performance(text: str, window: dict) -> dict:
    numbers = _numbers(window)
    kpis = {k["key"]: k for k in numbers["kpis"]}
    sections = [{
        "title": f"Sales — {window['label']}",
        "note": (f"Against {numbers['compare']['from']} to "
                 f"{numbers['compare']['to']}."),
        **_metrics([
            {"label": "Total sales", "value": _inr(kpis["total_sales"]["value"]),
             "delta": _pct(kpis["total_sales"]["delta_pct"])},
            {"label": "Orders", "value": str(kpis["orders"]["value"]),
             "delta": _pct(kpis["orders"]["delta_pct"])},
            {"label": "Average order value", "value": _inr(kpis["aov"]["value"]),
             "delta": _pct(kpis["aov"]["delta_pct"])},
        ]),
    }]
    if numbers["by_channel"]:
        sections.append(_table(
            "By channel", ["Channel", "Value", "Share"],
            [[c["label"], _inr(c["value"]), f"{c['pct']}%"]
             for c in numbers["by_channel"]]))
    return {
        "intent": "performance",
        "summary": (f"Over {window['label']}: "
                    f"{_inr(kpis['total_sales']['value'])} in total sales "
                    f"across {kpis['orders']['value']} orders."),
        "sections": sections, "findings": [], "actions": [],
        "limits": numbers["notes"],
        "links": [{"label": "Open analytics", "to": "/merchant"}],
    }


def _problems(text: str, window: dict) -> dict:
    numbers = _numbers(window)
    payments = numbers["payments"]
    rows = [["Captured", str(payments["captured"])],
            ["Failed", str(payments["failed"])],
            ["Refused as unverifiable", str(payments["refused_unverifiable"])]]
    sections = [_table(
        "Payments", ["Outcome", "Count"], rows,
        "A payment refused as unverifiable is the store declining to mark an "
        "order paid on an id Razorpay would not confirm. That is a refusal "
        "working, not a fault.")]

    findings = [{
        "headline": note.split(".")[0] + ".", "detail": note,
        "evidence": "order records", "strength": "observed",
    } for note in numbers["notes"] if "never paid" in note
        or "settled through Razorpay for real" in note]

    try:
        from app.firebase_client import db
        open_failures = [d.to_dict() or {} for d in
                         db.collection("failed_purchases").stream()
                         if (d.to_dict() or {}).get("state") == "open"]
    except Exception:
        open_failures = []
    if open_failures:
        sections.append(_table(
            "Purchases waiting to be recovered",
            ["Item", "Amount", "Why"],
            [[f.get("product", {}).get("name", "—"),
              _inr(f.get("amount_paise")),
              (f.get("summary") or "")[:90]] for f in open_failures[:6]]))

    return {
        "intent": "problems",
        "summary": ("Here is where this shop is losing money or refusing to "
                    "take it." if findings or open_failures else
                    "Nothing is currently failing that the records show."),
        "sections": sections, "findings": findings, "actions": [],
        "limits": ["This reads the decision log and the order records. A "
                   "failure that was never logged is invisible to it."],
        "links": [{"label": "Failure recovery", "to": "/recovery"},
                  {"label": "Audit trail", "to": "/audit"}],
    }


def _products(text: str, window: dict) -> dict:
    from app.merchant import store
    numbers = _numbers(window)
    catalogue = store.list_products()
    active = [p for p in catalogue if (p.get("status") or "active") == "active"]
    out_of_stock = [p for p in active if int(p.get("stock") or 0) <= 0]

    sections = []
    if numbers["by_product"]:
        sections.append(_table(
            f"Sold — {window['label']}", ["Product", "Value", "Units"],
            [[p["label"], _inr(p["value"]), str(p["units"])]
             for p in numbers["by_product"]]))
    sections.append(_table(
        "Catalogue", ["Product", "Price", "Stock", "Status"],
        [[p["name"], _inr(p.get("price_paise")), str(p.get("stock") or 0),
          (p.get("status") or "active")] for p in catalogue],
        "A draft is invisible to a buying agent and is refused with a 409 if "
        "one tries to buy it."))

    return {
        "intent": "products",
        "summary": (f"{len(active)} of {len(catalogue)} products are published "
                    f"and {len(numbers['by_product'])} sold in "
                    f"{window['label']}."
                    + (f" {len(out_of_stock)} active product"
                       f"{'' if len(out_of_stock) == 1 else 's'} out of stock."
                       if out_of_stock else "")),
        "sections": sections, "findings": [], "actions": [],
        "limits": [f"Sales cover {window['label']} only."],
        "links": [{"label": "Manage catalogue", "to": "/merchant/products"}],
    }


def _customers(text: str, window: dict) -> dict:
    numbers = _numbers(window)
    cohorts = numbers["cohorts"]
    sized = [r for r in cohorts["rows"] if r["size"]]
    sections = [_table(
        "Cohorts", ["First bought", "Customers", "Months tracked"],
        [[r["label"], str(r["size"]), str(len(r["cells"]))] for r in sized]
        or [["—", "0", "0"]],
        cohorts["note"])]
    return {
        "intent": "customers",
        "summary": (f"This shop has {cohorts['customers']} paying customer"
                    f"{'' if cohorts['customers'] == 1 else 's'}."
                    + (" Any rate computed over that is one person's decision, "
                       "not a trend." if cohorts["customers"] < 5 else "")),
        "sections": sections, "findings": [], "actions": [],
        "limits": ["Retention needs months of history and more than a handful "
                   "of customers before a percentage means anything."],
        "links": [{"label": "Cohort analysis", "to": "/merchant"}],
    }


def _agents(text: str, window: dict) -> dict:
    from app.growth import registry
    described = registry.describe()
    return {
        "intent": "agents",
        "summary": (f"{len(described)} growth agents are registered. "
                    f"{sum(1 for a in described if a['spends_margin'])} can "
                    f"give away margin, and every one of those passes the same "
                    f"gate before anything is applied."),
        "sections": [_table(
            "Registered agents", ["Agent", "Spends margin", "What it does"],
            [[a["name"], "yes" if a["spends_margin"] else "no", a["what"]]
             for a in described])],
        "findings": [], "actions": [],
        "limits": [
            "An agent proposes; it never applies. Applying happens in one "
            "place, after the gate, so there is one thing to audit.",
            "None of them can contact a customer. There is no email or SMS "
            "rail in this build.",
        ],
        "links": [{"label": "The queue", "to": "/merchant/growth/agents"}],
    }


def _compare(text: str, window: dict) -> dict:
    """
    This month against last month, over the SAME NUMBER OF DAYS.

    Four days of September against thirty-one of August is the oldest
    flattering comparison in commerce reporting, and it is always available
    to anyone who wants their numbers to look like a collapse or a boom.
    So the earlier window is trimmed to the same length as the elapsed part
    of this month, and the report says so in its own note rather than
    leaving the reader to check.

    `window` is ignored on purpose. `parse_window` reads the FIRST period
    phrase it finds, so "compare this month to last month" resolves to
    "last month" and the report would have compared August with July —
    answering a question nobody asked. A month-over-month report defines
    its own two windows.
    """
    from datetime import date, timedelta

    from app.merchant import analytics

    today = date.today()
    start_this = today.replace(day=1)
    elapsed = (today - start_this).days + 1

    end_prev_month = start_this - timedelta(days=1)
    start_prev = end_prev_month.replace(day=1)
    # Never past the end of the shorter month: comparing 31 elapsed days
    # against a 30-day month would silently shorten the earlier window.
    end_prev = min(start_prev + timedelta(days=elapsed - 1), end_prev_month)

    now = analytics.build(start_date=start_this.isoformat(),
                          end_date=today.isoformat())
    before = analytics.build(start_date=start_prev.isoformat(),
                             end_date=end_prev.isoformat())

    now_k = {k["key"]: k for k in now["kpis"]}
    before_k = {k["key"]: k for k in before["kpis"]}

    def shown(kpi):
        if kpi is None:
            return "—"
        unit, value = kpi.get("unit"), kpi.get("value")
        if unit == "paise":
            return _inr(value)
        if unit == "percent":
            return f"{value:.1f}%"
        return f"{int(value or 0):,}"

    def moved(key):
        a = (now_k.get(key) or {}).get("value")
        b = (before_k.get(key) or {}).get("value")
        # The same rule analytics uses: growth from nothing is not a
        # percentage, and printing one is the most common lie on a
        # dashboard. An em dash is the honest answer.
        if not b:
            return "—"
        pct = round(((a - b) / b) * 100, 1)
        return f"{pct:+.1f}%"

    rows = [[k["label"], shown(now_k.get(k["key"])),
             shown(before_k.get(k["key"])), moved(k["key"])]
            for k in now["kpis"]]

    this_label = f"{start_this.isoformat()} to {today.isoformat()}"
    prev_label = f"{start_prev.isoformat()} to {end_prev.isoformat()}"

    total_now = (now_k.get("total_sales") or {}).get("value") or 0
    total_before = (before_k.get("total_sales") or {}).get("value") or 0
    if not total_before:
        headline = (f"This month so far: {_inr(total_now)}. There is nothing "
                    f"in the same span of last month to compare it against, "
                    f"so no change is reported.")
    else:
        direction = "up" if total_now > total_before else (
            "down" if total_now < total_before else "level with")
        pct = abs(round(((total_now - total_before) / total_before) * 100, 1))
        headline = (f"This month so far: {_inr(total_now)} against "
                    f"{_inr(total_before)} over the same {elapsed} day"
                    f"{'' if elapsed == 1 else 's'} of last month — "
                    + (f"{direction} it." if direction == "level with"
                       else f"{direction} {pct}%."))

    limits = []
    if elapsed < 7:
        limits.append(
            f"Only {elapsed} day{'' if elapsed == 1 else 's'} of this month "
            f"have happened. A span this short moves on single orders, so "
            f"the percentages are arithmetic rather than a trend.")
    if not total_before:
        limits.append(
            "The matching span of last month holds no paid orders, so every "
            "change reads as a dash. A percentage against zero would be a "
            "larger number, not a truer one.")

    return {
        "intent": "compare",
        "summary": headline,
        "sections": [_table(
            f"This month against last — {elapsed} day"
            f"{'' if elapsed == 1 else 's'} each",
            ["Metric", "This month", "Last month", "Change"],
            rows,
            note=(f"{this_label} against {prev_label}. Equal spans, so the "
                  f"comparison is not flattered by a longer earlier month."),
        )],
        "findings": [],
        "actions": [],
        "limits": limits,
    }


def _discounts(text: str, window: dict) -> dict:
    """
    What the growth agents have cost, which is not the same as what they
    have given away.

    This existed as two figures inside the full report and had no route of
    its own, so "how much did I spend on discounts?" — a question the shop
    can answer exactly — came back as "I could not tell". Committed and
    redeemed are reported separately because they mean different things: an
    offer nobody has taken has cost the merchant nothing yet.
    """
    from app.growth import attribution
    days = max(1, int(window.get("days") or 30))
    try:
        traced = attribution.build(days=days)
    except Exception as exc:
        traced = {}
        print(f"[advisor] attribution unavailable: {exc}", flush=True)

    committed = int(traced.get("margin_spent_paise") or 0)
    redeemed = int(traced.get("margin_redeemed_paise") or 0)
    earned = int(traced.get("attributed_revenue_paise") or 0)
    conversions = traced.get("conversions") or []

    sections = [_metrics([
        {"label": "Margin committed to live offers", "value": _inr(committed)},
        {"label": "Margin actually redeemed", "value": _inr(redeemed)},
        {"label": "Revenue traced back to an offer", "value": _inr(earned)},
        {"label": "Offers taken", "value": str(len(conversions))},
    ])]
    if conversions:
        sections.append(_table(
            "Where the margin went",
            ["Kind", "Against", "Cost", "Revenue"],
            [[c.get("kind", ""), str(c.get("target_id", ""))[:28],
              _inr(c.get("cost_paise")), _inr(c.get("revenue_paise"))]
             for c in conversions[:20]],
            "Only offers attached to the thing that then sold are counted."))

    return {
        "intent": "discounts",
        "summary": (
            f"{_inr(committed)} of margin is committed to growth offers over "
            f"{window['label']}, and {_inr(redeemed)} of that has actually "
            f"been taken by a buyer."
            + (f" {_inr(earned)} of revenue is traceable to an offer."
               if earned else " No offer has converted yet.")),
        "sections": sections, "findings": [], "actions": [],
        "limits": [
            "Committed is what was approved and reserved against the daily "
            "budget. Redeemed is what a buyer actually took off a price. The "
            "difference is margin still standing behind offers nobody has "
            "used, and it is not a cost yet.",
            traced.get("caveat") or "",
        ],
        "links": [{"label": "Open attribution", "to": "/merchant/growth/attribution"}],
    }


def _conversion(text: str, window: dict) -> dict:
    """
    How many opened checkouts turned into money, in this shop's own records.

    Counted from checkout sessions rather than from page views, because
    this shop has no analytics beacon and a conversion rate over traffic it
    cannot see would be a number with no denominator behind it.
    """
    from app.merchant import store
    start, end = window["from"], window["to"]

    opened = paid = abandoned = 0
    paid_value = 0
    try:
        for doc in store.db.collection(store.SESSIONS).stream():
            row = doc.to_dict() or {}
            when = row.get("created_at")
            stamp = getattr(when, "isoformat", lambda: "")()[:10] or ""
            if stamp and not (start <= stamp <= end):
                continue
            opened += 1
            status = (row.get("status") or "")
            if status == "paid":
                paid += 1
                paid_value += int(row.get("total_paise") or 0)
            elif status in ("awaiting_payment", "open", "cancelled"):
                abandoned += 1
    except Exception as exc:
        return {
            "intent": "conversion",
            "summary": f"I could not read the checkout sessions: {exc}",
            "sections": [], "findings": [], "actions": [], "limits": [],
            "links": [],
        }

    # ORDERS THAT DID NOT COME THROUGH THIS SHOP'S CHECKOUT.
    #
    # Named rather than ignored. This shop's own sessions are one route in;
    # the agent console books orders through another. Reporting "0% of 3
    # checkouts" beside a dashboard showing three orders and ₹2,487 reads
    # as a contradiction, and a merchant is right to distrust both numbers
    # at that point. The honest version says which door it counted.
    elsewhere = 0
    try:
        numbers = _numbers(window)
        elsewhere = int((numbers.get("kpis_by_key") or {}).get("orders")
                        or next((k["value"] for k in numbers["kpis"]
                                 if k["key"] == "orders"), 0) or 0)
    except Exception:
        elsewhere = 0

    rate = (paid / opened * 100) if opened else None
    return {
        "intent": "conversion",
        "summary": (
            f"{paid} of {opened} checkout{'' if opened == 1 else 's'} opened "
            f"in this shop's own storefront in {window['label']} were paid — "
            f"{rate:.0f}%." if opened else
            f"No checkout was opened in this shop's own storefront in "
            f"{window['label']}, so there is no rate to compute. That is zero "
            f"activity, not a zero rate."),
        "sections": ([_metrics([
            {"label": "Checkouts opened", "value": str(opened)},
            {"label": "Paid", "value": str(paid)},
            {"label": "Left unpaid", "value": str(abandoned)},
            {"label": "Value of paid checkouts", "value": _inr(paid_value)},
        ])] if opened else []),
        "findings": [], "actions": [],
        "limits": [
            "This is checkout conversion — opened to paid. It is not a "
            "visit-to-order rate: this shop has no analytics on visits, and "
            "a percentage over traffic nobody measured would be invented.",
            (f"{elsewhere} order{'' if elsewhere == 1 else 's'} in this window "
             f"reached the shop through the agent console rather than through "
             f"its own checkout, and are not in this rate. They are in the "
             f"sales figures, which is why the two can look like they "
             f"disagree." if elsewhere else ""),
            ("With this few checkouts the percentage is a count, not a rate. "
             "One more sale moves it a long way."
             if opened and opened < 10 else ""),
        ],
        "links": [{"label": "Open orders", "to": "/merchant/orders"}],
    }


def _restock(text: str, window: dict) -> dict:
    """
    What is selling fast enough to run out, from units sold against stock held.

    "What should I stock more of?" used to route to the catalogue listing,
    which answered a different question with real numbers — the worst kind
    of wrong answer. Days of cover is the honest version: units sold in the
    window, divided into what is on the shelf.
    """
    from app.merchant import store
    numbers = _numbers(window)
    days = max(1, int(window.get("days") or 30))
    sold = {row["label"]: row for row in (numbers["by_product"] or [])}

    rows = []
    for product in store.list_products():
        if (product.get("status") or "active") != "active":
            continue
        units = int((sold.get(product["name"]) or {}).get("units") or 0)
        stock = int(product.get("stock") or 0)
        per_day = units / days
        cover = (stock / per_day) if per_day else None
        rows.append({"name": product["name"], "units": units, "stock": stock,
                     "cover": cover})

    # Anything selling at all, soonest to run out first. Products with no
    # sales are listed after, because "you have never sold one" is not a
    # restock signal however low the stock is.
    moving = sorted([r for r in rows if r["units"]],
                    key=lambda r: (r["cover"] if r["cover"] is not None else 1e9))
    still = [r for r in rows if not r["units"]]

    sections = []
    if moving:
        sections.append(_table(
            f"Selling — {window['label']}",
            ["Product", "Units sold", "In stock", "Days of cover"],
            [[r["name"], str(r["units"]), str(r["stock"]),
              ("—" if r["cover"] is None else f"{r['cover']:.0f}")]
             for r in moving],
            "Days of cover is stock divided by the rate it sold at in this "
            "window. It assumes the next weeks look like the last ones, "
            "which on this few orders is an assumption, not a forecast."))
    if still:
        sections.append(_table(
            "Not sold in this window", ["Product", "In stock"],
            [[r["name"], str(r["stock"])] for r in still],
            "No sales means no rate, so there is nothing to project. These "
            "are listed so the picture is complete, not as a recommendation."))

    urgent = [r for r in moving if r["cover"] is not None and r["cover"] < 30]
    return {
        "intent": "restock",
        "summary": (
            (f"{urgent[0]['name']} is the closest to running out — "
             f"{urgent[0]['stock']} left, about {urgent[0]['cover']:.0f} days "
             f"at the rate it sold in {window['label']}."
             if urgent else
             f"{len(moving)} product{'' if len(moving) == 1 else 's'} sold in "
             f"{window['label']} and none is close to running out.")
            if moving else
            f"Nothing from this shop's own catalogue sold in "
            f"{window['label']}, so there is no rate to restock against. "
            f"Orders booked through the agent console against other venues "
            f"are not stock this shop holds."),
        "sections": sections, "findings": [], "actions": [],
        "limits": [
            "This is what sold against what is held. It cannot tell you what "
            "would have sold if it had been in stock, because a stock-out "
            "leaves no record of the sale that did not happen.",
            "Only this shop's own products are counted. An order the agent "
            "console placed at another venue consumed none of this shop's "
            "stock, so it cannot be a reason to reorder.",
        ],
        "links": [{"label": "Manage catalogue", "to": "/merchant/products"}],
    }


HANDLERS = {
    "discounts": _discounts,
    "conversion": _conversion,
    "restock": _restock,
    "compare": _compare,
    "report": _report, "revenue": _revenue, "performance": _performance,
    "problems": _problems, "products": _products, "customers": _customers,
    "agents": _agents,
}


def _product_row(product: dict) -> list:
    return [["Name", str(product.get("name"))],
            ["Price", _inr(product.get("price_paise"))],
            ["Stock", str(product.get("stock"))],
            ["Category", str(product.get("category") or "\u2014")],
            ["Status", str(product.get("status"))],
            ["Photo", "attached" if product.get("image") else "none"]]


def _rendered_add(result: dict) -> dict:
    product = result.get("product") or {}
    draft = (product.get("status") or "draft") != "active"
    return {
        "summary": (
            f"Added \"{product.get('name')}\" as a draft. It is in your "
            f"storefront now, and it stays out of the agent catalogue until "
            f"you publish it \u2014 so nothing can buy it by accident."
            if draft else
            f"Added \"{product.get('name')}\" and published it. It is in the "
            f"UCP catalogue now, so a buying agent can find and check it out."),
        "sections": [_table(
            "What I added", ["Field", "Value"], _product_row(product),
            note=("Written to the store and to the decision log."
                  + (" Publish it from Storefront when you are happy with it."
                     if draft else ""))),
        ],
        "limits": ([
            "It is a draft. A buying agent cannot discover or check out a "
            "draft, so publishing is the step that makes it sellable and "
            "that step is yours."
        ] if draft else [
            "It is active, because you asked for it to be. It is buyable now."
        ]),
        "links": [{"label": "Open the storefront", "to": "/merchant/products"}],
    }


def _rendered_update(result: dict) -> dict:
    product = result.get("product") or {}
    changed = result.get("changed") or []
    if result.get("published"):
        headline = (f"Published \"{product.get('name')}\". It is in the UCP "
                    f"catalogue now, so a buying agent can discover and check "
                    f"it out.")
    elif result.get("unpublished"):
        headline = (f"Moved \"{product.get('name')}\" back to draft. It has "
                    f"left the UCP catalogue and can no longer be bought.")
    elif changed:
        headline = (f"Updated \"{product.get('name')}\": "
                    f"{', '.join(changed)}.")
    else:
        headline = (f"\"{product.get('name')}\" already had those values, so "
                    f"nothing changed.")
    return {
        "summary": headline,
        "sections": [_table("Where it stands now", ["Field", "Value"],
                            _product_row(product),
                            note="Written to the store and to the decision log.")],
        "limits": ([
            "A published product is reachable by any buying agent that can "
            "see this shop. Nothing else about it changed."
        ] if result.get("published") else []),
        "links": [{"label": "Open the storefront", "to": "/merchant/products"}],
    }


def _rendered_remove(result: dict) -> dict:
    product = result.get("product") or {}
    retired = result.get("retired") or []
    return {
        "summary": (f"Removed \"{product.get('name')}\" from the catalogue."
                    + (f" Also retired: {', '.join(retired)}." if retired else "")),
        "sections": [],
        "limits": [
            "Past orders keep their own copy of the line, so nothing already "
            "sold or reported has changed. This cannot be undone from here \u2014 "
            "the product would have to be added again."
        ],
        "links": [{"label": "Open the storefront", "to": "/merchant/products"}],
    }


RENDERERS = {
    "add_product": _rendered_add,
    "update_product": _rendered_update,
    "remove_product": _rendered_remove,
}


def _still_collecting(action: str, slots: dict, summary: str,
                      extra: list | None = None) -> dict:
    """One reply shape for every 'I need more from you' answer."""
    return {
        "intent": f"action:{action}",
        "summary": summary,
        "sections": [], "findings": [], "actions": [],
        "limits": (extra or []) + ["Nothing has been changed in your store yet."],
        "pending": {"action": action, "slots": slots},
    }


def act(text: str, image: str | None = None, pending: dict | None = None) -> dict:
    """
    Perform something on the merchant's account, or ask for what is missing.

    Returns None when the merchant was not asking for an action, so `ask`
    falls through to the reports exactly as before.

    THE UNFINISHED ACTION TRAVELS WITH THE CONVERSATION.
    `pending` is what the agent was already collecting, handed back by the
    client and merged with whatever the merchant has now said. Keeping it
    there rather than in a server-side session means the half-built product
    is visible in the payload, dies with the tab, and cannot be resumed by
    anyone else — which is the right lifetime for a thing that is about to
    change a real shop.

    FOUR STEPS, AND EACH ONE CAN STOP AND ASK.

        resolve   which product is this about, if the action needs one
        collect   the required fields, asked for by name
        ready     anything else the action needs before it can run
        confirm   for the one action that cannot be taken back

    Every one of them returns the same shape, carrying `pending`, so the
    conversation continues from where it stopped rather than restarting.
    """
    from app.merchant import actions

    action = (pending or {}).get("action") or actions.detect(text)
    if not action or action not in actions.ACTIONS:
        return None

    spec = actions.ACTIONS[action]
    slots = dict((pending or {}).get("slots") or {})
    slots.update(spec["parse"](text, image))

    # ── 1. Which product ─────────────────────────────────────────────────
    if spec.get("resolves_product") and not slots.get("product_id"):
        # A pending action already knows its product, so the merchant's
        # answer to "which one?" is resolved against the catalogue rather
        # than against the original sentence.
        found = actions.resolve_product(text)
        if found.get("error"):
            return _still_collecting(action, slots, found["error"])
        if found.get("choices"):
            names = [c["name"] for c in found["choices"]]
            return _still_collecting(
                action, slots,
                "Which one did you mean? " + "; ".join(names),
                ["I will not guess between them — the wrong one would be the "
                 "wrong product changed."])
        product = found["product"]
        slots["product_id"] = product["id"]
        slots["_product_name"] = product["name"]

    # ── 2. Required fields ───────────────────────────────────────────────
    missing = actions.missing_fields(action, slots)
    if missing:
        field = missing[0]
        prompts = spec.get("prompts", {})
        known = [f for f in (spec["required"] + spec["optional"])
                 if slots.get(f) and not f.startswith("_")]
        return _still_collecting(
            action, slots, prompts.get(field, f"I need the {field} first."),
            (["I have " + ", ".join(known) + " so far."] if known else []))

    # ── 3. Anything else the action needs ────────────────────────────────
    ready = spec.get("ready")
    if ready:
        blocker = ready(slots)
        if blocker:
            return _still_collecting(action, slots, blocker)

    # ── 4. Confirmation, for the action that cannot be undone ────────────
    if spec.get("confirm_required") and not slots.get("_confirmed"):
        if _DECLINED_RE.match((text or "").strip()):
            # Dropped entirely, `pending` cleared. Re-asking after a no is
            # how a confirmation turns into pestering, and a merchant who
            # has to say no twice will start saying yes to get past it.
            name = slots.get("_product_name") or "that product"
            return {
                "intent": f"action:{action}",
                "summary": f"Left \"{name}\" alone.",
                "sections": [], "findings": [], "actions": [],
                "limits": ["Nothing was changed."],
                "pending": None,
            }
        if _AGREED_RE.match((text or "").strip()):
            slots["_confirmed"] = True
        else:
            name = slots.get("_product_name") or "that product"
            return _still_collecting(
                action, slots,
                f"Remove \"{name}\" from the catalogue? Say yes and I will.",
                ["Past orders keep their own copy of the line, so nothing "
                 "already sold or reported would change. Any promotion or "
                 "growth offer pointing at it is retired with it."])

    result = spec["execute"](slots)
    if not result.get("ok"):
        return {
            "intent": f"action:{action}",
            "summary": f"I could not {spec['label']}: {result.get('error')}",
            "sections": [], "findings": [], "actions": [],
            "limits": ["Nothing was changed."],
            # The slots are kept but the confirmation is not: a refused
            # deletion must be agreed to again, not retried on the strength
            # of a yes the merchant gave to a different attempt.
            "pending": {"action": action,
                        "slots": {k: v for k, v in slots.items()
                                  if k != "_confirmed"}},
        }

    rendered = (RENDERERS.get(action) or (lambda r: {"summary": "Done."}))(result)
    return {
        "intent": f"action:{action}",
        "findings": [], "actions": [],
        "sections": [], "limits": [], "links": [],
        **rendered,
        "pending": None,
    }


# What counts as agreement to something irreversible. Deliberately short:
# "yes, but change the price first" is not a yes, and anything that is not
# plainly agreement falls through and asks again.
_AGREED_RE = re.compile(
    r"^(yes|yep|yeah|yup|ok|okay|sure|confirm(ed)?|do it|go ahead|"
    r"remove it|delete it|please do)\b[\s.!]*$", re.I)

# And what counts as refusing. Equally short, and it wins over agreement:
# "no, don't" contains neither a yes nor an ambiguity worth resolving.
_DECLINED_RE = re.compile(
    r"^(no|nope|nah|don'?t|do not|cancel|stop|leave it|keep it|"
    r"never\s?mind|nevermind|forget it)\b.*$", re.I)


def ask(text: str, image: str | None = None, pending: dict | None = None) -> dict:
    """One merchant question, answered from real records."""
    performed = act(text, image=image, pending=pending)
    if performed is not None:
        return {"question": text, "window": parse_window(text),
                "routed_by": "action", "suggestions": CAN_ANSWER, **performed}

    window = parse_window(text)

    # THE MODEL ROUTES FIRST, AND THE RULES ARE THE FALLBACK.
    #
    # This was the other way round, and the careful part never ran. The
    # rules match on single common nouns — "sell", "product", "stock",
    # "revenue" — and returned the FIRST hit, so every question containing
    # one was answered before the model was consulted at all. The prompt
    # written to say "answer none unless the report genuinely answers this"
    # only ever saw questions the rules had already given up on, which are
    # the ones it can help with least.
    #
    # Measured, on this shop: "what should I stock more of?" was answered
    # with a catalogue listing; "am I growing or shrinking?" with a list of
    # growth proposals; "which product should I raise the price of?" with a
    # count of published products. Each was a confident answer, carrying
    # real computed figures, to a question nobody asked — which is exactly
    # the failure the model gate exists to prevent and was structurally
    # prevented from preventing.
    #
    # So the order is inverted. The model decides whether a report answers
    # the question; the rules decide when the model cannot be reached. A
    # model that says `none` has made a decision and it stands — falling
    # back to the rules there would reinstate the mis-route it just refused.
    # WHICH RULES ARE ALLOWED TO OVERRULE A `none`.
    #
    # Making the model's refusal absolute fixed the mis-routes and broke
    # something else: "give me a detailed report of revenue growth this
    # week" — a sentence out of this agent's own suggestion list — came
    # back as "I could not tell", because a 7B model decided a full
    # breakdown did not specifically answer "revenue growth". A refusal
    # that noisy cannot be the last word on its own.
    #
    # The split is between patterns that name their own subject and
    # patterns that match a single common noun. "Discounts", "conversion",
    # "restock", "compare" and "report" only fire on words that mean one
    # thing in a shop, and every mis-route measured came from the other
    # three: `products` matching "sell", `performance` matching "sales",
    # `revenue` matching "growing". So the specific patterns overrule a
    # `none`; the generic ones defer to it, which is exactly where the
    # model's judgement was worth having.
    intent, routed_by = None, "model"
    verdict = route_with_model(text)
    if verdict and verdict != "none":
        intent = verdict
    elif verdict == "none":
        by_rule = classify(text)
        if by_rule in TRUSTED_RULES:
            intent, routed_by = by_rule, "rules-over-model"
        else:
            intent = "unknown"
    else:
        # The model could not be reached at all. Rules alone, and said so.
        intent, routed_by = classify(text), "rules"

    handler = HANDLERS.get(intent)
    if not handler:
        return {
            "question": text, "intent": "unknown", "window": window,
            "routed_by": routed_by,
            "summary": ("I could not tell which part of the shop you were "
                        "asking about. I answer from this shop's own records "
                        "rather than from a language model, which makes me "
                        "accurate and narrow — I will not improvise an answer "
                        "I cannot compute."),
            "sections": [], "findings": [], "actions": [], "limits": [],
            "suggestions": CAN_ANSWER, "links": [],
        }

    # A QUESTION CAN ASK FOR TWO THINGS.
    #
    # "…and what can be done to increase revenue" is a second request, not
    # decoration on the first. The primary report still leads — that is
    # what was asked for first — but the opportunities the growth agents
    # found are attached to it rather than thrown away. Only the actions
    # are merged, not a whole second report: two summaries stapled together
    # read as a machine that could not decide, and the actions are the part
    # that answers "what can be done".
    also_wants_actions = ("revenue" in classify_all(text)
                          and intent not in ("revenue", "unknown"))

    try:
        answer = handler(text, window)
    except Exception as exc:
        print(f"[advisor] {intent} failed: {exc}", flush=True)
        return {
            "question": text, "intent": intent, "window": window,
            "routed_by": routed_by,
            "summary": f"I could not complete that analysis: {exc}",
            "sections": [], "findings": [], "actions": [], "limits": [],
            "links": [],
        }

    if also_wants_actions and not answer.get("actions"):
        try:
            opportunities = _revenue(text, window)
        except Exception as exc:
            print(f"[advisor] could not attach opportunities: {exc}", flush=True)
        else:
            actions = opportunities.get("actions") or []
            if actions:
                answer["actions"] = actions
                # Say where they came from. A reader who asked for a report
                # should not have to wonder why it grew an action list.
                answer["summary"] = (
                    f"{answer.get('summary', '').rstrip()} "
                    f"You also asked what could be done about it, so the "
                    f"growth agents' current proposals are below."
                ).strip()
            else:
                answer.setdefault("limits", []).append(
                    "You asked what could be done to increase revenue. The "
                    "growth agents found nothing worth proposing against "
                    "this shop's records right now, which is a real answer "
                    "rather than an omission.")

    return {"question": text, "window": window, "routed_by": routed_by,
            "suggestions": CAN_ANSWER, **answer}
