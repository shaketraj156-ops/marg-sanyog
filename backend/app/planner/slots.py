"""Time <-> slot conversion. The solver works in integer slots counted from the horizon start."""
import math

MINUTES_PER_DAY = 24 * 60


def slots_per_day(slot_minutes: int) -> int:
    return MINUTES_PER_DAY // slot_minutes


def duration_slots(minutes: int, slot_minutes: int) -> int:
    """Durations are rounded up to a whole number of slots."""
    return math.ceil(minutes / slot_minutes)


def absolute_slot(day: int, offset: int, per_day: int) -> int:
    return day * per_day + offset


def prefix_sums(values: list[int]) -> list[int]:
    """cum[k] = sum of values[:k], so the cost of slots [a, b) is cum[b] - cum[a]."""
    cum = [0]
    for value in values:
        cum.append(cum[-1] + value)
    return cum


def hhmm(slot: int, slot_minutes: int) -> str:
    minutes = slot * slot_minutes
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
