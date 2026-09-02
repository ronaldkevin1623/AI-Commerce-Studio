"""
THE LOOP, AND THE SOCKETS THE ENGINES PLUG INTO.

    understand  →  fetch  →  rank  →  explain

Each arrow carries one of the typed structures, and each box is swappable
at run time. `use(understanding=..., recsys=...)` replaces either half
without the other knowing, which is the test of whether a boundary is real:
the autonomous path already runs a different understanding engine from the
interactive one and nothing downstream changed.

ON THE EXPLAIN STEP, AND WHERE THIS DEPARTS FROM THE REFERENCE

The architecture slide has the GenAI "explain & re-rank product
recommendations". This implements the explaining and refuses the re-ranking,
which is a deliberate departure and worth stating plainly.

Re-ranking would hand the final say back to the model the separation exists
to keep away from it. Everything the RecSys measured — shrunk seller
feedback, banded quality, verified superlatives — could be silently
overturned by a model that liked a different title, and nothing downstream
could tell. The whole argument for two engines is that the second one
decides; a re-rank puts the first one back in charge at the last moment.

So the explainer may phrase, never choose. `DeterministicExplainer` is the
default and builds the sentence from `Ranked.signals`. `PhrasingExplainer`
lets a model write it, and is bounded twice: it is given only the facts the
RecSys supplied, and its output is discarded if it names a product that is
not the chosen one. A model that hallucinates in that slot fails closed to
the deterministic sentence rather than reaching a person.
"""
from app.agent import explain as explainer_rules
from app.engines.contracts import Explanation, NeedSpec, Ranked
from app.engines.recsys import SignalRecSys
from app.engines.understanding import RuleFirstUnderstanding


class DeterministicExplainer:
    """
    The sentence, built from the signals rather than from the listing.

    Every clause traces to a measured value, which is why it can carry a
    superlative at all: the claim is checked against the candidate set
    before it is uttered.
    """

    name = "deterministic"

    def explain(self, need: NeedSpec, ranked: Ranked) -> Explanation:
        if not ranked.chosen:
            return Explanation("Nothing here answers that.", [], self.name)

        facts = []
        signals = ranked.signals or {}
        if signals.get("quality_score") is not None:
            facts.append(f"quality {signals['quality_score']} "
                         f"({signals.get('quality_confidence')} confidence)")
        if signals.get("precision_evidence"):
            facts.append(signals["precision_evidence"])
        if signals.get("seller_feedback") is not None:
            facts.append(f"seller {signals['seller_feedback']}% over "
                         f"{signals.get('seller_ratings') or 0:,} ratings")
        facts.append(f"chosen from {ranked.considered} considered")

        reason = signals.get("reason") or ", ".join(ranked.basis)
        name = ranked.chosen.get("name") or "this listing"
        return Explanation(f"{name} — {reason}", facts, self.name)


class PhrasingExplainer:
    """
    A model writes the sentence, over facts it was handed.

    Given no listings, no market and no choice — only the chosen product's
    name and the signals behind it — so there is nothing for it to pick
    between. If it returns something that does not mention the chosen
    product, the deterministic sentence is used instead: a phrasing step
    that quietly renamed the product would be worse than no phrasing step.
    """

    name = "model-phrasing"

    def __init__(self, fallback=None):
        self.fallback = fallback or DeterministicExplainer()

    def explain(self, need: NeedSpec, ranked: Ranked) -> Explanation:
        plain = self.fallback.explain(need, ranked)
        if not ranked.chosen:
            return plain

        try:
            from app.agent.ollama_agent import _client, OLLAMA_MODEL
            name = ranked.chosen.get("name") or ""
            prompt = (
                "Write one short sentence telling a shopper why this product "
                "was chosen. Use ONLY the facts listed. Do not add features, "
                "prices or claims that are not here. Do not suggest a "
                "different product.\n\n"
                f"Product: {name}\n"
                f"Facts: {'; '.join(plain.facts)}\n"
                f"They asked for: {need.query}\n\nSentence:")
            reply = _client.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0, "num_predict": 60},
            )
            text = (reply["message"]["content"] or "").strip()
        except Exception:
            return plain

        # The guard. A phrasing that lost the product is not a phrasing.
        head = " ".join((ranked.chosen.get("name") or "").split()[:3]).lower()
        if not text or (head and head not in text.lower()):
            return plain
        return Explanation(text, plain.facts, self.name)


# The sockets. Module-level so a caller can swap an engine for a request or
# for a test without threading an object through every layer.
_understanding = RuleFirstUnderstanding()
_recsys = SignalRecSys()
_explainer = DeterministicExplainer()


def use(*, understanding=None, recsys=None, explainer=None):
    """Swap either half. Returns what was there, so a test can put it back."""
    global _understanding, _recsys, _explainer
    previous = (_understanding, _recsys, _explainer)
    if understanding is not None:
        _understanding = understanding
    if recsys is not None:
        _recsys = recsys
    if explainer is not None:
        _explainer = explainer
    return previous


def engines() -> dict:
    """Which implementations are currently plugged in."""
    return {"understanding": _understanding.name, "recsys": _recsys.name,
            "explainer": _explainer.name}


def run(text: str, fetch, *, predicted: dict | None = None,
        understanding=None, recsys=None, explainer=None) -> dict:
    """
    One pass of the loop, with every hand-off returned.

    `fetch` is a callable taking the NeedSpec and returning candidates, so
    the loop does not know or care which marketplace it is talking to —
    which is the seam Step 5's adapters plug into.
    """
    understanding = understanding or _understanding
    recsys = recsys or _recsys
    explainer = explainer or _explainer

    need = understanding.understand(text, predicted=predicted)
    candidates = fetch(need) or []
    ranked = recsys.rank(need, candidates)
    written = explainer.explain(need, ranked)

    return {
        "engines": {"understanding": understanding.name,
                    "recsys": recsys.name, "explainer": explainer.name},
        "need": need.to_dict(),
        "fetched": len(candidates),
        "ranked": ranked.to_dict(),
        "explanation": {"text": written.text, "facts": written.facts,
                        "written_by": written.written_by},
    }
