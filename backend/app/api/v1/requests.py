from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_role
from app.db.models import User
from app.schemas.request import (
    BlockRequestIn,
    BlockRequestPatch,
    DependenciesIn,
    RejectIn,
    RequestListOut,
    RequestOut,
    VersionIn,
)
from app.services import request_service as svc

router = APIRouter(prefix="/requests", tags=["requests"])

# Department users act on their own department only; the service enforces that.
writers = require_role("dept_user", "planner", "admin")
reviewers = require_role("planner", "admin")


@router.post("", status_code=201, response_model=RequestOut)
def create_request(
    body: BlockRequestIn, user: User = Depends(writers), db: Session = Depends(get_db)
) -> RequestOut:
    request, warnings = svc.create_request(db, user, body)
    return svc.to_out(request, warnings)


@router.get("", response_model=RequestListOut)
def list_requests(
    status: str | None = None,
    section: str | None = None,
    department: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: int | None = Query(None, ge=1),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestListOut:
    rows, next_cursor = svc.list_requests(
        db,
        status=status,
        section=section,
        department=department,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        cursor=cursor,
    )
    return RequestListOut(items=[svc.to_out(r) for r in rows], next_cursor=next_cursor)


@router.get("/{request_id}", response_model=RequestOut)
def get_request(
    request_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> RequestOut:
    return svc.to_out(svc.get_or_404(db, request_id))


@router.patch("/{request_id}", response_model=RequestOut)
def update_request(
    request_id: int,
    body: BlockRequestPatch,
    user: User = Depends(writers),
    db: Session = Depends(get_db),
) -> RequestOut:
    request, warnings = svc.update_request(db, user, request_id, body)
    return svc.to_out(request, warnings)


@router.post("/{request_id}/submit", response_model=RequestOut)
def submit_request(
    request_id: int,
    body: VersionIn | None = None,
    user: User = Depends(writers),
    db: Session = Depends(get_db),
) -> RequestOut:
    request, warnings = svc.submit_request(db, user, request_id, body.version if body else None)
    return svc.to_out(request, warnings)


@router.post("/{request_id}/cancel", response_model=RequestOut)
def cancel_request(
    request_id: int,
    body: VersionIn | None = None,
    user: User = Depends(writers),
    db: Session = Depends(get_db),
) -> RequestOut:
    request = svc.cancel_request(db, user, request_id, body.version if body else None)
    return svc.to_out(request)


@router.post("/{request_id}/reject", response_model=RequestOut)
def reject_request(
    request_id: int,
    body: RejectIn,
    user: User = Depends(reviewers),
    db: Session = Depends(get_db),
) -> RequestOut:
    request = svc.reject_request(db, user, request_id, body.reason, body.version)
    return svc.to_out(request)


@router.put("/{request_id}/dependencies", response_model=RequestOut)
def replace_dependencies(
    request_id: int,
    body: DependenciesIn,
    user: User = Depends(writers),
    db: Session = Depends(get_db),
) -> RequestOut:
    return svc.to_out(svc.replace_dependencies(db, user, request_id, body))
