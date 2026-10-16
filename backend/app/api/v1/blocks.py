from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.services import review_service

router = APIRouter(prefix="/blocks", tags=["blocks"])


@router.get("")
def list_published_blocks(
    section: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Published blocks as a calendar, oldest first."""
    return {"blocks": review_service.published_blocks(db, section, date_from, date_to)}
