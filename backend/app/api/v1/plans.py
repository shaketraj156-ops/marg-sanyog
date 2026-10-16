from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_role
from app.db.models import User
from app.schemas.plan import PlanAccepted, PlanCreateIn, PlanListOut, PlanOut
from app.services import plan_runner, plan_service

router = APIRouter(prefix="/plans", tags=["plans"])

reviewers = require_role("planner", "admin")


@router.post("", status_code=202, response_model=PlanAccepted)
def create_plan(
    body: PlanCreateIn,
    idempotency_key: str | None = Header(default=None, max_length=200),
    user: User = Depends(reviewers),
    db: Session = Depends(get_db),
):
    run, created = plan_service.create_run(db, user, body, idempotency_key)
    if created:
        plan_runner.submit(run.id)
    return JSONResponse(
        status_code=202,
        content={
            "id": run.id,
            "status": run.status,
            "links": {"self": f"/api/v1/plans/{run.id}"},
        },
    )


@router.get("", response_model=PlanListOut)
def list_plans(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: int | None = Query(None, ge=1),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlanListOut:
    rows, next_cursor = plan_service.list_runs(db, status, limit, cursor)
    return PlanListOut(items=[plan_service.plan_out(db, r) for r in rows], next_cursor=next_cursor)


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(
    plan_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> PlanOut:
    return plan_service.plan_out(db, plan_service.get_run_or_404(db, plan_id))


@router.get("/{plan_id}/schedule")
def get_schedule(
    plan_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return plan_service.schedule(db, plan_service.get_run_or_404(db, plan_id))


@router.get("/{plan_id}/baseline")
def get_baseline(
    plan_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return plan_service.baseline(plan_service.get_run_or_404(db, plan_id))
