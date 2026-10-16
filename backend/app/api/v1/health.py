from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import PlanRun

router = APIRouter(tags=["health"])

# A run that has waited this long without anything running means the planner thread is stuck.
STALLED_AFTER_SECONDS = 600


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness only: does not touch the database."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness: the database answers, its tables are in place, the solver loads, and the plan
    queue is moving. 200 when everything is fine, 503 with the failing checks otherwise."""
    checks: dict[str, object] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001
        checks["database"] = "unavailable"

    if checks["database"] == "ok":
        try:
            counts = dict(db.execute(select(PlanRun.status, func.count()).group_by(PlanRun.status)).all())
            checks["schema"] = "ok"
            queued, running = counts.get("queued", 0), counts.get("running", 0)
            oldest = db.scalar(select(func.min(PlanRun.created_at)).where(PlanRun.status == "queued"))
            waiting = (datetime.now(UTC) - oldest).total_seconds() if oldest else 0
            stalled = bool(queued) and not running and waiting > STALLED_AFTER_SECONDS
            checks["planner"] = {
                "status": "stalled" if stalled else "ok",
                "queued": queued,
                "running": running,
                "oldest_queued_seconds": round(waiting),
            }
        except Exception:  # noqa: BLE001
            db.rollback()
            checks["schema"] = "missing tables: run alembic upgrade head"

    try:
        from ortools.sat.python import cp_model  # noqa: F401

        checks["solver"] = "ok"
    except Exception:  # noqa: BLE001
        checks["solver"] = "unavailable"

    healthy = (
        checks["database"] == "ok"
        and checks.get("schema") == "ok"
        and checks["solver"] == "ok"
        and checks.get("planner", {}).get("status") == "ok"
    )
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )
