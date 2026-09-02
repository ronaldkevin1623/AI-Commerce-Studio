"""
THE DECISION HALF: which of these actually answers the need?

No language model is called anywhere in this file, and that is the design
rather than an omission. Two attempts to have one rank listings are on the
record in this project: a keep/reject prompt threw out an iPhone 12 as
"wrong type" and left one listing out of twenty-three, and a 0-5 scoring
prompt returned all zeros. What replaced them — anchored screens, Bayesian
shrinkage over seller feedback, banded quality scoring, a verified
superlative check — is what this class runs.

The stages, in order, and each one either removes candidates or measures
them. None of them is a preference expressed to a model:

    relevance   does the title answer the request at all
    accessory   is this a thing FOR the product rather than the product
    condition   is it the condition that was asked for
    trust       price outliers, thin sellers, risky condition strings
    precision   can it actually be bought — stock, and the signals with it
    quality     score it from reviews, seller record, condition
    rank        order by the need's priority, then the precision tie-break

`stages` records what each one did, so the hand-off carries not just the
answer but the shape of the funnel that produced it — which is what makes
a decision auditable after the fact rather than merely repeatable.
"""
from app.agent import explain as explainer_rules
from app.agent import precision, quality
from app.agent.ollama_agent import (
    is_accessory_for, matches_request, query_terms, screen_relevance,
)
from app.agent.trust_agent import assess as trust_assess
from app.engines.contracts import NeedSpec, Ranked


class SignalRecSys:
    """Deterministic ranking over measured signals."""

    name = "signal-recsys"

    def __init__(self, enrich=None, shortlist: int = 8):
        # Injected so a test can run the whole engine without a network
        # call, and so a different enrichment source can be dropped in.
        self.enrich = enrich
        self.shortlist = shortlist

    def rank(self, need: NeedSpec, candidates: list[dict]) -> Ranked:
        stages: list[dict] = []
        dropped: dict[str, int] = {}

        def note(stage, before, after, detail=""):
            lost = before - after
            if lost:
                dropped[stage] = lost
            stages.append({"stage": stage, "in": before, "out": after,
                           "dropped": lost, "detail": detail})

        rows = list(candidates or [])
        started = len(rows)
        terms = query_terms(need.category or need.query)

        # ── accessory and relevance ──────────────────────────────────────
        before = len(rows)
        rows = [c for c in rows
                if not is_accessory_for(c.get("name") or "", need.query)
                and (not terms or matches_request(c.get("name") or "", terms)[0])]
        note("accessory_and_terms", before, len(rows),
             "Things sold FOR the product, and titles that do not answer it.")

        if rows:
            before = len(rows)
            screened = screen_relevance(rows, need.category or need.query,
                                        budget_paise=need.max_price_paise
                                        if need.budget_stated else 0)
            rows = screened["candidates"]
            note("relevance", before, len(rows), screened.get("summary", ""))

        # ── condition ────────────────────────────────────────────────────
        if need.condition_ids and rows:
            before = len(rows)
            rows = [c for c in rows
                    if str(c.get("condition_id") or "") in need.condition_ids
                    or (c.get("source") == "merchant" and "1000" in need.condition_ids)]
            note("condition", before, len(rows),
                 f"Kept only {', '.join(sorted(need.condition_ids))}.")

        # ── trust ────────────────────────────────────────────────────────
        if rows:
            before = len(rows)
            trust = trust_assess(rows)
            rows = [c for c in trust["candidates"]
                    if (c.get("trust") or {}).get("ok", True)]
            note("trust", before, len(rows), trust.get("summary", ""))

        # ── precision: the hard filter, before anything is scored ────────
        if rows:
            if self.enrich:
                rows = self.enrich(rows, self.shortlist)
            before = len(rows)
            screen = precision.screen(rows)
            rows = screen["candidates"]
            note("precision", before, len(rows), screen.get("summary", ""))

        if not rows:
            return Ranked(candidates=[], chosen=None, considered=started,
                          dropped=dropped, stages=stages,
                          basis=["Nothing survived the screens."])

        # ── score and order ──────────────────────────────────────────────
        quality.annotate(rows)
        budget = need.max_price_paise if need.budget_stated else 0
        rows.sort(key=lambda p: (quality.value_key(p, budget, need.bias),
                                 precision.preference_key(p)))

        decision = explainer_rules.choose(
            rows, need.priority, budget_paise=budget,
            requirements=need.requirements, user_text=need.query,
            bias=need.bias)
        chosen = decision.get("product") or rows[0]
        stages.append({"stage": "rank", "in": len(rows), "out": len(rows),
                       "dropped": 0,
                       "detail": f"Ordered by {need.priority}, then by stock, "
                                 f"approval and how many have sold."})

        assessment = chosen.get("quality") or {}
        return Ranked(
            candidates=rows,
            chosen=chosen,
            basis=assessment.get("basis") or [],
            signals={
                "quality_score": assessment.get("score"),
                "quality_confidence": assessment.get("confidence"),
                "precision": chosen.get("precision"),
                "precision_evidence": precision.explain(chosen),
                "price_paise": chosen.get("price_paise"),
                "seller_feedback": chosen.get("seller_feedback"),
                "seller_ratings": chosen.get("seller_feedback_count"),
                # The reason the deterministic explainer produced, carried
                # as a signal rather than as the answer — an explainer may
                # phrase it differently, but not contradict it.
                "reason": decision.get("reason"),
            },
            confidence=assessment.get("confidence", "unknown"),
            considered=started,
            dropped=dropped,
            stages=stages,
        )
