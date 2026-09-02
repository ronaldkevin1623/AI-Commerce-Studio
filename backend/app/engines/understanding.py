"""
THE GENAI HALF: what does this person need?

Wraps the intent parsing this project already does, and puts a typed
boundary around it. Nothing about the parsing changes — the point is that
what comes out is now a `NeedSpec`, which has no field capable of naming a
product.

The division inside it is the one this project arrived at the hard way. The
rules read the budget, the search phrase and the condition, because a
red-team probe showed a sentence in a listing could talk the model into
signing a ₹5,000 ceiling over a typed ₹1,000 one. The model contributes the
fuller reading of requirements — what the person actually wants the thing
to do — which is the part rules are bad at and a model is good at.

So `source` on each constraint is not decoration. "typed" means it came
from the person's own words by rule and cannot be moved by anything a
seller wrote. "inferred" means the model suggested it. A reader of the
audit trail can tell which is which, which is the whole reason the field
exists.
"""
from app.agent.ollama_agent import (
    condition_preference, fast_intent, merge_model_intent, parse_intent,
)
from app.engines.contracts import Constraint, NeedSpec


class RuleFirstUnderstanding:
    """
    Rules for anything that bounds money; the model for everything else.

    `use_model=False` makes it entirely deterministic, which is what the
    autonomous path uses: an unattended run has no person waiting, so it
    gains nothing from a slower reading, and the fewer moving parts between
    a prediction and a purchase the better.
    """

    name = "rule-first"

    def __init__(self, use_model: bool = True):
        self.use_model = use_model

    def understand(self, text: str, *, predicted: dict | None = None) -> NeedSpec:
        intent = fast_intent(text)
        constraints = [
            Constraint("max_price_paise", intent["max_price_paise"],
                       "typed" if intent.get("budget_stated") else "default",
                       intent.get("budget_source", "")),
            Constraint("category", intent["category"], "typed",
                       "The request with the shopping instructions removed."),
            Constraint("priority", intent["priority"], "typed",
                       "Read from the wording by rule."),
        ]

        if self.use_model:
            try:
                # The model's reading is merged for requirements only. It is
                # not allowed near the budget — that is the defence, not a
                # preference.
                parsed = parse_intent(text)
                intent = merge_model_intent(intent, parsed)
                if intent.get("requirements"):
                    constraints.append(
                        Constraint("requirements", intent["requirements"],
                                   "inferred",
                                   "The model's reading of what the thing must do."))
            except Exception as exc:
                constraints.append(
                    Constraint("requirements", [], "default",
                               f"The model did not answer ({type(exc).__name__}); "
                               f"the rules stand alone."))

        wanted = condition_preference(text)
        constraints.append(
            Constraint("condition", wanted["label"],
                       "typed" if wanted["stated"] else "default",
                       "New unless the person said otherwise."))

        return NeedSpec(
            query=text,
            category=intent["category"],
            max_price_paise=intent["max_price_paise"] if intent.get("budget_stated") else 0,
            budget_stated=bool(intent.get("budget_stated")),
            priority=intent["priority"],
            bias=(intent.get("quality_bias") or "neutral"),
            requirements=intent.get("requirements") or [],
            condition_ids=set(wanted["allow"]),
            constraints=constraints,
            predicted=predicted,
        )


class PredictedNeed:
    """
    The Level 5 entry point: a need nobody typed.

    The replenishment model produces a prediction; this turns it into the
    same `NeedSpec` a person's sentence would produce, so everything
    downstream cannot tell — and does not need to — whether the need was
    asked for or foreseen. The evidence rides along in `predicted` so the
    audit trail can say why a purchase happened with nobody present.
    """

    name = "predicted"

    def understand(self, text: str, *, predicted: dict | None = None) -> NeedSpec:
        base = RuleFirstUnderstanding(use_model=False).understand(text)
        base.predicted = predicted
        base.constraints.append(
            Constraint("trigger", "replenishment", "predicted",
                       (predicted or {}).get("explanation")
                       or "Predicted from purchase history."))
        return base
