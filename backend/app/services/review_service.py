"""The review workflow: what-if, override, approve and publish."""
import logging
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ProblemError
from app.core.timeutil import iso_ist
from app.db.models import (
    Block,
    BlockRequest,
    Department,
    Explanation,
    PlanAssignment,
    PlanRun,
    Section,
    User,
)
from app.planner.checker import check_plan
from app.planner.metrics import compute_metrics
from app.planner.plan import Placement, Plan
from app.planner.snapshot import Snapshot
from app.schemas.review import MoveIn, OverrideIn, WhatIfIn
from app.services import audit, explain, plan_service
from app.services import request_service as requests_svc
from app.services.explain import fmt_day, label
from app.services.request_service import ValidationProblem
from app.services.solving import solve

log = logging.getLogger(__name__)
METRIC_KEYS = (
    "closures",
    "block_hours",
    "trains_affected",
    "traffic_cost",
    "weighted_postponement_days",
    "deferred",
)


def _workers() -> int | None:
    return get_settings().solver_workers or None


def _load(run: PlanRun) -> tuple[Snapshot, Plan, Plan]:
    return (
        Snapshot.from_dict(run.snapshot),
        Plan.from_dict(run.plan),
        Plan.from_dict(run.baseline),
    )


def _where(snapshot: Snapshot, start_date: date, placement: Placement | None) -> dict | None:
    if placement is None:
        return None
    return {
        "start": iso_ist(
            plan_service.slot_ts(start_date, placement.day, placement.offset, snapshot.slot_minutes)
        ),
        "end": iso_ist(
            plan_service.slot_ts(start_date, placement.day, placement.end, snapshot.slot_minutes)
        ),
    }


# ---------- moves (what-if and override) ----------


def _parse_move(snapshot: Snapshot, start_date: date, move: MoveIn) -> tuple[int, int, int]:
    request = next((r for r in snapshot.requests if r.id == move.request_id), None)
    if request is None:
        raise ProblemError(
            422, "unknown_request", f"Request {move.request_id} is not part of this plan"
        )
    day, slot, aligned = plan_service.ts_to_day_slot(start_date, move.start, snapshot.slot_minutes)
    if not aligned:
        raise ValidationProblem(
            "start", f"start must be on a {snapshot.slot_minutes}-minute boundary"
        )
    forced = snapshot.forced_deferrals()
    lo, hi = snapshot.window(request)
    if request.id in forced:
        raise ProblemError(
            422,
            "move_outside_window",
            f"{label(request.id)} cannot be placed ({forced[request.id]}), so it cannot be moved",
        )
    if not lo <= day <= hi:
        raise ProblemError(
            422,
            "move_outside_window",
            f"{label(request.id)} may only be planned between {fmt_day(start_date, lo)} and "
            f"{fmt_day(start_date, hi)}",
        )
    if slot + snapshot.dur(request) > snapshot.per_day:
        raise ProblemError(
            422, "move_outside_window", f"{label(request.id)} would run past midnight"
        )
    return request.id, day, slot


def _require_reviewable(run: PlanRun) -> None:
    if run.status not in ("succeeded", "approved"):
        raise ProblemError(
            409,
            "invalid_state",
            f"Plan {run.id} is {run.status}; only a succeeded or approved plan can be reviewed",
        )


def _difference(before: dict, after: dict) -> dict:
    return {
        k: round(after[k] - before[k], 2) if isinstance(after[k], float) else after[k] - before[k]
        for k in METRIC_KEYS
    }


def _moved(snapshot: Snapshot, start_date: date, old: Plan, new: Plan, skip: set[int]) -> list[dict]:
    moved = []
    for request_id in sorted(set(old.placements) | set(new.placements) | set(old.deferred)):
        if request_id in skip:
            continue
        before, after = old.placements.get(request_id), new.placements.get(request_id)
        if before != after:
            moved.append(
                {
                    "request_id": request_id,
                    "request": label(request_id),
                    "from": _where(snapshot, start_date, before),
                    "to": _where(snapshot, start_date, after),
                }
            )
    return moved


def _resolve(snapshot: Snapshot, plan: Plan, fixed: dict, time_limit_s: int, seed: int):
    result = solve(
        snapshot,
        hints=plan,
        fixed=fixed,
        time_limit_s=time_limit_s,
        seed=seed,
        workers=_workers(),
    )
    if result.status == "CRASHED":
        log.error("the solver crashed during a re-solve: %s", result.message)
        raise ProblemError(
            503, "solver_crashed", "The solver stopped unexpectedly. Nothing was changed; try again."
        )
    if result.status in ("OPTIMAL", "FEASIBLE"):
        violations = check_plan(snapshot, result.plan)
        if violations:
            log.error("checker rejected a re-solve: %s", violations)
            raise ProblemError(
                500, "checker_rejected", "The re-solved plan failed verification and was discarded"
            )
    return result


