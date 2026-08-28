"""
Reading and changing what the specialists are allowed to do.

The audit rule here is the point of the whole feature: moving a financial
bound is itself a financial action. If someone raises the auto-approve limit
and a large order then sails through unescalated, the trail has to explain
that — so every changed bound is logged with its old value and its new one,
under an action type that stands out from ordinary purchase decisions.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent import settings
from app.firebase_client import log_decision

router = APIRouter()


def _describe(change: dict, source: str | None) -> str:
    body = (
        f"{change['node'].title()} · {change['label']}: "
        f"{change['old']} → {change['new']}"
    )
    # Naming the preset matters: "who changed this and why" is the question
    # the trail exists to answer, and "the Seller preset did" is an answer.
    return f"{source} · {body}" if source else body


def _record(changes: list[dict], customer_id: str | None, source: str | None = None) -> None:
    """One audit row per changed value, so each is filterable on its own."""
    for change in changes:
        log_decision(
            action_type=(
                "financial_bound_changed" if change["financial"] else "agent_setting_changed"
            ),
            amount_paise=0,
            # A widened bound is the one worth flagging on sight: it lets
            # more money move with less friction than it did a moment ago.
            decision="escalated" if change["financial"] else "allowed",
            reason=_describe(change, source),
            customer_id=customer_id,
        )


@router.get("/agent-settings")
def read_settings():
    """Current values, the spec the UI renders from, and what has no dials."""
    return {
        "values": settings.all_settings(),
        "spec": settings.SPEC,
        "defaults": settings.DEFAULTS,
        "no_tunables": settings.NO_TUNABLES,
        "presets": settings.PRESETS,
        "preset_scope": settings.PRESET_SCOPE,
        "active_preset": settings.active_preset(),
    }


class SettingsPatch(BaseModel):
    changes: dict
    customer_id: str | None = None
    source: str | None = None


@router.patch("/agent-settings")
def update_settings(req: SettingsPatch):
    try:
        changes = settings.apply(req.changes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _record(changes, req.customer_id, req.source)
    return {
        "changed": changes,
        "values": settings.all_settings(),
        "active_preset": settings.active_preset(),
    }


class PresetRequest(BaseModel):
    name: str
    customer_id: str | None = None


@router.post("/agent-settings/preset")
def apply_preset(req: PresetRequest):
    preset = settings.PRESETS.get(req.name)
    if not preset:
        raise HTTPException(status_code=404, detail=f"No preset named {req.name}")

    changes = settings.apply(preset["values"])
    _record(changes, req.customer_id, f"{preset['label']} preset")
    return {
        "changed": changes,
        "values": settings.all_settings(),
        "active_preset": settings.active_preset(),
    }


class SettingsReset(BaseModel):
    node: str | None = None
    customer_id: str | None = None


@router.post("/agent-settings/reset")
def reset_settings(req: SettingsReset):
    changes = settings.reset(req.node)
    _record(changes, req.customer_id, "Reset to defaults")
    return {
        "changed": changes,
        "values": settings.all_settings(),
        "active_preset": settings.active_preset(),
    }
