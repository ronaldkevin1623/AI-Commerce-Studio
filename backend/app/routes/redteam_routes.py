"""
Adversarial evaluation, on demand.

Exposed as an endpoint rather than a script so the results can be shown in
the product itself. A security claim nobody can re-run is a marketing claim.
"""
from fastapi import APIRouter

from app.redteam import runner
from app.redteam.attacks import ATTACKS
from app.firebase_client import log_decision

router = APIRouter(prefix="/redteam")


@router.get("/corpus")
def corpus():
    """What the harness will try, without running it."""
    return {"count": len(ATTACKS), "attacks": ATTACKS}


@router.post("/run")
def run_suite():
    """Execute the corpus against the live pipeline and score it."""
    report = runner.run()

    log_decision(
        action_type="redteam_run",
        amount_paise=0,
        decision="allowed" if report["breached"] == 0 else "blocked",
        reason=(
            f"Adversarial suite: {report['held']}/{report['total']} invariants held, "
            f"{report['critical_held']}/{report['critical_total']} critical"
        ),
    )
    return report


@router.get("/history")
def past_runs(limit: int = 20):
    """Every suite run so far, so the score is a trend and not a screenshot."""
    return {"runs": runner.history(limit)}


@router.post("/fixtures/clear")
def clear():
    """Remove any hostile listing a interrupted run left behind."""
    return {"removed": runner.clear_fixtures()}
