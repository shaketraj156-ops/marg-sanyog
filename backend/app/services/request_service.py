from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.config import get_settings
from app.core.errors import ProblemError
from app.core.timeutil import iso_ist
from app.db.models import BlockRequest, Department, RequestDependency, Section, User
from app.schemas.request import (
    BlockRequestIn,
    BlockRequestPatch,
    DependenciesIn,
    DependencyOut,
    RequestOut,
    WarningOut,
)
from app.services import audit
from app.services.validation import find_cycle

EDITABLE = ("draft", "submitted")

# Section 8 of the spec. "scheduled", "published" and "completed" are reached by the system
# (plan approval, publication, actuals), but the table lives here so there is one definition.
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"scheduled", "cancelled", "rejected"},
    "scheduled": {"published", "cancelled"},
    "published": {"completed"},
}


def transition(request: BlockRequest, to_status: str) -> None:
    if to_status not in TRANSITIONS.get(request.status, set()):
        raise ProblemError(
            409,
            "invalid_transition",
            f"A request cannot move from {request.status} to {to_status}",
        )
    request.status = to_status


class ValidationProblem(ProblemError):
    """422 with a field error list, same shape as schema validation errors."""

    def __init__(self, field: str, message: str):
        super().__init__(
            422,
            "validation",
            "Request body is invalid",
            extra={"errors": [{"field": field, "message": message}]},
        )


def get_or_404(db: Session, request_id: int) -> BlockRequest:
    request = db.get(BlockRequest, request_id)
    if request is None:
        raise ProblemError(404, "not_found", f"Request {request_id} does not exist")
    return request


def ensure_can_act(actor: User, request: BlockRequest) -> None:
    if actor.role == "dept_user" and actor.department_id != request.department_id:
        raise ProblemError(
            403, "forbidden", "Department users may only act for their own department"
        )


def check_version(request: BlockRequest, expected: int | None) -> None:
    if expected is not None and expected != request.version:
        raise ProblemError(
            409, "version_conflict", f"Request is at version {request.version}, not {expected}"
        )


def commit(db: Session) -> None:
    """Commit; a lost optimistic-locking race becomes 409 version_conflict."""
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        raise ProblemError(
            409, "version_conflict", "The request was changed by someone else; reload it"
        ) from None


def _section(db: Session, code: str) -> Section:
    section = db.scalar(select(Section).where(Section.code == code))
    if section is None:
        raise ProblemError(422, "unknown_section", f"Section {code} does not exist")
    return section


def _department_for(db: Session, actor: User, code: str | None) -> Department:
    if actor.role == "dept_user":
        if actor.department_id is None:
            raise ProblemError(403, "forbidden", "Your account has no department")
        department = db.get(Department, actor.department_id)
        if code is not None and code != department.code:
            raise ProblemError(
                403, "forbidden", "Department users may only act for their own department"
            )
        return department
    if code is None:
        raise ValidationProblem("department_code", "department_code is required for this role")
    department = db.scalar(select(Department).where(Department.code == code))
    if department is None:
        raise ProblemError(422, "unknown_department", f"Department {code} does not exist")
    return department


def find_duplicates(
    db: Session,
    department_id: int,
    section_id: int,
    work_type: str,
    earliest: date,
    deadline: date,
    exclude_id: int | None,
) -> list[WarningOut]:
    """Same department, section and type with an overlapping window. A warning only."""
    query = select(BlockRequest.id).where(
        BlockRequest.department_id == department_id,
        BlockRequest.section_id == section_id,
        BlockRequest.work_type == work_type,
        BlockRequest.status.not_in(("cancelled", "rejected")),
        BlockRequest.earliest_date <= deadline,
        BlockRequest.deadline_date >= earliest,
    )
    if exclude_id is not None:
        query = query.where(BlockRequest.id != exclude_id)
    ids = list(db.scalars(query.order_by(BlockRequest.id)))
    if not ids:
        return []
    listed = ", ".join(str(i) for i in ids)
    return [
        WarningOut(
            code="duplicate_request",
            detail=f"Possible duplicate of request {listed} (same department, section, type "
            "and overlapping dates)",
            request_ids=ids,
        )
    ]


