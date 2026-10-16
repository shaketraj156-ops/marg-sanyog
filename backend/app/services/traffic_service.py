from datetime import date

from sqlalchemy.orm import Session

Arrays = dict[str, dict[int, list[int]]]


def load_arrays(
    db: Session, sections: list[str], start_date: date, days: int, slot_minutes: int
) -> tuple[Arrays, Arrays]:
    """Per-slot weighted trains and plain train counts: section -> day index -> list.

    No traffic data is loaded yet, so every slot counts as empty."""
    return {}, {}
