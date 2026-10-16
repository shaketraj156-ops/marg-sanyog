import csv
import io
from collections import defaultdict
from datetime import date, timedelta

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ProblemError
from app.db.models import Section, TimetableEntry, TrafficProfile
from app.db.models.traffic import CATEGORY_WEIGHT
from app.planner.slots import slots_per_day
from app.schemas.traffic import TimetableEntryIn

Arrays = dict[str, dict[int, list[int]]]

MAX_REBUILD_DAYS = 62
MAX_PROFILE_DAYS = 31
MAX_UPLOAD_ROWS = 5000


def _problem(errors: list[dict]) -> ProblemError:
    return ProblemError(
        422, "validation", "Request body is invalid", extra={"errors": errors}
    )


# ---------- timetable upload ----------


def parse_csv(text: str) -> list[TimetableEntryIn]:
    """Columns: train_no, category, section_code, enters_at, leaves_at (HH:MM), and optionally
    weight and days_of_week."""
    reader = csv.DictReader(io.StringIO(text))
    required = {"train_no", "category", "section_code", "enters_at", "leaves_at"}
    if reader.fieldnames is None or not required <= set(reader.fieldnames):
        missing = sorted(required - set(reader.fieldnames or []))
        raise _problem([{"field": "(csv header)", "message": f"missing columns: {', '.join(missing)}"}])
    entries, errors = [], []
    for number, row in enumerate(reader, start=2):  # row 1 is the header
        if number - 1 > MAX_UPLOAD_ROWS:
            raise _problem([{"field": "(csv)", "message": f"at most {MAX_UPLOAD_ROWS} rows"}])
        data = {k: v.strip() for k, v in row.items() if k and v is not None and v.strip() != ""}
        for numeric in ("weight", "days_of_week"):
            if numeric in data:
                try:
                    data[numeric] = int(data[numeric])
                except ValueError:
                    errors.append({"field": f"row {number}: {numeric}", "message": "not a number"})
                    data.pop(numeric)
        try:
            entries.append(TimetableEntryIn(**data))
        except ValidationError as exc:
            for e in exc.errors():
                field = ".".join(str(p) for p in e["loc"]) or "(row)"
                errors.append({"field": f"row {number}: {field}", "message": e["msg"]})
    if errors:
        raise _problem(errors)
    return entries


def add_entries(db: Session, entries: list[TimetableEntryIn], replace: bool) -> int:
    sections = {s.code: s.id for s in db.scalars(select(Section))}
    unknown = sorted({e.section_code for e in entries} - set(sections))
    if unknown:
        raise ProblemError(422, "unknown_section", f"Unknown sections: {', '.join(unknown)}")
    if replace:
        db.execute(delete(TimetableEntry))
    db.add_all(
        TimetableEntry(
            train_no=e.train_no,
            category=e.category,
            weight=e.weight if e.weight is not None else CATEGORY_WEIGHT[e.category],
            section_id=sections[e.section_code],
            days_of_week=e.days_of_week,
            enters_at=e.enters_at,
            leaves_at=e.leaves_at,
        )
        for e in entries
    )
    db.commit()
    return len(entries)


# ---------- the traffic profile ----------


def rebuild_profile(db: Session, date_from: date, date_to: date) -> dict[str, int]:
    """Expand the timetable into trains per slot per section per day.

    A train counts in the slot where it enters the section, so a closure affects the trains
    that arrive while it lasts. Rebuilding is idempotent."""
    if date_to < date_from:
        raise _problem([{"field": "date_to", "message": "date_to must not be before date_from"}])
    days = (date_to - date_from).days + 1
    if days > MAX_REBUILD_DAYS:
        raise _problem([{"field": "date_to", "message": f"at most {MAX_REBUILD_DAYS} days at once"}])
    slot_minutes = get_settings().slot_minutes
    entries = list(db.scalars(select(TimetableEntry)))

    db.execute(
        delete(TrafficProfile).where(TrafficProfile.day >= date_from, TrafficProfile.day <= date_to)
    )
    rows = 0
    sections = set()
    for offset in range(days):
        day = date_from + timedelta(days=offset)
        counts: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
        for entry in entries:
            if not entry.days_of_week >> day.weekday() & 1:
                continue
            slot = (entry.enters_at.hour * 60 + entry.enters_at.minute) // slot_minutes
            cell = counts[entry.section_id, slot]
            cell[0] += 1
            cell[1] += entry.weight
        for (section_id, slot), (trains, weighted) in sorted(counts.items()):
            db.add(
                TrafficProfile(
                    section_id=section_id, day=day, slot_index=slot, trains=trains, weighted=weighted
                )
            )
            sections.add(section_id)
            rows += 1
    db.commit()
    return {"days": days, "sections": len(sections), "rows": rows}


def _day_arrays(rows, per_day: int) -> tuple[list[int], list[int]]:
    trains, weighted = [0] * per_day, [0] * per_day
    for row in rows:
        trains[row.slot_index] = row.trains
        weighted[row.slot_index] = row.weighted
    return trains, weighted


def load_arrays(
    db: Session, sections: list[str], start_date: date, days: int, slot_minutes: int
) -> tuple[Arrays, Arrays]:
    """Per-slot weighted trains (the planner's cost) and plain train counts (reported as
    trains affected): section -> day index -> list. Sections without traffic are omitted."""
    per_day = slots_per_day(slot_minutes)
    ids = {s.code: s.id for s in db.scalars(select(Section).where(Section.code.in_(sections)))}
    by_code = {v: k for k, v in ids.items()}
    grouped: dict[tuple[str, int], list[TrafficProfile]] = defaultdict(list)
    for row in db.scalars(
        select(TrafficProfile).where(
            TrafficProfile.section_id.in_(list(ids.values())),
            TrafficProfile.day >= start_date,
            TrafficProfile.day < start_date + timedelta(days=days),
        )
    ):
        grouped[by_code[row.section_id], (row.day - start_date).days].append(row)
    cost: Arrays = {}
    trains: Arrays = {}
    for (code, day), rows in grouped.items():
        plain, weighted = _day_arrays(rows, per_day)
        trains.setdefault(code, {})[day] = plain
        cost.setdefault(code, {})[day] = weighted
    return cost, trains


def get_profile(db: Session, section_code: str, date_from: date, date_to: date) -> dict:
    section = db.scalar(select(Section).where(Section.code == section_code))
    if section is None:
        raise ProblemError(404, "not_found", f"Section {section_code} does not exist")
    if date_to < date_from:
        raise _problem([{"field": "date_to", "message": "date_to must not be before date_from"}])
    count = (date_to - date_from).days + 1
    if count > MAX_PROFILE_DAYS:
        raise _problem([{"field": "date_to", "message": f"at most {MAX_PROFILE_DAYS} days at once"}])
    slot_minutes = get_settings().slot_minutes
    per_day = slots_per_day(slot_minutes)
    by_day: dict[date, list[TrafficProfile]] = defaultdict(list)
    for row in db.scalars(
        select(TrafficProfile).where(
            TrafficProfile.section_id == section.id,
            TrafficProfile.day >= date_from,
            TrafficProfile.day <= date_to,
        )
    ):
        by_day[row.day].append(row)
    result = []
    for offset in range(count):
        day = date_from + timedelta(days=offset)
        trains, weighted = _day_arrays(by_day.get(day, []), per_day)
        result.append({"date": day, "trains": trains, "weighted": weighted})
    return {"section_code": section_code, "slot_minutes": slot_minutes, "days": result}