def to_out(request: BlockRequest, warnings: list[WarningOut] | None = None) -> RequestOut:
    return RequestOut(
        id=request.id,
        status=request.status,
        department=request.department.code,
        section_code=request.section.code,
        work_type=request.work_type,
        description=request.description,
        duration_minutes=request.duration_minutes,
        earliest_date=request.earliest_date,
        deadline_date=request.deadline_date,
        priority=request.priority,
        needs_power_block=request.needs_power_block,
        preferred_start=iso_ist(request.preferred_start),
        requested_by=request.requested_by,
        version=request.version,
        dependencies=[
            DependencyOut(
                depends_on=d.depends_on_request_id,
                relation=d.relation,
                min_gap_minutes=d.min_gap_minutes,
            )
            for d in request.dependencies
        ],
        created_at=iso_ist(request.created_at),
        updated_at=iso_ist(request.updated_at),
        warnings=warnings or [],
    )


def _jsonable(value):
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def create_request(
    db: Session, actor: User, body: BlockRequestIn
) -> tuple[BlockRequest, list[WarningOut]]:
    department = _department_for(db, actor, body.department_code)
    section = _section(db, body.section_code)
    warnings = find_duplicates(
        db,
        department.id,
        section.id,
        body.work_type,
        body.earliest_date,
        body.deadline_date,
        None,
    )
    request = BlockRequest(
        department_id=department.id,
        section_id=section.id,
        requested_by=actor.id,
        work_type=body.work_type,
        description=body.description,
        duration_minutes=body.duration_minutes,
        earliest_date=body.earliest_date,
        deadline_date=body.deadline_date,
        priority=body.priority,
        needs_power_block=body.needs_power_block,
        preferred_start=body.preferred_start,
    )
    db.add(request)
    db.flush()
    audit.record(
        db,
        actor,
        "request.create",
        "block_request",
        request.id,
        {"department": department.code, "section": section.code, "work_type": body.work_type},
    )
    commit(db)
    return request, warnings


def update_request(
    db: Session, actor: User, request_id: int, body: BlockRequestPatch
) -> tuple[BlockRequest, list[WarningOut]]:
    request = get_or_404(db, request_id)
    ensure_can_act(actor, request)
    if request.status not in EDITABLE:
        raise ProblemError(
            409, "invalid_state", f"Only draft or submitted requests can be edited, not {request.status}"
        )
    check_version(request, body.version)

    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    section = _section(db, changes.pop("section_code")) if "section_code" in changes else None
    earliest = changes.get("earliest_date", request.earliest_date)
    deadline = changes.get("deadline_date", request.deadline_date)
    if deadline < earliest:
        raise ValidationProblem("deadline_date", "deadline_date must not be before earliest_date")
    for field in ("work_type", "duration_minutes", "earliest_date", "deadline_date", "priority"):
        if field in changes and changes[field] is None:
            raise ValidationProblem(field, f"{field} cannot be null")

    warnings = find_duplicates(
        db,
        request.department_id,
        section.id if section else request.section_id,
        changes.get("work_type", request.work_type),
        earliest,
        deadline,
        request.id,
    )
    if not changes and section is None:
        return request, warnings

    diff: dict[str, list] = {}
    for field, value in changes.items():
        diff[field] = [_jsonable(getattr(request, field)), _jsonable(value)]
        setattr(request, field, value)
    if section is not None:
        diff["section_code"] = [request.section.code, section.code]
        request.section = section
        request.section_id = section.id
    request.updated_at = datetime.now(UTC)
    audit.record(db, actor, "request.update", "block_request", request.id, {"changes": diff})
    commit(db)
    return request, warnings


def submit_request(
    db: Session, actor: User, request_id: int, version: int | None
) -> tuple[BlockRequest, list[WarningOut]]:
    request = get_or_404(db, request_id)
    ensure_can_act(actor, request)
    check_version(request, version)
    if request.status != "draft":
        raise ProblemError(
            409, "invalid_transition", f"A request cannot move from {request.status} to submitted"
        )
    # Validation must pass: re-check everything that can have changed since it was saved.
    if request.duration_minutes > get_settings().max_block_minutes:
        raise ValidationProblem(
            "duration_minutes",
            f"Input should be less than or equal to {get_settings().max_block_minutes}",
        )
    _check_dependency_targets(db, [d.depends_on_request_id for d in request.dependencies])
    warnings = find_duplicates(
        db,
        request.department_id,
        request.section_id,
        request.work_type,
        request.earliest_date,
        request.deadline_date,
        request.id,
    )
    transition(request, "submitted")
    request.updated_at = datetime.now(UTC)
    audit.record(db, actor, "request.submit", "block_request", request.id)
    commit(db)
    return request, warnings


