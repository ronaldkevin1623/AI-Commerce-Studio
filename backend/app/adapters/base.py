"""
ONE SHAPE FOR EVERY PLACE THINGS CAN BE BOUGHT.

"End-to-end shopping experiences won't happen in only one platform" is the
reference deck's point, and the architectural consequence is that the agent
must not know which platform it is talking to. Before this, it did:
search_catalog called eBay by name, then the merchant by name, and adding a
third venue meant editing that function.

A venue is now anything that can answer four questions:

    who are you           name, and what KIND of entry point you are
    are you reachable     without which the run should skip you quietly
    what do you have      given a phrase, a ceiling and a condition
    can you be paid       which is a different question from having stock

That last pair is the distinction this project has to keep. eBay can be
searched but not settled with — the listings are real, payable through
Razorpay, and no seller is going to ship them. The UCP store can actually
be paid and will actually fulfil. Both are venues; only one is a shop. An
interface that flattened that difference would let the agent promise
delivery it cannot arrange, so `can_fulfil` is part of the contract rather
than a note in the UI.

Adapters return listings in the shape the pipeline already expects, and set
`source` themselves. Everything downstream — trust, precision, quality,
ranking, the risk gate, the mandate chain — treats them identically, which
is what makes a new venue a new file rather than a new code path.
"""
from typing import Literal, Protocol, runtime_checkable

# What kind of entry point this is. Named after how the deck describes the
# journey, so a reader can map an adapter to the diagram: a marketplace
# aggregates many sellers, a retailer sells its own stock, and the rest are
# the pathways GenAI added beside them.
VenueKind = Literal[
    "marketplace",      # eBay, Amazon, an aggregator
    "retailer",         # a brand's own store, first-party stock
    "retail_media",     # sponsored inventory inside a retailer
    "social",           # shoppable posts
    "in_store",         # local availability
    "genai_platform",   # another assistant exposing a catalogue
]


@runtime_checkable
class VenueAdapter(Protocol):
    """
    A place the agent can look for something to buy.

    Deliberately small. Everything an adapter needs to do is fetch and
    normalise; nothing about ranking, screening or paying belongs here,
    because those are the same wherever the listing came from — and an
    adapter that could influence them would be a way for a venue to
    advantage its own stock.
    """

    name: str
    kind: VenueKind
    # Whether an order placed here can actually be fulfilled. False is not
    # a defect: a venue worth searching is not always a venue worth paying.
    can_fulfil: bool

    def available(self) -> bool:
        """Is this venue configured and reachable enough to try?"""
        ...

    def search(self, query: str, *, max_price_paise: int = 0,
               condition_ids: set | None = None,
               requirements: list | None = None,
               sort: str | None = None) -> list[dict]:
        """Listings in the pipeline's shape, with `source` set."""
        ...


class AdapterResult:
    """
    What one venue returned, and what it cost to ask.

    Carried separately from the listings so a caller can report "eBay gave
    22, the store gave 3, the third venue timed out" — which is the honest
    version of a multi-channel search, rather than a single merged list
    that hides which channel was silent.
    """

    __slots__ = ("adapter", "kind", "listings", "error", "took_ms")

    def __init__(self, adapter: str, kind: str, listings: list[dict],
                 error: str | None = None, took_ms: int = 0):
        self.adapter = adapter
        self.kind = kind
        self.listings = listings
        self.error = error
        self.took_ms = took_ms

    def to_dict(self) -> dict:
        return {"adapter": self.adapter, "kind": self.kind,
                "count": len(self.listings), "error": self.error,
                "took_ms": self.took_ms}
