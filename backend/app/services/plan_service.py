from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ProblemError
from app.core.timeutil import IST, iso_ist, to_ist
from app.db.models import (
    Block,
    BlockRequest,
    PlanAssignment,
    PlanRun,
    Section,
    User,
)
from app.planner.plan import Plan
from app.planner.slots import hhmm
from app.planner.snapshot import (
    DEFAULT_WEIGHTS,
    PlanDependency,
    PlanRequest,
    Snapshot,
)
from app.schemas.plan import PlanCreateIn, PlanOut
from app.services import audit, traffic_service
from app.services.request_service import ValidationProblem

MAX_HORIZON_DAYS = 31


# ---------- time <-> slots ----------


def horizon_start_date(run: PlanRun) -> date:
    return to_ist(run.horizon_start).date()


def slot_ts(start_date: date, day: int, slot: int, slot_minutes: int) -> datetime:
    midnight = datetime.combine(start_date + timedelta(days=day), time(0), tzinfo=IST)
    return midnight + timedelta(minutes=slot * slot_minutes)


def ts_to_day_slot(start_date: date, moment: datetime, slot_minutes: int) -> tuple[int, int, bool]:
    """(day index, slot offset, aligned to the slot grid?) for a timestamp."""
    local = to_ist(moment)
    minutes = local.hour * 60 + local.minute
    aligned = local.second == 0 and local.microsecond == 0 and minutes % slot_minutes == 0
    return (local.date() - start_date).days, minutes // slot_minutes, aligned


# ---------- creating a run ----------


def validate_horizon(body: PlanCreateIn) -> None:
    start, end = to_ist(body.horizon_start), to_ist(body.horizon_end)
    if start.time() != time(0) or end.time() != time(0):
        raise ValidationProblem(
            "horizon_start", "The horizon must start and end at midnight Asia/Kolkata (+05:30)"
        )
    days = (end.date() - start.date()).days
    if not 1 <= days <= MAX_HORIZON_DAYS:
        raise ValidationProblem(
            "horizon_end", f"The horizon must span between 1 and {MAX_HORIZON_DAYS} whole days"
        )
    configured = get_settings().slot_minutes
    if body.slot_minutes != configured:
        raise ValidationProblem(
            "slot_minutes", f"slot_minutes must be {configured}, the configured planning grid"
        )


