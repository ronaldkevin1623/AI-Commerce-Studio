"""
AGENT SETTINGS

The hive is not just a diagram of the pipeline — it's the control surface
for it. Every value here is a parameter some agent genuinely reads at run
time, so turning a dial on a node changes what that agent actually does on
the next run. Nothing in this module is decorative: if a control exists,
the agent below it consumes it.

TWO CLASSES OF SETTING, AND WHY IT MATTERS:
Some of these are search preferences (how many listings to fetch, how the
ranker breaks ties). Others move the boundary of what the agent is allowed
to spend without asking — the auto-approve limit, the session ceiling, the
minimum trust score. Raising an auto-approve limit is itself a financial
act: it widens the band in which money moves with no human in the loop. So
changes to those are written to the audit trail under their own action type,
and the log records the old value alongside the new one. A reviewer can then
answer "why did this £4,000 order sail through?" with "because the limit was
raised eleven minutes earlier, by this person".

Persistence is Firestore, with an in-memory cache so a pipeline step doesn't
pay a network read per threshold lookup. If Firestore is unreachable the
cache still serves defaults rather than crashing the run.
"""
import time

from app.config import AUTO_APPROVE_LIMIT_PAISE

# ── Specification ────────────────────────────────────────────────────────
# Each entry: kind, bounds, default, and whether it moves a financial bound.
# The frontend renders its controls from a mirror of this, but the backend
# validates independently — a client is never trusted to keep itself in range.

_AUTO_APPROVE_DEFAULT_INR = AUTO_APPROVE_LIMIT_PAISE // 100

