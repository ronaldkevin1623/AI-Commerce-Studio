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

CAN_ANSWER = [
    "Give me a detailed report of revenue growth this week",
    "Find me an opportunity to increase revenue",
    "How is the shop doing this month?",
    "What is going wrong?",
    "Which products are selling?",
    "Who are my customers?",
]


def classify(text: str) -> str:
    blob = (text or "").lower()
    for intent, pattern in INTENTS:
        if re.search(pattern, blob):
            return intent
    return "unknown"


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

    prompt = (
        "You route a shop owner's question to one report. Reply with JSON "
        "only, of the form {\"report\": \"<name>\"}.\n\n"
        "Reports:\n"
        "  report      — a full structured breakdown of the shop's numbers\n"
        "  revenue     — opportunities to increase revenue\n"
        "  problems    — what is failing or losing money\n"
        "  performance — sales, orders, average order value, channels\n"
        "  products    — what is selling and what is in stock\n"
        "  customers   — who buys, and whether they come back\n"
        "  agents      — what the automated agents can and cannot do\n"
        "  none        — the question is not about this shop\n\n"
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
    # Only a name from the list is accepted. Anything else is the model
    # improvising, and improvisation is exactly what it is not here for.
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
         ["Margin given away", _inr(growth["spent"])],
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


HANDLERS = {
    "report": _report, "revenue": _revenue, "performance": _performance,
    "problems": _problems, "products": _products, "customers": _customers,
    "agents": _agents,
}


def ask(text: str) -> dict:
    """One merchant question, answered from real records."""
    window = parse_window(text)
    intent = classify(text)
    routed_by = "rules"

    if intent == "unknown":
        # The rules did not recognise it. The model gets one shot at mapping
        # it onto a report that exists — and cannot invent one.
        guess = route_with_model(text)
        if guess:
            intent, routed_by = guess, "model"

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

    return {"question": text, "window": window, "routed_by": routed_by,
            "suggestions": CAN_ANSWER, **answer}