def create_run(
    db: Session, actor: User, body: PlanCreateIn, idempotency_key: str | None
) -> tuple[PlanRun, bool]:
    """Returns (run, created). A repeated Idempotency-Key returns the original run."""
    if idempotency_key:
        existing = db.scalar(select(PlanRun).where(PlanRun.idempotency_key == idempotency_key))
        if existing is not None:
            return existing, False
    validate_horizon(body)
    run = PlanRun(
        created_by=actor.id,
        horizon_start=body.horizon_start,
        horizon_end=body.horizon_end,
        slot_minutes=body.slot_minutes,
        weights=body.weights.model_dump(),
        time_limit_s=body.time_limit_s,
        random_seed=body.seed,
        model_versions={},
        status="queued",
        idempotency_key=idempotency_key,
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError:  # two requests with the same key at the same moment
        db.rollback()
        existing = db.scalar(select(PlanRun).where(PlanRun.idempotency_key == idempotency_key))
        if existing is None:
            raise
        return existing, False
    audit.record(
        db, actor, "plan.create", "plan_run", run.id, {"time_limit_s": body.time_limit_s}
    )
    db.commit()
    return run, True


# ---------- the snapshot a run plans from ----------


def build_snapshot(db: Session, run: PlanRun) -> Snapshot:
    settings = get_settings()
    start_date = horizon_start_date(run)
    days = (to_ist(run.horizon_end).date() - start_date).days
    rows = list(
        db.scalars(
            select(BlockRequest).where(BlockRequest.status == "submitted").order_by(BlockRequest.id)
        ).unique()
    )
    included = {r.id for r in rows}
    requests = []
    for r in rows:
        pref_day = pref_offset = None
        if r.preferred_start is not None:
            pref_day, pref_offset, _ = ts_to_day_slot(start_date, r.preferred_start, run.slot_minutes)
        requests.append(
            PlanRequest(
                id=r.id,
                dept=r.department.code,
                section=r.section.code,
                duration_minutes=r.duration_minutes,
                earliest_day=(r.earliest_date - start_date).days,
                deadline_day=(r.deadline_date - start_date).days,
                priority=r.priority,
                version=r.version,
                pref_day=pref_day,
                pref_offset=pref_offset,
            )
        )
    # Only dependencies between requests that are part of this run can be planned.
    dependencies = [
        PlanDependency(
            before=d.depends_on_request_id,
            after=d.request_id,
            relation=d.relation,
            gap_minutes=d.min_gap_minutes,
        )
        for r in rows
        for d in r.dependencies
        if d.depends_on_request_id in included
    ]
    sections = sorted({r.section for r in requests})
    cost, trains = traffic_service.load_arrays(db, sections, start_date, days, run.slot_minutes)
    return Snapshot(
        days=days,
        slot_minutes=run.slot_minutes,
        max_block_minutes=settings.max_block_minutes,
        requests=tuple(requests),
        dependencies=tuple(dependencies),
        crews={dept: settings.crews_per_department for dept in {r.dept for r in requests}},
        default_crews=settings.crews_per_department,
        weights={**DEFAULT_WEIGHTS, **run.weights},
        cost=cost,
        trains=trains,
    )


# ---------- saving a verified plan ----------


def save_result(
    db: Session,
    run: PlanRun,
    snapshot: Snapshot,
    plan: Plan,
    baseline: Plan,
    metrics: dict,
    solver_status: str,
    objective: float | None,
    best_bound: float | None,
    overridden_ids: set[int] | None = None,
) -> None:
    """Write blocks, assignments and the run's results in the caller's transaction."""
    start_date = horizon_start_date(run)
    section_ids = {s.code: s.id for s in db.scalars(select(Section))}
    rows: dict[tuple[str, int], Block] = {}
    for block in plan.blocks:
        row = Block(
            plan_run_id=run.id,
            section_id=section_ids[block.section],
            start_ts=slot_ts(start_date, block.day, block.start, snapshot.slot_minutes),
            end_ts=slot_ts(start_date, block.day, block.end, snapshot.slot_minutes),
            trains_affected=sum(snapshot.trains_at(block.section, block.day)[block.start : block.end]),
        )
        db.add(row)
        rows[block.section, block.day] = row
    db.flush()
    for request_id, placement in plan.placements.items():
        db.add(
            PlanAssignment(
                plan_run_id=run.id,
                request_id=request_id,
                block_id=rows[placement.section, placement.day].id,
                start_ts=slot_ts(start_date, placement.day, placement.offset, snapshot.slot_minutes),
                end_ts=slot_ts(start_date, placement.day, placement.end, snapshot.slot_minutes),
                overridden=request_id in (overridden_ids or set()),
            )
        )
    for request_id, reason in plan.deferred.items():
        db.add(
            PlanAssignment(
                plan_run_id=run.id, request_id=request_id, deferred=True, defer_reason=reason
            )
        )
    run.snapshot = snapshot.to_dict()
    run.input_hash = snapshot.input_hash()
    run.plan = plan.to_dict()
    run.baseline = baseline.to_dict()
    run.metrics = metrics
    run.solver_status = solver_status
    run.objective_value = objective
    run.best_bound = best_bound
    run.status = "succeeded"
    run.error = None
    run.finished_at = datetime.now(UTC)


def fail_orphaned_runs(db: Session) -> int:
    """Runs left queued or running by a server that stopped can never finish."""
    result = db.execute(
        update(PlanRun)
        .where(PlanRun.status.in_(("queued", "running")))
        .values(status="failed", error="The server stopped before this run finished")
    )
    db.commit()
    return result.rowcount


# ---------- reading ----------


def get_run_or_404(db: Session, plan_id: int) -> PlanRun:
    run = db.get(PlanRun, plan_id)
    if run is None:
        raise ProblemError(404, "not_found", f"Plan {plan_id} does not exist")
    return run


def plan_out(db: Session, run: PlanRun) -> PlanOut:
    deferred = db.scalars(
        select(PlanAssignment.request_id)
        .where(PlanAssignment.plan_run_id == run.id, PlanAssignment.deferred.is_(True))
        .order_by(PlanAssignment.request_id)
    )
    gap = None
    if run.objective_value is not None and run.best_bound is not None:
        gap = max(0.0, run.objective_value - run.best_bound)
    return PlanOut(
        id=run.id,
        parent_id=run.parent_id,
        status=run.status,
        solver_status=run.solver_status,
        horizon_start=iso_ist(run.horizon_start),
        horizon_end=iso_ist(run.horizon_end),
        slot_minutes=run.slot_minutes,
        weights=run.weights,
        time_limit_s=run.time_limit_s,
        seed=run.random_seed,
        input_hash=run.input_hash,
        objective_value=run.objective_value,
        best_bound=run.best_bound,
        gap=gap,
        metrics=run.metrics,
        deferred_request_ids=list(deferred),
        error=run.error,
        created_by=run.created_by,
        created_at=iso_ist(run.created_at),
        finished_at=iso_ist(run.finished_at),
        approved_at=iso_ist(run.approved_at),
        published_at=iso_ist(run.published_at),
    )


def list_runs(
    db: Session, status: str | None, limit: int, cursor: int | None
) -> tuple[list[PlanRun], int | None]:
    query = select(PlanRun).order_by(PlanRun.id.desc())
    if status:
        query = query.where(PlanRun.status == status)
    if cursor:
        query = query.where(PlanRun.id < cursor)
    rows = list(db.scalars(query.limit(limit + 1)))
    next_cursor = rows[limit - 1].id if len(rows) > limit else None
    return rows[:limit], next_cursor


READY = ("succeeded", "approved", "published")


def require_ready(run: PlanRun) -> None:
    if run.status not in READY:
        raise ProblemError(
            409, "plan_not_ready", f"Plan {run.id} is {run.status}; it has no schedule yet"
        )


def render_plan(
    snapshot: Snapshot,
    plan: Plan,
    start_date: date,
    block_ids: dict[tuple[str, int], int] | None = None,
) -> dict:
    """Blocks with member requests, in the shape the schedule and baseline endpoints return."""
    dept_of = {r.id: r.dept for r in snapshot.requests}
    blocks = []
    for block in plan.blocks:
        members = []
        for request_id in block.request_ids:
            placement = plan.placements[request_id]
            members.append(
                {
                    "request": f"R{request_id}",
                    "request_id": request_id,
                    "dept": dept_of[request_id],
                    "start": hhmm(placement.offset, snapshot.slot_minutes),
                    "end": hhmm(placement.end, snapshot.slot_minutes),
                }
            )
        blocks.append(
            {
                "id": (block_ids or {}).get((block.section, block.day)),
                "section_code": block.section,
                "start": iso_ist(slot_ts(start_date, block.day, block.start, snapshot.slot_minutes)),
                "end": iso_ist(slot_ts(start_date, block.day, block.end, snapshot.slot_minutes)),
                "trains_affected": sum(
                    snapshot.trains_at(block.section, block.day)[block.start : block.end]
                ),
                "members": members,
            }
        )
    deferred = [
        {"request_id": rid, "request": f"R{rid}", "reason": reason}
        for rid, reason in sorted(plan.deferred.items())
    ]
    return {"blocks": blocks, "deferred": deferred}


def schedule(db: Session, run: PlanRun) -> dict:
    require_ready(run)
    snapshot, plan = Snapshot.from_dict(run.snapshot), Plan.from_dict(run.plan)
    start_date = horizon_start_date(run)
    sections = {s.id: s.code for s in db.scalars(select(Section))}
    block_ids = {}
    for row in db.scalars(select(Block).where(Block.plan_run_id == run.id)):
        day = (to_ist(row.start_ts).date() - start_date).days
        block_ids[sections[row.section_id], day] = row.id
    return {"plan_id": run.id, **render_plan(snapshot, plan, start_date, block_ids)}


def baseline(run: PlanRun) -> dict:
    require_ready(run)
    snapshot, plan = Snapshot.from_dict(run.snapshot), Plan.from_dict(run.baseline)
    return {
        "plan_id": run.id,
        "metrics": (run.metrics or {}).get("baseline"),
        **render_plan(snapshot, plan, horizon_start_date(run)),
    }

