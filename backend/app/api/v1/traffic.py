import json
from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_role
from app.core.errors import ProblemError
from app.db.models import Section, User
from app.schemas.traffic import (
    InsertedOut,
    ProfileOut,
    RebuildIn,
    RebuildOut,
    SyntheticIn,
    TimetableEntryIn,
    TimetableUploadIn,
)
from app.services import audit, timetable_gen, traffic_service

router = APIRouter(prefix="/traffic", tags=["traffic"])

planners = require_role("planner", "admin")
MAX_BODY_BYTES = 2_000_000


@router.post("/timetable", status_code=201, response_model=InsertedOut)
async def upload_timetable(
    request: Request,
    replace: bool = False,
    user: User = Depends(planners),
    db: Session = Depends(get_db),
) -> InsertedOut:
    """Bulk upload. Send JSON ({"entries": [...], "replace": false}) or a CSV file with
    Content-Type text/csv (use ?replace=true to replace the timetable)."""
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ProblemError(413, "too_large", "The upload is larger than 2 MB")
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("text/csv"):
        entries = traffic_service.parse_csv(raw.decode("utf-8-sig", errors="replace"))
    else:
        try:
            body = TimetableUploadIn(**json.loads(raw or b"{}"))
        except (ValueError, TypeError) as exc:
            if isinstance(exc, ValidationError):
                errors = [
                    {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
                    for e in exc.errors()
                ]
                raise ProblemError(
                    422, "validation", "Request body is invalid", extra={"errors": errors}
                ) from None
            raise ProblemError(400, "malformed", "The body is not valid JSON") from None
        entries, replace = body.entries, body.replace or replace
    inserted = traffic_service.add_entries(db, entries, replace)
    audit.record(db, user, "traffic.timetable", "timetable", None, {"inserted": inserted, "replace": replace})
    db.commit()
    return InsertedOut(inserted=inserted)


@router.post("/synthetic", status_code=201, response_model=InsertedOut)
def generate_synthetic_timetable(
    body: SyntheticIn | None = None,
    user: User = Depends(planners),
    db: Session = Depends(get_db),
) -> InsertedOut:
    """Fill the timetable with invented traffic for every section (demo and testing)."""
    body = body or SyntheticIn()
    codes = list(db.scalars(select(Section.code)))
    entries = [
        TimetableEntryIn(**e) for e in timetable_gen.generate_timetable(codes, body.seed)
    ]
    inserted = traffic_service.add_entries(db, entries, body.replace)
    audit.record(db, user, "traffic.synthetic", "timetable", None, {"seed": body.seed, "inserted": inserted})
    db.commit()
    return InsertedOut(inserted=inserted)


@router.post("/rebuild", response_model=RebuildOut)
def rebuild_traffic(
    body: RebuildIn, user: User = Depends(planners), db: Session = Depends(get_db)
) -> RebuildOut:
    result = traffic_service.rebuild_profile(db, body.date_from, body.date_to)
    audit.record(
        db,
        user,
        "traffic.rebuild",
        "traffic_profile",
        None,
        {"date_from": body.date_from.isoformat(), "date_to": body.date_to.isoformat(), **result},
    )
    db.commit()
    return RebuildOut(**result)


@router.get("/profile", response_model=ProfileOut)
def get_profile(
    section: str,
    date_from: date,
    date_to: date,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return traffic_service.get_profile(db, section, date_from, date_to)