SPEC: dict[str, dict[str, dict]] = {
    "intent": {
        # Ranges are kept tight deliberately: the scrub gesture spreads the
        # whole range across ~300px, so a needlessly huge ceiling would make
        # the control unusable — and a lower cap on a money bound is safer.
        "max_price_override_inr": {
            "kind": "int", "min": 0, "max": 200000, "default": 0,
            "label": "Budget cap",
            "note": "0 means use whatever budget was parsed from the request.",
        },
    },
    "scout": {
        "result_limit": {
            "kind": "int", "min": 3, "max": 50, "default": 24,
            "label": "Listings",
            "note": "How many live eBay listings to pull per search. Too few and "
                    "the ranker has nothing to choose between once trust and "
                    "relevance screening have taken their cut.",
        },
    },
    "trust": {
        "outlier_floor_pct": {
            "kind": "int", "min": 0, "max": 95, "default": 45,
            "label": "Outlier floor", "suffix": "%",
            "note": "Flag a listing priced below this share of the result-set median.",
        },
        "min_seller_feedback": {
            "kind": "int", "min": 0, "max": 100, "default": 90,
            "label": "Min feedback", "suffix": "%",
            "note": "Flag sellers whose eBay feedback percentage is below this.",
        },
        "drop_flagged": {
            "kind": "bool", "default": True,
            "label": "Drop flagged listings",
            "note": "When off, flagged listings stay in the ranking but keep their warning.",
        },
    },
    "value": {
        "priority": {
            "kind": "enum",
            "choices": ["auto", "value", "discount", "price", "rating",
                        "delivery_days"],
            "default": "auto",
            "label": "Rank by",
            "note": "Overrides the priority Intent parsed. 'auto' defers to the request.",
        },
    },
    "budget": {
        "session_ceiling_inr": {
            "kind": "int", "min": 100, "max": 200000,
            "default": _AUTO_APPROVE_DEFAULT_INR * 4,
            "label": "Session ceiling", "prefix": "₹", "financial": True,
            "note": "Total cumulative spend allowed for a customer before the agent blocks.",
        },
        "warn_at_pct": {
            "kind": "int", "min": 10, "max": 100, "default": 75,
            "label": "Warn at", "suffix": "%", "financial": True,
            "note": "Share of the ceiling at which Budget turns amber instead of green.",
        },
    },
    "risk": {
        "auto_approve_limit_inr": {
            "kind": "int", "min": 0, "max": 100000, "default": _AUTO_APPROVE_DEFAULT_INR,
            "label": "Auto-approve up to", "prefix": "₹", "financial": True,
            "note": "Orders above this are escalated to a human instead of auto-approved.",
        },
        "duplicate_window_seconds": {
            "kind": "int", "min": 0, "max": 3600, "default": 60,
            "label": "Duplicate window", "suffix": "s", "financial": True,
            "note": "Block a repeat of the same product by the same customer inside this window.",
        },
        "min_trust_score": {
            "kind": "int", "min": 0, "max": 100, "default": 40,
            "label": "Min trust score", "financial": True,
            "note": "Customers below this score cannot buy autonomously.",
        },
        "max_purchases_per_window": {
            "kind": "int", "min": 0, "max": 50, "default": 5,
            "label": "Purchases per window", "financial": True,
            "note": "More autonomous purchases than this inside the velocity "
                    "window escalate to a human. 0 turns the check off.",
        },
        "velocity_window_seconds": {
            "kind": "int", "min": 60, "max": 86400, "default": 3600,
            "label": "Velocity window", "suffix": "s", "financial": True,
            "note": "How far back the purchase count looks.",
        },
    },
    "negotiator": {
        "goal": {
            "kind": "enum",
            "choices": ["condition", "authenticity", "price", "shipping"],
            "default": "condition",
            "label": "Default ask",
            "note": "Which question the seller-contact draft opens on.",
        },
        "max_sentences": {
            "kind": "int", "min": 1, "max": 6, "default": 3,
            "label": "Max sentences",
            "note": "Hard cap given to the model when drafting.",
        },
    },
    "ollama": {
        "temperature": {
            "kind": "int", "min": 0, "max": 100, "default": 70,
            "label": "Temperature", "scale": 0.01,
            "note": "Passed to Ollama as temperature ÷ 100. Lower is more repeatable.",
        },
    },
    "ebay": {
        "usd_to_inr": {
            "kind": "int", "min": 1, "max": 200, "default": 83,
            "label": "USD → INR", "prefix": "₹", "financial": True,
            "note": "Browse API has no India marketplace, so USD prices are converted at this "
                    "fixed rate. It is not a live forex lookup, and it decides what you are "
                    "actually charged in rupees.",
        },
    },
}

DEFAULTS = {
    node: {key: spec["default"] for key, spec in params.items()}
    for node, params in SPEC.items()
}

# Nodes with no tunable parameters. Listed explicitly so the UI can say
# "nothing to tune here, and here's why" rather than rendering an empty card.
NO_TUNABLES = {
    "payment": "Payment has no dials — the amount comes from the listing and the gate above it "
               "decides whether it runs at all.",
    "refund": "A refund is issued against a specific captured payment, so there is nothing to "
              "pre-configure.",
    "firestore": "Firestore is the audit store. Making the record adjustable would defeat its "
                 "purpose.",
    "razorpay": "Razorpay runs in test mode with keys from the environment. Nothing here is "
                "safe to tune from a browser.",
}

# ── Role presets ─────────────────────────────────────────────────────────
# One-click starting points, for the very reasonable person who does not
# know what "outlier floor 45%" is supposed to mean.
#
# DELIBERATE OMISSION: no preset touches budget or risk. Those hold the
# bounds on how much money can move without a human, and a button that
# quietly widened them — however well labelled — would hollow out the whole
# "bounded and gated" claim. Presets tune what the agent looks for and how
# suspicious it is; what it may spend stays a decision someone makes on
# purpose, on the Budget and Risk nodes.

