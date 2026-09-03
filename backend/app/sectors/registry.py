"""
THE SECTOR REGISTRY, AND THE ROUTE INTO ONE.

Adding a sector is `register(MySector())`. Nothing else: no edit to the
core loop, no branch in the pipeline, and — the part that is easy to get
wrong and easy to check — no change to the front end, because the `/`
picker reads this list rather than holding its own copy.

CHOOSING A SECTOR FROM FREE TEXT

Someone who types "wireless earbuds under 2000" has not picked a sector,
and defaulting to products would be right today and wrong the moment a
third sector exists. So each sector scores its own claim on the text and
the strongest wins — but only if it wins clearly. A close call is not
resolved by picking the higher number; it is resolved by asking, because
running an entire pipeline against the wrong sector is a much worse
outcome than one extra question.

The margin is deliberately not a single threshold. A sector can be
confident in absolute terms and still be nearly tied with another, and
both failures matter: "nothing claims this" and "two things claim it
equally" need different answers.
"""
from app.sectors.base import Sector

_SECTORS: list = []

# A sector must beat this to be chosen at all. Below it, nothing on the
# page understood the request well enough to act on it.
MIN_CONFIDENCE = 0.30
# ...and must beat the runner-up by this much. Two sectors within a
# whisker of each other is a genuine ambiguity, not a narrow win.
MIN_MARGIN = 0.15


def register(sector, *, replace: bool = False) -> None:
    existing = next((s for s in _SECTORS if s.sector_id == sector.sector_id), None)
    if existing:
        if not replace:
            raise ValueError(f"A sector with id {sector.sector_id!r} is registered.")
        _SECTORS.remove(existing)
    _SECTORS.append(sector)


def unregister(sector_id: str) -> bool:
    for sector in list(_SECTORS):
        if sector.sector_id == sector_id:
            _SECTORS.remove(sector)
            return True
    return False


def sectors() -> list:
    return list(_SECTORS)


def get(sector_id: str):
    return next((s for s in _SECTORS if s.sector_id == sector_id), None)


def describe() -> list[dict]:
    """Everything the `/` picker needs, straight from the registry."""
    out = []
    for sector in _SECTORS:
        out.append({
            "sector_id": sector.sector_id,
            "name": sector.name,
            "icon": sector.icon,
            "description": sector.description,
            "can_transact": sector.can_transact,
            "label": f"/{sector.sector_id}",
            "templates": [t.to_dict() for t in sector.templates()],
            "intent_schema": [f.to_dict() for f in sector.intent_schema()],
            "criteria": [c.to_dict() for c in sector.evaluation_criteria()],
        })
    return out


def classify(text: str) -> dict:
    """
    Which sector does this free text belong to?

    Returns the decision AND the losing scores. The audit trail records
    both, because "why did my trip request run as a product search" is
    only answerable afterwards if the runner-up was written down at the
    time.
    """
    scores = {}
    for sector in _SECTORS:
        try:
            scores[sector.sector_id] = max(0.0, min(1.0, float(sector.classify(text))))
        except Exception:
            scores[sector.sector_id] = 0.0

    if not scores:
        return {"sector_id": None, "confidence": 0.0, "ask": True,
                "reason": "No sectors are registered.", "scores": {}}

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_id, top = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0

    if top < MIN_CONFIDENCE:
        return {"sector_id": None, "confidence": top, "ask": True,
                "reason": ("Nothing here reads clearly as one kind of request. "
                           "Asking rather than guessing."),
                "scores": scores, "candidates": [r[0] for r in ranked[:2]]}

    if top - runner_up < MIN_MARGIN:
        return {"sector_id": None, "confidence": top, "ask": True,
                "reason": (f"This reads about equally as "
                           f"{ranked[0][0]} and {ranked[1][0]}. Asking rather "
                           f"than running the whole pipeline against a guess."),
                "scores": scores, "candidates": [r[0] for r in ranked[:2]]}

    return {"sector_id": top_id, "confidence": top, "ask": False,
            "reason": f"Read as {top_id} ({top:.0%}), ahead of "
                      f"{ranked[1][0] if len(ranked) > 1 else 'nothing else'} "
                      f"({runner_up:.0%}).",
            "scores": scores}


def bootstrap() -> None:
    """
    Register the built-in sectors.

    Imported lazily so a sector that fails to load — a missing dataset,
    say — cannot stop the application starting. The sector simply is not
    offered, which the `/` picker shows honestly by not listing it.
    """
    from app.sectors.products import ProductsSector
    if not get("products"):
        register(ProductsSector())

    try:
        from app.sectors.trip import TripSector
        if not get("trip"):
            register(TripSector())
    except Exception as exc:
        print(f"[sectors] trip sector unavailable: {exc}", flush=True)
