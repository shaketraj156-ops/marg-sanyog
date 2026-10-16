from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.errors import ProblemError
from app.db.models import Department, Section
from app.schemas.reference import DepartmentOut, SectionOut

# Every signed-in role may read reference data.
router = APIRouter(tags=["reference"], dependencies=[Depends(get_current_user)])


@router.get("/sections", response_model=list[SectionOut])
def list_sections(db: Session = Depends(get_db)):
    return db.scalars(select(Section).order_by(Section.code)).all()


@router.get("/sections/{section_id}", response_model=SectionOut)
def get_section(section_id: int, db: Session = Depends(get_db)):
    section = db.get(Section, section_id)
    if section is None:
        raise ProblemError(404, "not_found", f"Section {section_id} does not exist")
    return section


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    return db.scalars(select(Department).order_by(Department.code)).all()
