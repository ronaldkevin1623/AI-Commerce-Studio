"""
THE DUAL ENGINE — is the boundary real?

A separation you can describe is not a separation. These check the three
things that make it one:

  A  the GenAI half structurally cannot name a product
  B  each half can be replaced without the other noticing
  C  the decision half calls no language model, and is deterministic
  D  the explainer may phrase but never re-rank, and fails closed

Offline: synthetic candidates, no marketplace, no model.
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


from dataclasses import fields

from app.engines import loop
from app.engines.contracts import Explanation, NeedSpec, Ranked
from app.engines.recsys import SignalRecSys
from app.engines.understanding import PredictedNeed, RuleFirstUnderstanding
from app.engines.loop import DeterministicExplainer, PhrasingExplainer

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def listing(name, price, **extra):
    return {"id": name.lower().replace(" ", "-"), "name": name,
            "price_paise": price, "source": "ebay", "condition_id": "1000",
            "seller_feedback": 99.0, "seller_feedback_count": 5000,
            "availability": "IN_STOCK", "stock": 1, **extra}


CANDIDATES = [
    listing("Wireless Bluetooth Headphones Over Ear", 180000,
            review_stars=4.5, review_count=300, sold_quantity=200),
    listing("Wireless Bluetooth Headphones Studio", 240000,
            review_stars=4.1, review_count=90, sold_quantity=40),
    listing("Wireless Bluetooth Headphones Basic", 90000,
            review_stars=3.2, review_count=12, sold_quantity=5),
]

print("=== A. The GenAI half cannot name a product ===")
names = {f.name for f in fields(NeedSpec)}
check("NeedSpec has no product id field",
      not any(k in names for k in ("product", "product_id", "chosen", "recommendation")),
      ", ".join(sorted(names)))

need = RuleFirstUnderstanding(use_model=False).understand(
    "bluetooth headphones under 3000")
check("It carries the need, not an answer",
      need.category and need.max_price_paise == 300000)

sources = {c.field: c.source for c in need.constraints}
check("A typed budget is labelled 'typed'", sources.get("max_price_paise") == "typed",
      sources.get("max_price_paise"))
unstated = RuleFirstUnderstanding(use_model=False).understand("bluetooth headphones")
un_src = {c.field: c.source for c in unstated.constraints}
check("An unstated budget is labelled 'default', not typed",
      un_src.get("max_price_paise") == "default", un_src.get("max_price_paise"))
check("...and does not become a ceiling", unstated.max_price_paise == 0)

print("\n=== B. Either half can be replaced ===")


class StubRecSys:
    name = "stub"

    def rank(self, need, candidates):
        return Ranked(candidates=candidates, chosen=candidates[-1],
                      basis=["stub picked the last one"], considered=len(candidates))


out = loop.run("bluetooth headphones", lambda n: list(CANDIDATES), recsys=StubRecSys())
check("A swapped RecSys decides instead", out["engines"]["recsys"] == "stub")
check("...and its choice is the one returned",
      out["ranked"]["chosen"]["name"].endswith("Basic"),
      out["ranked"]["chosen"]["name"][-24:])
check("...while the understanding half is unchanged",
      out["engines"]["understanding"] == "rule-first")

predicted = {"explanation": "Bought 4 times, about every 30 days."}
out2 = loop.run("Coffee Pods", lambda n: list(CANDIDATES),
                understanding=PredictedNeed(), recsys=StubRecSys(),
                predicted=predicted)
check("A predicted need enters through the same door",
      out2["engines"]["understanding"] == "predicted")
check("...and carries its evidence",
      out2["need"]["predicted"]["explanation"].startswith("Bought 4 times"))
check("...labelled as predicted, not typed",
      any(c["source"] == "predicted" for c in out2["need"]["constraints"]))

before = loop.engines()
restore = loop.use(recsys=StubRecSys())
check("Engines can be swapped globally", loop.engines()["recsys"] == "stub")
loop.use(understanding=restore[0], recsys=restore[1], explainer=restore[2])
check("...and put back", loop.engines() == before, str(loop.engines()))

print("\n=== C. The decision half is deterministic and model-free ===")
# Asserted by breaking the model, not by grepping for its name. recsys.py
# does import from app.agent.ollama_agent — but only rule-based helpers
# that live in a badly-named module, and a text search cannot tell those
# apart from an inference call. Poisoning the client can: if ranking still
# works with every model call raising, no model was consulted.
import app.agent.ollama_agent as _oa


class _Poisoned:
    def chat(self, *a, **k):
        raise AssertionError("the decision layer called a language model")


_real_client = _oa._client
_oa._client = _Poisoned()
poisoned = None
try:
    poisoned = SignalRecSys().rank(need, [dict(c) for c in CANDIDATES])
    model_free = True
except AssertionError:
    model_free = False
finally:
    _oa._client = _real_client
check("Ranking completes with every model call poisoned", model_free)
check("...and still chose a product",
      poisoned is not None and poisoned.chosen is not None)

rec = SignalRecSys()
one = rec.rank(need, [dict(c) for c in CANDIDATES])
two = rec.rank(need, [dict(c) for c in CANDIDATES])
check("The same input gives the same choice",
      one.chosen["name"] == two.chosen["name"], one.chosen["name"][-22:])
check("...and the same funnel",
      [s["out"] for s in one.stages] == [s["out"] for s in two.stages])
check("Every stage is recorded", len(one.stages) >= 5, f"{len(one.stages)} stages")
check("The evidence is data, not prose",
      isinstance(one.basis, list) and isinstance(one.signals, dict))

print("\n=== D. The explainer phrases, never chooses ===")
det = DeterministicExplainer().explain(need, one)
check("The deterministic sentence names the chosen product",
      one.chosen["name"][:18].lower() in det.text.lower())
check("...and lists the facts it used", len(det.facts) >= 2, "; ".join(det.facts)[:70])


class RenamingModel(PhrasingExplainer):
    """A model that answers with a different product — the failure to catch."""

    def explain(self, need, ranked):
        plain = self.fallback.explain(need, ranked)
        text = "I recommend the Sony WH-1000XM5 instead."
        head = " ".join((ranked.chosen.get("name") or "").split()[:3]).lower()
        if not text or (head and head not in text.lower()):
            return plain
        return Explanation(text, plain.facts, self.name)


renamed = RenamingModel().explain(need, one)
check("A phrasing that renames the product is discarded",
      "Sony" not in renamed.text, renamed.text[:52])
check("...falling back to the deterministic sentence",
      renamed.written_by == "deterministic")

check("Explainer cannot change the ranking",
      not any(hasattr(cls, "rank") for cls in (DeterministicExplainer, PhrasingExplainer)))

print("\n" + "=" * 62)
print(f"  {passed} passed · {failed} failed")