def whatif(run: PlanRun, body: WhatIfIn) -> dict:
    """Try one move. Re-solves everything else around it; nothing is saved."""
    plan_service.require_ready(run)
    _require_reviewable(run)
    snapshot, plan, _ = _load(run)
    start_date = plan_service.horizon_start_date(run)
    request_id, day, slot = _parse_move(snapshot, start_date, body)
    result = _resolve(snapshot, plan, {request_id: (day, slot)}, body.time_limit_s, run.random_seed)
    if result.plan is None:
        reason = (
            "No plan is possible with that move"
            if result.status == "INFEASIBLE"
            else "No solution was found within the time limit"
        )
        return {"feasible": False, "solver_status": result.status, "reason": reason}
    current = (run.metrics or {})["integrated"]
    changed = compute_metrics(snapshot, result.plan)
    return {
        "feasible": True,
        "solver_status": result.status,
        "target": {
            "request_id": request_id,
            "from": _where(snapshot, start_date, plan.placements.get(request_id)),
            "to": _where(snapshot, start_date, result.plan.placements.get(request_id)),
        },
        "metrics": {
            "current": current,
            "whatif": changed,
            "difference": _difference(current, changed),
        },
        "moved_requests": _moved(snapshot, start_date, plan, result.plan, {request_id}),
    }


def override(db: Session, actor: User, run: PlanRun, body: OverrideIn) -> PlanRun:
    """Apply moves and re-solve. The result is a child run; the original stays on record."""
    plan_service.require_ready(run)
    _require_reviewable(run)
    snapshot, plan, baseline = _load(run)
    start_date = plan_service.horizon_start_date(run)
    ids = [m.request_id for m in body.moves]
    if len(set(ids)) != len(ids):
        raise ValidationProblem("moves", "each request may be moved only once")
    fixed = {}
    for move in body.moves:
        request_id, day, slot = _parse_move(snapshot, start_date, move)
        fixed[request_id] = (day, slot)

    result = _resolve(snapshot, plan, fixed, body.time_limit_s, run.random_seed)
    if result.plan is None:
        raise ProblemError(
            409,
            "override_infeasible",
            "Those moves cannot be combined into a valid plan"
            if result.status == "INFEASIBLE"
            else "No solution was found within the time limit",
        )

    child = PlanRun(
        parent_id=run.id,
        created_by=actor.id,
        horizon_start=run.horizon_start,
        horizon_end=run.horizon_end,
        slot_minutes=run.slot_minutes,
        weights=run.weights,
        time_limit_s=body.time_limit_s,
        random_seed=run.random_seed,
        model_versions=run.model_versions,
        status="running",
    )
    db.add(child)
    db.flush()
    metrics = {
        "baseline": run.metrics["baseline"],
        "integrated": compute_metrics(snapshot, result.plan),
        "solver": {"wall_time_s": round(result.wall_time_s, 2), "gap": result.gap},
    }
    plan_service.save_result(
        db,
        child,
        snapshot,
        result.plan,
        baseline,
        metrics,
        result.status,
        result.objective,
        result.best_bound,
        overridden_ids=set(fixed),
    )
    db.flush()
    drafts = explain.explain(
        snapshot,
        result.plan,
        baseline,
        start_date,
        parent=plan,
        overridden=frozenset(fixed),
    )
    explain.save(db, child, drafts)
    audit.record(
        db,
        actor,
        "plan.override",
        "plan_run",
        child.id,
        {"parent": run.id, "moves": [{"request_id": m.request_id, "start": m.start.isoformat()} for m in body.moves]},
    )
    db.commit()
    return child


# ---------- approve and publish ----------


