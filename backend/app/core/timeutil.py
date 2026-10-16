from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def to_ist(value: datetime) -> datetime:
    return value.astimezone(IST)


def iso_ist(value: datetime | None) -> str | None:
    """ISO 8601 with the +05:30 offset, as shown in the API."""
    return to_ist(value).isoformat() if value is not None else None
