"""
WHAT THE TWO ENGINES SAY TO EACH OTHER.

The reference architecture is a loop: a GenAI layer works out what somebody
needs, a recommendation system decides which products actually answer it
using behavioural data, and the GenAI explains the result. The value is in
the separation — the model never picks the product, so it cannot invent
one — and a separation only holds if there is something concrete at the
boundary.

That is what this file is. Three structures, and the rule that goes with
each:

  NeedSpec      what the GenAI produces. Words, constraints, and where each
                one came from. No products, no prices, no claims about the
                market — it describes a need, not an answer.

  Candidate     what the marketplace produced, plus every signal measured
                about it. Facts only.

  Ranked        what the RecSys decided, with the evidence that decided it.
                Ordered, scored, and carrying the reason as data rather
                than as a sentence.

Two properties are deliberate.

`NeedSpec` carries `source` on its fields, so a value read from a person's
own words is distinguishable from one a model inferred. The budget defence
in this project rests on exactly that distinction: a ceiling read by rule
cannot be talked upwards by a listing, and this makes that visible at the
boundary rather than buried in the parser.

`Ranked` carries `basis` and `signals`, not prose. The sentence a person
reads is generated afterwards from these fields, which means an explanation
can be checked against the decision instead of being trusted alongside it.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Protocol

Priority = Literal["value", "price", "rating", "discount", "delivery_days"]
Bias = Literal["neutral", "best", "cheapest"]
Source = Literal["typed", "inferred", "history", "default", "predicted"]


@dataclass
class Constraint:
    """One requirement, and who is responsible for it."""
    field: str
    value: Any
    source: Source
    note: str = ""


@dataclass
class NeedSpec:
    """
    The GenAI layer's output. A need, never an answer.

    Deliberately incapable of naming a product: there is no `product_id`
    and no `recommendation` field, so a model that wanted to pick something
    has nowhere to put it. That is the architectural version of the rule
    this project already enforces by convention.
    """
    query: str
    category: str = ""
    max_price_paise: int = 0
    budget_stated: bool = False
    priority: Priority = "value"
    bias: Bias = "neutral"
    requirements: list[str] = field(default_factory=list)
    condition_ids: set[str] = field(default_factory=set)
    constraints: list[Constraint] = field(default_factory=list)
    # Set when the need was predicted rather than asked for — the Level 5
    # entry point. Carries the evidence so the RecSys and the audit trail
    # can see what triggered a purchase nobody requested.
    predicted: dict | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        out["condition_ids"] = sorted(self.condition_ids)
        return out


@dataclass
class Ranked:
    """
    The decision layer's output: an ordered list and why.

    `basis` is the evidence in the order it counted, `signals` the measured
    facts behind it. Both are data. The sentence comes later and is built
    from these, so it can be checked rather than believed.
    """
    candidates: list[dict]
    chosen: dict | None
    basis: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    confidence: str = "unknown"
    considered: int = 0
    dropped: dict = field(default_factory=dict)
    stages: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Explanation:
    """The sentence, and the facts it was built from."""
    text: str
    facts: list[str] = field(default_factory=list)
    written_by: str = "deterministic"


class Understanding(Protocol):
    """The GenAI half. Swappable: anything that turns words into a need."""

    name: str

    def understand(self, text: str, *, predicted: dict | None = None) -> NeedSpec:
        ...


class RecSys(Protocol):
    """
    The decision half. Swappable: anything that turns a need into a ranked
    answer using behavioural data.
    """

    name: str

    def rank(self, need: NeedSpec, candidates: list[dict]) -> Ranked:
        ...


class Explainer(Protocol):
    """
    The write-up. Separate from both, because who phrases the answer and
    who decides it are different questions — and only one of them may be a
    language model.
    """

    name: str

    def explain(self, need: NeedSpec, ranked: Ranked) -> Explanation:
        ...