PRESETS = {
    "customer": {
        "label": "Customer",
        "blurb": "Shopping for yourself. Screens hard, hunts discounts, and asks sellers about condition.",
        "values": {
            "scout": {"result_limit": 24},
            "trust": {
                "outlier_floor_pct": 45,
                "min_seller_feedback": 95,
                "drop_flagged": True,
            },
            # Deliberately "auto", not "discount". Pinning the ranker to
            # discount made every search a hunt for the biggest markdown —
            # a camera-phone request came back with ₹166 flip phones because
            # they happened to be 80% off. Following the request is the
            # right default; someone who wants deals can say so.
            "value": {"priority": "auto"},
            "negotiator": {"goal": "condition"},
        },
    },
    "reseller": {
        "label": "Reseller",
        "blurb": "Sourcing stock to sell on. Casts wide, ranks on price for margin, "
                 "and stops treating repeat buys of the same item as a mistake.",
        "values": {
            # Sourcing is a numbers game — more of the market in view.
            "scout": {"result_limit": 40},
            # Still screens hard. Someone buying to resell carries the
            # consequences of a bad listing twice over, so this is the one
            # place a reseller wants *more* caution than a casual shopper,
            # not less.
            "trust": {
                "outlier_floor_pct": 40,
                "min_seller_feedback": 95,
                "drop_flagged": True,
            },
            "value": {"priority": "price"},
            "negotiator": {"goal": "price"},
            # The two brakes that assume one-off shopping. Buying ten of the
            # same thing is what sourcing *is*; the money ceilings below are
            # untouched and still bind.
            "risk": {
                "duplicate_window_seconds": 0,
                "max_purchases_per_window": 25,
            },
        },
    },
    "seller": {
        "label": "Seller",
        "blurb": "Sourcing or sizing up a market. Casts wider, keeps suspicious listings visible, and hunts the price floor.",
        "values": {
            # A merchant wants breadth over curation: more results, and the
            # cheap outliers kept in view. To a buyer a listing 60% under
            # median is a red flag; to a seller it is the competition.
            "scout": {"result_limit": 30},
            "trust": {
                "outlier_floor_pct": 25,
                "min_seller_feedback": 80,
                "drop_flagged": False,
            },
            "value": {"priority": "price"},
            "negotiator": {"goal": "price"},
        },
    },
}

# Which nodes a preset can reach at all — the UI states this rather than
# leaving people to infer it from what happens to change.
PRESET_SCOPE = ["scout", "trust", "value", "negotiator", "risk"]

# The dials no preset may move, whatever it claims to be for. These decide
# how much money can leave without a human, and choosing a role is not the
# same act as raising a spending limit — those stay a deliberate, separate
# change on the node itself.
PRESET_FROZEN = {
    ("risk", "auto_approve_limit_inr"),
    ("risk", "min_trust_score"),
    ("budget", "session_ceiling_inr"),
    ("budget", "warn_at_pct"),
    ("intent", "max_price_override_inr"),
}


def _audit_presets():
    """
    Fail at import if a preset reaches somewhere it should not.

    A preset that quietly touched a frozen dial would be indistinguishable
    from one that did not until somebody read the diff, so this is checked
    once, loudly, rather than trusted.
    """
    for name, preset in PRESETS.items():
        for node, values in preset["values"].items():
            if node not in PRESET_SCOPE:
                raise ValueError(
                    f"Preset '{name}' touches '{node}', which is outside PRESET_SCOPE"
                )
            for key in values:
                if (node, key) in PRESET_FROZEN:
                    raise ValueError(
                        f"Preset '{name}' touches frozen dial {node}.{key} — "
                        "presets may change behaviour, never spending limits"
                    )


_audit_presets()

_COLLECTION = "agent_settings"
_DOCUMENT = "current"

# Cache is what the pipeline reads; Firestore is where it survives a restart.
# Seeded from defaults so the pipeline works before any write.
#
# The cache is refreshed on a short TTL rather than loaded once per process.
# uvicorn --reload runs several worker processes over a session, and a
# process holding a stale copy used to clobber everyone else's values the
# next time it wrote — _persist() sends the whole document, so one stale key
# overwrites all of them. Re-reading before any write, and every few seconds
# on read, keeps separate processes from fighting each other.
_CACHE_TTL_SECONDS = 5