def approve(db: Session, actor: User, run: PlanRun) -> PlanRun:
    if run.status != "succeeded":
        raise ProblemError(
            409,
            "invalid_transition",
            f"A plan can only be approved when it has succeeded, not when it is {run.status}",
        )
    snapshot = Snapshot.from_dict(run.snapshot)
    plan = Plan.from_dict(run.plan)
    versions = {r.id: r.version for r in snapshot.requests}
    rows = {
        r.id: r
        for r in db.scalars(select(BlockRequest).where(BlockRequest.id.in_(list(plan.placements))))
        .unique()
    }
    stale = sorted(
        i
        for i in plan.placements
        if i not in rows or rows[i].status != "submitted" or rows[i].version != versions[i]
    )
    if stale:
        raise ProblemError(
            409,
            "stale_plan",
            "These requests changed after the plan was made, so it cannot be approved: "
            + ", ".join(label(i) for i in stale)
            + ". Run a new plan.",
            extra={"request_ids": stale},
        )
    now = datetime.now(UTC)
    for request in rows.values():
        requests_svc.transition(request, "scheduled")
        request.updated_at = now
    run.status = "approved"
    run.approved_by = actor.id
    run.approved_at = now
    audit.record(
        db, actor, "plan.approve", "plan_run", run.id, {"requests": sorted(plan.placements)}
    )
    requests_svc.commit(db)
    return run


def _overlapping_published(db: Session, block: Block) -> Block | None:
    """The overlap rule for published blocks, enforced here so SQLite honours it too (on
    Postgres an exclusion constraint backs it up)."""
    return db.scalars(
        select(Block).where(
            Block.status == "published",
            Block.section_id == block.section_id,
            Block.start_ts < block.end_ts,
            Block.end_ts > block.start_ts,
            Block.id != block.id,
        )
    ).first()


def publish(db: Session, actor: User, run: PlanRun) -> PlanRun:
    if run.status != "approved":
        raise ProblemError(
            409,
            "invalid_transition",
            f"A plan can only be published after approval, not when it is {run.status}",
        )
    blocks = list(db.scalars(select(Block).where(Block.plan_run_id == run.id)))
    sections = {s.id: s.code for s in db.scalars(select(Section))}
    conflicts = []
    for block in blocks:
        other = _overlapping_published(db, block)
        if other is not None:
            conflicts.append(
                {
                    "block_id": block.id,
                    "section_code": sections[block.section_id],
                    "start": iso_ist(block.start_ts),
                    "end": iso_ist(block.end_ts),
                    "conflicts_with_block": other.id,
                    "conflicts_with_plan": other.plan_run_id,
                }
            )
    if conflicts:
        raise ProblemError(
            409,
            "block_overlap",
            "A published block already closes the same section at an overlapping time; "
            "nothing was published",
            extra={"conflicts": conflicts},
        )
    now = datetime.now(UTC)
    for block in blocks:
        block.status = "published"
    request_ids = list(
        db.scalars(
            select(PlanAssignment.request_id).where(
                PlanAssignment.plan_run_id == run.id, PlanAssignment.deferred.is_(False)
            )
        )
    )
    for request in db.scalars(select(BlockRequest).where(BlockRequest.id.in_(request_ids))).unique():
        requests_svc.transition(request, "published")
        request.updated_at = now
    run.status = "published"
    run.published_at = now
    audit.record(
        db, actor, "plan.publish", "plan_run", run.id, {"blocks": [b.id for b in blocks]}
    )
    try:
        requests_svc.commit(db)
    except IntegrityError:  # the database-level exclusion constraint (Postgres)
        db.rollback()
        raise ProblemError(
            409, "block_overlap", "A published block overlaps one of these blocks"
        ) from None
    return run


# ---------- conflicts ----------


def _components(requests, snapshot: Snapshot) -> list[list]:
    """Group requests on one section whose date windows overlap, as connected components."""
    ordered = sorted(requests, key=lambda r: snapshot.window(r))
    groups: list[list] = []
    reach = -1
    for request in ordered:
        lo, hi = snapshot.window(request)
        if groups and lo <= reach:
            groups[-1].append(request)
            reach = max(reach, hi)
        else:
            groups.append([request])
            reach = hi
    return groups


