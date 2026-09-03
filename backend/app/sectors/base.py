"""
A SECTOR IS A PLACE COMMERCE HAPPENS, NOT A CATEGORY OF THING.

The adapter seam answered "where can this be bought". This answers a
question one level up: "what kind of buying is this at all". Earbuds and a
three-day trip are not two categories in one marketplace; they need
different fields from the person, different evidence to judge a candidate,
and — the part that actually forces a boundary — different notions of what
an answer even is. Products ranking picks ONE best row from a list. An
itinerary is a SET chosen jointly under time and money constraints. No
amount of relabelling turns the first into the second.

So the core loop stays sector-agnostic and calls into whichever Sector is
active:

    route → understand → search → evaluate → gate → purchase → record

and a Sector supplies the five things that differ:

    intent_schema        what has to be asked or inferred before searching
    adapters             where this sector's candidates come from
    evaluation_criteria  what "better" means here, named and weighted
    templates            the second-level `/` menu once this sector is picked
    assemble             OPTIONAL — how candidates combine into one answer

That last one is the honest reason this interface exists. Products has no
`assemble`: the best row is the answer. Trip must have one, because a
flight, a hotel and three meals are only an answer once they fit together.
A sector interface without it would have been a naming convention.

WHAT A SECTOR MUST NOT DO

Reach into the core. If sector logic starts appearing inside the ranking
or the gate, the boundary has failed and adding the third sector will mean
editing the engine again — which is the thing this is supposed to prevent.

Sector adapters are registered PER SECTOR, never in the global venue
registry. A flight in the results of a search for earbuds would be the
clearest possible sign this was done wrong.
"""
from typing import Any, Protocol, runtime_checkable


class IntentField:
    """
    One thing a sector needs to know before it can search.

    `required` is the interesting flag: a products search can proceed with
    nothing but a phrase, whereas a trip with no destination is not an
    under-specified search, it is not a search at all. The core uses this
    to decide whether to ask rather than guess.
    """

    __slots__ = ("name", "kind", "required", "prompt", "example")

    def __init__(self, name: str, kind: str, *, required: bool = False,
                 prompt: str = "", example: str = ""):
        self.name = name
        self.kind = kind                  # text | int | money | date | city | enum
        self.required = required
        self.prompt = prompt              # what to ask if it is missing
        self.example = example

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "required": self.required,
                "prompt": self.prompt, "example": self.example}


class Criterion:
    """
    One dimension a sector judges candidates on.

    Carried as data rather than buried in a scoring function so the UI can
    show what the agent weighed, and so two sectors can be compared without
    reading either implementation.
    """

    __slots__ = ("name", "weight", "direction", "detail")

    def __init__(self, name: str, weight: float, direction: str, detail: str = ""):
        self.name = name
        self.weight = weight
        self.direction = direction        # "higher_is_better" | "lower_is_better"
        self.detail = detail

    def to_dict(self) -> dict:
        return {"name": self.name, "weight": self.weight,
                "direction": self.direction, "detail": self.detail}


class Template:
    """An entry in the sector's own `/` sub-menu."""

    __slots__ = ("key", "label", "description", "text")

    def __init__(self, key: str, label: str, description: str, text: str):
        self.key = key
        self.label = label                # "/deal"
        self.description = description    # shown beside it in the menu
        self.text = text                  # what typing it inserts

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label,
                "description": self.description, "text": self.text}


@runtime_checkable
class Sector(Protocol):
    """
    A kind of commerce the agent can conduct.

    Deliberately small, and deliberately data-first: four of the five
    members are descriptions rather than behaviour, so the `/` picker, the
    audit trail and the intent classifier can all read a sector without
    executing it.
    """

    sector_id: str
    name: str
    icon: str
    description: str

    # Whether this sector can end in a real payment. False is not a defect
    # — it is the same distinction `can_fulfil` draws for venues, and it
    # must be visible rather than discovered at checkout.
    can_transact: bool

    def intent_schema(self) -> list[IntentField]:
        """What must be known before a search is worth running."""
        ...

    def adapters(self) -> list:
        """This sector's providers. Never the global venue registry."""
        ...

    def evaluation_criteria(self) -> list[Criterion]:
        """What 'better' means here."""
        ...

    def templates(self) -> list[Template]:
        """The second-level menu shown once this sector is chosen."""
        ...

    def classify(self, text: str) -> float:
        """
        How strongly this sector claims a piece of free text, 0.0–1.0.

        Each sector scores its own claim rather than one central classifier
        holding a map of every sector's vocabulary — that map is exactly
        the thing that would need editing every time a sector is added.
        """
        ...


class SectorResult:
    """
    What a sector run produced, in a shape the core can gate and record
    without knowing which sector it came from.

    `legs` is why this exists. A products answer has one leg and its total
    is its price. A trip has several, and the spend cap has to see the sum
    — the single most likely place for a multi-sector system to charge
    someone for a flight and then quietly not count the hotel.
    """

    __slots__ = ("sector_id", "legs", "total_paise", "narrative",
                 "criteria", "warnings", "payable_leg", "steps", "date_note")

    def __init__(self, sector_id: str, legs: list[dict], *,
                 narrative: str = "", criteria: list | None = None,
                 warnings: list | None = None, payable_leg: dict | None = None,
                 steps: list | None = None, date_note: str = ""):
        self.sector_id = sector_id
        self.legs = legs
        # Summed here, once, so no caller can forget to. Every leg carries
        # its own price and the total is never asserted separately.
        self.total_paise = sum(int(leg.get("price_paise") or 0) for leg in legs)
        self.narrative = narrative
        self.criteria = criteria or []
        self.warnings = warnings or []
        # The one leg, if any, that can end in a real charge.
        self.payable_leg = payable_leg
        # How the answer was arrived at, step by step. Carried on the
        # result rather than logged and forgotten, so the UI can show the
        # funnel the same way a product search shows its screens.
        self.steps = steps or []
        self.date_note = date_note

    def to_dict(self) -> dict:
        return {
            "sector_id": self.sector_id,
            "legs": self.legs,
            "total_paise": self.total_paise,
            "narrative": self.narrative,
            "criteria": [c.to_dict() if hasattr(c, "to_dict") else c
                         for c in self.criteria],
            "warnings": self.warnings,
            "payable_leg": self.payable_leg,
            "steps": self.steps,
            "date_note": self.date_note,
        }
