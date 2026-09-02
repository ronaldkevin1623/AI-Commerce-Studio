"""
Does every dial on the hive actually change behaviour?

For each setting: flip it, call the real agent function, and check the
output differs. Uses synthetic candidate data where a live search isn't
needed — that's a test fixture, not product output.
"""
import os
import sys
from pathlib import Path

# The backend package, found from this file rather than from where the
# runner happened to be invoked — so a suite works the same whether it is
# run on its own, through run_all.py, or from any directory.
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
# The app resolves serviceAccountKey.json and the .env relative to the
# working directory, so a suite has to stand where the server stands. Doing
# it here rather than in the runner keeps every suite runnable on its own.
os.chdir(BACKEND)
sys.stdout.reconfigure(encoding="utf-8")

from app.agent import settings
from app.agent import trust_agent, budget_agent, risk_gate

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, condition, detail):
    results.append((PASS if condition else FAIL, name, detail))


def set_to(node, key, value):
    settings.apply({node: {key: value}})


CANDIDATES = [
    {"id": "a", "price_paise": 500000, "seller_feedback": 99.0, "condition": "New"},
    {"id": "b", "price_paise": 480000, "seller_feedback": 98.0, "condition": "New"},
    {"id": "c", "price_paise": 520000, "seller_feedback": 85.0, "condition": "New"},
    {"id": "d", "price_paise": 150000, "seller_feedback": 99.0, "condition": "New"},
    {"id": "e", "price_paise": 300000, "seller_feedback": 92.0, "condition": "New"},
]


def fresh():
    return [dict(c) for c in CANDIDATES]


# ── trust.outlier_floor_pct ──────────────────────────────────────────────
set_to("trust", "outlier_floor_pct", 45)
set_to("trust", "min_seller_feedback", 0)
strict = trust_agent.assess(fresh())["flagged"]
set_to("trust", "outlier_floor_pct", 10)
loose = trust_agent.assess(fresh())["flagged"]
check("trust.outlier_floor_pct", strict != loose,
      f"flagged {strict} at 45% vs {loose} at 10%")

# ── trust.min_seller_feedback ────────────────────────────────────────────
set_to("trust", "outlier_floor_pct", 0)
set_to("trust", "min_seller_feedback", 90)
at90 = trust_agent.assess(fresh())["flagged"]
set_to("trust", "min_seller_feedback", 80)
at80 = trust_agent.assess(fresh())["flagged"]
check("trust.min_seller_feedback", at90 != at80,
      f"flagged {at90} at 90% vs {at80} at 80%")

# ── budget.session_ceiling_inr ───────────────────────────────────────────
customer = {"total_spend_paise": 1000000}
set_to("budget", "session_ceiling_inr", 20000)
big = budget_agent.assess(customer, 500000)["status"]
set_to("budget", "session_ceiling_inr", 100)
small = budget_agent.assess(customer, 500000)["status"]
check("budget.session_ceiling_inr", big != small,
      f"'{big}' at Rs20000 ceiling vs '{small}' at Rs100")

# ── budget.warn_at_pct ───────────────────────────────────────────────────
set_to("budget", "session_ceiling_inr", 20000)
# Rs5,000 spent plus a Rs5,000 order against a Rs20,000 ceiling is a ratio
# of 0.5 — below 75% and above 10%, so the two settings must disagree. The
# previous fixture used Rs10,000 + Rs5,000, which lands on exactly 0.75:
# both thresholds fire, and the dial looks broken when it is the test
# standing on the boundary.
warn_customer = {"total_spend_paise": 500000}
set_to("budget", "warn_at_pct", 75)
w75 = budget_agent.assess(warn_customer, 500000)["status"]
set_to("budget", "warn_at_pct", 10)
w10 = budget_agent.assess(warn_customer, 500000)["status"]
check("budget.warn_at_pct", w75 != w10, f"'{w75}' at 75% vs '{w10}' at 10%")

# ── risk.auto_approve_limit_inr ──────────────────────────────────────────
cust = {"id": "audit-cust", "trust_score": 100}
product = {"id": "audit-prod", "price_paise": 400000, "stock": 5}
set_to("risk", "duplicate_window_seconds", 0)
set_to("risk", "auto_approve_limit_inr", 5000)
low = risk_gate.evaluate(cust, product)["decision"]
set_to("risk", "auto_approve_limit_inr", 100)
high = risk_gate.evaluate(cust, product)["decision"]
check("risk.auto_approve_limit_inr", low != high,
      f"'{low}' at Rs5000 limit vs '{high}' at Rs100")

# ── risk.min_trust_score ─────────────────────────────────────────────────
set_to("risk", "auto_approve_limit_inr", 5000)
shaky = {"id": "audit-cust2", "trust_score": 50}
set_to("risk", "min_trust_score", 40)
below = risk_gate.evaluate(shaky, product)["decision"]
set_to("risk", "min_trust_score", 60)
above = risk_gate.evaluate(shaky, product)["decision"]
check("risk.min_trust_score", below != above,
      f"'{below}' at min 40 vs '{above}' at min 60")

