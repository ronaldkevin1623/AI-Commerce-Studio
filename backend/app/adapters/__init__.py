"""
Venues the agent can shop from, behind one interface.

Adding a channel is `register(MyAdapter())` — no edit to the search path,
no branch in the pipeline, no new word for the ranker to learn.
"""
from app.adapters.base import AdapterResult, VenueAdapter, VenueKind
from app.adapters.registry import (
    adapters, describe, register, search_all, unregister,
)

__all__ = ["AdapterResult", "VenueAdapter", "VenueKind",
           "adapters", "describe", "register", "search_all", "unregister"]