def cancel_request(
    db: Session, actor: User, request_id: int, version: int | None
) -> BlockRequest:
    request = get_or_404(db, request_id)
    ensure_can_act(actor, request)
    check_version(request, version)
    previous = request.status
    transition(request, "cancelled")
    request.updated_at = datetime.now(UTC)
    audit.record(
        db, actor, "request.cancel", "block_request", request.id, {"from": previous}
    )
    commit(db)
    return request


def reject_request(
    db: Session, actor: User, request_id: int, reason: str, version: int | None
) -> BlockRequest:
    request = get_or_404(db, request_id)
    check_version(request, version)
    transition(request, "rejected")
    request.updated_at = datetime.now(UTC)
    audit.record(
        db, actor, "request.reject", "block_request", request.id, {"reason": reason}
    )
    commit(db)
    return request


def _check_dependency_targets(db: Session, ids: list[int]) -> None:
    if not ids:
        return
    found = {
        r.id: r.status for r in db.execute(select(BlockRequest.id, BlockRequest.status).where(BlockRequest.id.in_(ids)))
    }
    for target in ids:
        if target not in found:
            raise ProblemError(422, "unknown_dependency", f"Request {target} does not exist")
        if found[target] == "cancelled":
            raise ProblemError(
                422, "unknown_dependency", f"Request {target} is cancelled and cannot be depended on"
            )


def replace_dependencies(
    db: Session, actor: User, request_id: int, body: DependenciesIn
) -> BlockRequest:
    request = get_or_404(db, request_id)
    ensure_can_act(actor, request)
    if request.status not in EDITABLE:
        raise ProblemError(
            409, "invalid_state", f"Dependencies of a {request.status} request cannot be changed"
        )
    check_version(request, body.version)

    targets = [d.depends_on for d in body.dependencies]
    if len(set(targets)) != len(targets):
        raise ValidationProblem("dependencies", "each request may be listed only once")
    if request.id in targets:
        raise ProblemError(
            422, "dependency_cycle", f"Request {request.id} cannot depend on itself"
        )
    _check_dependency_targets(db, targets)

    edges: dict[int, set[int]] = {}
    rows = db.execute(
        select(RequestDependency.request_id, RequestDependency.depends_on_request_id).where(
            RequestDependency.request_id != request.id
        )
    )
    for source, target in rows:
        edges.setdefault(source, set()).add(target)
    cycle = find_cycle(request.id, targets, edges)
    if cycle:
        path = " -> ".join(f"R{i}" for i in cycle)
        raise ProblemError(422, "dependency_cycle", f"Dependencies would form a cycle: {path}")

    request.dependencies = [
        RequestDependency(
            request_id=request.id,
            depends_on_request_id=d.depends_on,
            relation=d.relation,
            min_gap_minutes=d.min_gap_minutes,
        )
        for d in body.dependencies
    ]
    request.updated_at = datetime.now(UTC)
    audit.record(
        db,
        actor,
        "request.dependencies",
        "block_request",
        request.id,
        {"dependencies": [d.model_dump() for d in body.dependencies]},
    )
    commit(db)
    return request


def list_requests(
    db: Session,
    *,
    status: str | None,
    section: str | None,
    department: str | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    cursor: int | None,
) -> tuple[list[BlockRequest], int | None]:
    query = select(BlockRequest).order_by(BlockRequest.id)
    if status:
        query = query.where(BlockRequest.status == status)
    if section:
        query = query.join(Section, BlockRequest.section_id == Section.id).where(
            Section.code == section
        )
    if department:
        query = query.join(Department, BlockRequest.department_id == Department.id).where(
            Department.code == department
        )
    if date_from:
        query = query.where(BlockRequest.deadline_date >= date_from)
    if date_to:
        query = query.where(BlockRequest.earliest_date <= date_to)
    if cursor:
        query = query.where(BlockRequest.id > cursor)
    rows = list(db.scalars(query.limit(limit + 1)).unique())
    next_cursor = rows[limit - 1].id if len(rows) > limit else None
    return rows[:limit], next_cursor