# ── risk.duplicate_window_seconds ────────────────────────────────────────
set_to("risk", "min_trust_score", 40)
set_to("risk", "duplicate_window_seconds", 60)
dup_cust = {"id": "audit-dup", "trust_score": 100}
dup_prod = {"id": "audit-dup-prod", "price_paise": 100000, "stock": 5}
first = risk_gate.evaluate(dup_cust, dup_prod)["decision"]
second = risk_gate.evaluate(dup_cust, dup_prod)["decision"]
set_to("risk", "duplicate_window_seconds", 0)
third = risk_gate.evaluate(dup_cust, dup_prod)["decision"]
check("risk.duplicate_window_seconds", second != third,
      f"repeat is '{second}' with a 60s window, '{third}' with 0s")

# ── ebay.usd_to_inr + scout.result_limit (real API) ──────────────────────
try:
    from app.agent.ebay_client import search_live_catalog
    set_to("scout", "result_limit", 4)
    set_to("ebay", "usd_to_inr", 83)
    few = search_live_catalog("wireless earbuds", 500000)
    set_to("scout", "result_limit", 12)
    many = search_live_catalog("wireless earbuds", 500000)
    check("scout.result_limit", len(few) <= 4 < len(many),
          f"{len(few)} listings at limit 4 vs {len(many)} at limit 12")

    set_to("ebay", "usd_to_inr", 166)
    doubled = search_live_catalog("wireless earbuds", 500000)
    cheap = min(p["price_paise"] for p in many) if many else 0
    dear = min(p["price_paise"] for p in doubled) if doubled else 0
    check("ebay.usd_to_inr", dear > cheap,
          f"cheapest Rs{cheap/100:.0f} at rate 83 vs Rs{dear/100:.0f} at 166")
except Exception as exc:
    check("scout.result_limit / ebay.usd_to_inr", False, f"live call failed: {exc}")

# ── ollama.temperature (is it actually sent?) ────────────────────────────
try:
    from app.agent import ollama_agent
    set_to("ollama", "temperature", 30)
    opts = ollama_agent._options()
    check("ollama.temperature", abs(opts["temperature"] - 0.30) < 1e-9,
          f"_options() -> {opts}")
except Exception as exc:
    check("ollama.temperature", False, str(exc))

# ── value.priority ───────────────────────────────────────────────────────
set_to("value", "priority", "auto")
auto = ollama_agent.effective_priority("rating")
set_to("value", "priority", "discount")
pinned = ollama_agent.effective_priority("rating")
check("value.priority", auto == "rating" and pinned == "discount",
      f"'rating' request -> '{auto}' on auto, '{pinned}' when pinned")

# ── negotiator.max_sentences / goal (prompt actually carries them?) ──────
try:
    from app.agent import negotiator_agent
    import unittest.mock as mock
    captured = {}

    def fake_chat(model, messages, options=None):
        captured["prompt"] = messages[0]["content"]
        return {"message": {"content": "drafted"}}

    with mock.patch.object(negotiator_agent._client, "chat", side_effect=fake_chat):
        set_to("negotiator", "max_sentences", 5)
        set_to("negotiator", "goal", "shipping")
        negotiator_agent.draft_message({"name": "X", "price_paise": 100000})
        p = captured["prompt"]
    check("negotiator.max_sentences", "5 sentences at most" in p,
          "prompt says '5 sentences at most'" if "5 sentences" in p else f"prompt tail: {p[-160:]}")
    check("negotiator.goal", "shipping cost" in p,
          "prompt carries the shipping ask" if "shipping cost" in p else f"prompt tail: {p[-160:]}")
except Exception as exc:
    check("negotiator.*", False, str(exc))

# ── intent.max_price_override_inr ────────────────────────────────────────
try:
    captured2 = {}

    def fake_chat2(model, messages, options=None):
        return {"message": {"content": '{"category":"x","max_price_paise":999,"priority":"price"}'}}

    with mock.patch.object(ollama_agent._client, "chat", side_effect=fake_chat2):
        set_to("intent", "max_price_override_inr", 0)
        no_override = ollama_agent.parse_intent("anything")["max_price_paise"]
        set_to("intent", "max_price_override_inr", 1500)
        with_override = ollama_agent.parse_intent("anything")["max_price_paise"]
    check("intent.max_price_override_inr", no_override == 999 and with_override == 150000,
          f"parsed {no_override} paise, overridden to {with_override}")
except Exception as exc:
    check("intent.max_price_override_inr", False, str(exc))

# ── trust.drop_flagged is consumed in the route, not the agent ───────────
import inspect
from app.routes import agent_routes
route_src = inspect.getsource(agent_routes)
check("trust.drop_flagged", 'settings.get("trust", "drop_flagged")' in route_src,
      "read in agent_routes before the trusted-only filter")

settings.reset()

print()
for status, name, detail in results:
    mark = "OK  " if status == PASS else "FAIL"
    print(f"[{mark}] {name:34} {detail}")
failed = [r for r in results if r[0] == FAIL]
print(f"\n{len(results) - len(failed)}/{len(results)} dials verified functional")
if failed:
    print("FAILING: " + ", ".join(r[1] for r in failed))
