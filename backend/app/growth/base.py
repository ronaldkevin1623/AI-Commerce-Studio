"""
GROWTH AGENTS: THE MERCHANT SIDE OF THE SAME BAR.

The buying agent is bounded, gated and audited because it spends the
shopper's money. A growth agent spends the MERCHANT's — a discount is
margin given away, a placement bid is cash, a recovery offer is both — and
it is aimed at persuading someone. So it gets the same treatment, and for
the same reason: an agent that can move money is only useful if you can say
exactly what stops it.

That symmetry is the whole design. `risk_gate` stops the buyer overspending;
`growth.gate` stops the merchant over-discounting. Neither can approve its
own action, both write a decision either way, and both refuse rather than
guess when the evidence is thin.

    detect()   read real signals out of the datastore. No inputs invented.
    propose()  turn a signal into a bounded, priced Proposal.
    -> gate    the core decides. An agent never applies its own proposal.
    -> record  every outcome, including refusals, into the decision log.

WHAT A GROWTH AGENT MUST NOT DO

Act. `propose()` returns a description of an action and never performs one.
Applying is the core's job, after the gate, so there is exactly one place
where merchant money moves and exactly one place to audit.

ON THIN EVIDENCE

This build has one genuinely abandoned checkout, not a thousand. An agent
that reports "recovered 12% of carts" from a sample of one is lying with
arithmetic. Every Proposal therefore carries `sample_size` and
`evidence_note`, and the UI shows both — a recommendation from n=1 is
allowed, but it is never allowed to look like a trend.
"""
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Proposal:
    """
    One bounded action a growth agent wants taken, and why.

    Deliberately inert. It carries what would happen and what it would
    cost; nothing here changes anything until the gate has passed it.
    """

    agent: str                      # which growth agent produced it
    kind: str                       # recover_cart | test_discount | cross_sell
    headline: str                   # one line a merchant can judge on sight
    detail: str                     # the reasoning, in full

    # THE MONEY. `cost_paise` is what this gives away or spends if applied —
    # margin on a discount, budget on a placement. Zero is a legitimate
    # answer and means the action is free to the merchant.
    cost_paise: int = 0

    # What it is aimed at, so the audit trail names a specific thing rather
    # than "a customer".
    target_kind: str = ""           # checkout_session | product | order
    target_id: str = ""

    # HOW MUCH THIS IS ACTUALLY KNOWN. A proposal from a sample of one is
    # allowed; presenting it as a trend is not.
    sample_size: int = 0
    evidence_note: str = ""

    # Filled by the gate, never by the agent.
    verdict: str = ""               # allowed | escalated | blocked
    verdict_reason: str = ""

    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent": self.agent, "kind": self.kind,
            "headline": self.headline, "detail": self.detail,
            "cost_paise": self.cost_paise,
            "target_kind": self.target_kind, "target_id": self.target_id,
            "sample_size": self.sample_size,
            "evidence_note": self.evidence_note,
            "verdict": self.verdict, "verdict_reason": self.verdict_reason,
            "params": self.params,
        }


@runtime_checkable
class GrowthAgent(Protocol):
    """
    One way of growing merchant revenue.

    Small on purpose, and split so that reading a signal, deciding what to
    do about it, and doing it are three separate steps owned by three
    different pieces of code.
    """

    agent_id: str
    name: str
    what: str                       # what it does, in a sentence, for the UI

    # Whether this agent can give away money. False means it can only
    # rearrange what is already shown — a cross-sell suggestion costs the
    # merchant nothing, a discount costs margin.
    spends_margin: bool

    def detect(self) -> list[dict]:
        """Real signals from the datastore. Never fabricated inputs."""
        ...

    def propose(self, signals: list[dict]) -> list[Proposal]:
        """Turn signals into bounded proposals. Performs nothing."""
        ...
