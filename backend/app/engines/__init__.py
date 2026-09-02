"""
The dual-engine architecture: a GenAI layer that reads a need, a
recommendation system that decides the answer, and a typed boundary
between them so neither can quietly do the other's job.
"""
from app.engines.contracts import Constraint, Explanation, NeedSpec, Ranked
from app.engines.loop import engines, run, use

__all__ = ["Constraint", "Explanation", "NeedSpec", "Ranked",
           "engines", "run", "use"]