def conflicts(run: PlanRun) -> dict:
    """Conflicts found in the input and how the plan resolved them."""
    plan_service.require_ready(run)
    snapshot, plan, _ = _load(run)
    start_date = plan_service.horizon_start_date(run)
    found = []

    by_section = defaultdict(list)
    for request in snapshot.requests:
        by_section[request.section].append(request)
    for section, requests in sorted(by_section.items()):
        for group in _components(requests, snapshot):
            if len(group) < 2:
                continue
            ids = sorted(r.id for r in group)
            placed = [plan.placements[i] for i in ids if i in plan.placements]
            closures = {(p.section, p.day) for p in placed}
            if not placed:
                resolution, detail = "DEFERRED", "none of them could be placed"
            elif len(closures) == 1 and len(placed) == len(ids):
                day = next(iter(closures))[1]
                resolution = "MERGED"
                detail = f"all share one block on {fmt_day(start_date, day)}"
            else:
                resolution = "SEPARATED"
                detail = (
                    f"placed in {len(closures)} closure{'s' if len(closures) != 1 else ''}"
                    + (f", {len(ids) - len(placed)} deferred" if len(placed) < len(ids) else "")
                )
            found.append(
                {
                    "type": "SECTION_COMPETITION",
                    "section_code": section,
                    "request_ids": ids,
                    "departments": sorted({r.dept for r in group}),
                    "detail": f"{', '.join(label(i) for i in ids)} want {section} within "
                    "overlapping dates",
                    "resolution": resolution,
                    "resolution_detail": detail,
                }
            )

    for dep in snapshot.dependencies:
        if dep.relation == "same_block_allowed":
            continue
        before, after = plan.placements.get(dep.before), plan.placements.get(dep.after)
        if after is None:
            resolution, detail = "DEFERRED", f"{label(dep.after)} was not placed"
        elif before is None:
            resolution, detail = "DEFERRED", f"{label(dep.before)} was not placed"
        elif dep.relation == "finish_before_start":
            resolution = "ORDERED"
            detail = f"{label(dep.before)} runs first, {label(dep.after)} starts after it"
        else:
            resolution = "SEPARATED_DAYS"
            detail = (
                f"{label(dep.before)} on {fmt_day(start_date, before.day)}, "
                f"{label(dep.after)} on {fmt_day(start_date, after.day)}"
            )
        found.append(
            {
                "type": "DEPENDENCY",
                "request_ids": [dep.before, dep.after],
                "relation": dep.relation,
                "detail": f"{label(dep.after)} depends on {label(dep.before)} ({dep.relation})",
                "resolution": resolution,
                "resolution_detail": detail,
            }
        )

    for request_id, reason in sorted(plan.deferred.items()):
        found.append(
            {
                "type": "UNPLACED",
                "request_ids": [request_id],
                "reason": reason,
                "detail": f"{label(request_id)} could not be planned ({reason})",
                "resolution": "DEFERRED",
                "resolution_detail": "stays submitted for a later plan",
            }
        )
    return {"plan_id": run.id, "conflicts": found}


# ---------- reading explanations and the published calendar ----------


def explanations(
    db: Session, run: PlanRun, code: str | None, request_id: int | None, block_id: int | None
) -> list[Explanation]:
    query = select(Explanation).where(Explanation.plan_run_id == run.id).order_by(Explanation.id)
    if code:
        query = query.where(Explanation.code == code)
    if request_id:
        query = query.where(Explanation.request_id == request_id)
    if block_id:
        query = query.where(Explanation.block_id == block_id)
    return list(db.scalars(query))


def published_blocks(
    db: Session, section: str | None, date_from: date | None, date_to: date | None
) -> list[dict]:
    query = (
        select(Block, Section.code)
        .join(Section, Block.section_id == Section.id)
        .where(Block.status == "published")
        .order_by(Block.start_ts, Block.id)
    )
    if section:
        query = query.where(Section.code == section)
    if date_from:
        query = query.where(Block.end_ts > plan_service.slot_ts(date_from, 0, 0, 30))
    if date_to:
        query = query.where(Block.start_ts < plan_service.slot_ts(date_to, 1, 0, 30))
    rows = db.execute(query).all()
    members: dict[int, list[dict]] = defaultdict(list)
    ids = [b.id for b, _ in rows]
    if ids:
        for assignment, dept in db.execute(
            select(PlanAssignment, Department.code)
            .join(BlockRequest, PlanAssignment.request_id == BlockRequest.id)
            .join(Department, BlockRequest.department_id == Department.id)
            .where(PlanAssignment.block_id.in_(ids))
            .order_by(PlanAssignment.start_ts, PlanAssignment.request_id)
        ).all():
            members[assignment.block_id].append(
                {
                    "request_id": assignment.request_id,
                    "request": label(assignment.request_id),
                    "dept": dept,
                    "start": iso_ist(assignment.start_ts),
                    "end": iso_ist(assignment.end_ts),
                }
            )
    return [
        {
            "id": block.id,
            "plan_id": block.plan_run_id,
            "section_code": code,
            "start": iso_ist(block.start_ts),
            "end": iso_ist(block.end_ts),
            "trains_affected": block.trains_affected,
            "status": block.status,
            "members": members[block.id],
        }
        for block, code in rows
    ]