_cache: dict[str, dict] = {node: dict(values) for node, values in DEFAULTS.items()}
_loaded_at = 0.0


def _db():
    from app.firebase_client import db
    return db


def _load(force: bool = False) -> None:
    """Pull persisted settings over the defaults, at most once per TTL."""
    global _loaded_at
    now = time.time()
    if not force and _loaded_at and (now - _loaded_at) < _CACHE_TTL_SECONDS:
        return
    _loaded_at = now
    try:
        doc = _db().collection(_COLLECTION).document(_DOCUMENT).get()
        if not doc.exists:
            return
        stored = doc.to_dict() or {}
        for node, values in stored.items():
            if node not in SPEC or not isinstance(values, dict):
                continue
            for key, value in values.items():
                if key in SPEC[node]:
                    _cache[node][key] = value
    except Exception as exc:
        # A settings read must never take the pipeline down — defaults are
        # a perfectly good answer, and the failure is worth seeing.
        print(f"[settings] could not load from Firestore, using defaults: {exc}")


def all_settings() -> dict:
    _load()
    return {node: dict(values) for node, values in _cache.items()}


def get(node: str, key: str):
    """The accessor every agent uses. Falls back to the declared default."""
    _load()
    return _cache.get(node, {}).get(key, DEFAULTS.get(node, {}).get(key))


def _coerce(spec: dict, value):
    """Validate and clamp one incoming value against its spec."""
    kind = spec["kind"]
    if kind == "bool":
        return bool(value)
    if kind == "enum":
        if value not in spec["choices"]:
            raise ValueError(f"must be one of {spec['choices']}")
        return value
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("must be a whole number")
    # Clamp rather than reject: the UI already bounds its controls, and a
    # value one past the edge is a slip, not an attack.
    return max(spec["min"], min(spec["max"], number))


def apply(patch: dict) -> list[dict]:
    """
    Validate and persist a patch. Returns one record per value that actually
    changed — {node, key, old, new, financial, label} — so the caller can
    write an honest audit entry naming the movement, not just the new state.
    """
    # Force a re-read first: writing the whole document from a stale cache
    # would silently revert changes another process made.
    _load(force=True)
    changes: list[dict] = []

    for node, values in (patch or {}).items():
        if node not in SPEC or not isinstance(values, dict):
            continue
        for key, raw in values.items():
            spec = SPEC[node].get(key)
            if not spec:
                continue
            new = _coerce(spec, raw)
            old = _cache[node].get(key)
            if old == new:
                continue
            _cache[node][key] = new
            changes.append({
                "node": node,
                "key": key,
                "label": spec.get("label", key),
                "old": old,
                "new": new,
                "financial": bool(spec.get("financial")),
            })

    if changes:
        _persist()
    return changes


def active_preset() -> str | None:
    """
    The preset whose values the current settings match, or None for a
    hand-tuned mix. Only the keys a preset actually defines are compared —
    a preset says nothing about spending bounds, so those never decide this.
    """
    _load()
    for name, preset in PRESETS.items():
        if all(
            _cache.get(node, {}).get(key) == value
            for node, values in preset["values"].items()
            for key, value in values.items()
        ):
            return name
    return None


def reset(node: str | None = None) -> list[dict]:
    """Restore defaults for one node, or all of them."""
    _load()
    nodes = [node] if node else list(SPEC.keys())
    patch = {n: dict(DEFAULTS[n]) for n in nodes if n in DEFAULTS}
    return apply(patch)


def _persist() -> None:
    try:
        _db().collection(_COLLECTION).document(_DOCUMENT).set(_cache)
    except Exception as exc:
        # The change still holds in memory for this process; say so loudly
        # rather than pretending it was saved.
        print(f"[settings] change applied in memory but NOT persisted: {exc}")
