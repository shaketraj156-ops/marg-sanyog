"""Synthetic timetable generator. Invented data only: no real railway figures are used.

Each section gets a mix of train categories with a realistic daily rhythm: commuter peaks
in the morning and evening, mail trains at night, freight biased to the small hours. That
makes the night quieter than the day (but never empty), which gives the planner something
real to optimise."""
import random
from datetime import time

from app.db.models.traffic import CATEGORY_WEIGHT

# category -> (trains per section, relative weight of each start hour, traverse minutes)
PATTERNS: dict[str, tuple[int, list[int], tuple[int, int]]] = {
    "premium": (4, [0, 0, 0, 0, 0, 1, 3, 3, 3, 2, 1, 1, 1, 1, 1, 2, 3, 3, 3, 3, 2, 1, 0, 0], (20, 35)),
    "mail": (3, [3, 2, 1, 1, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 3, 3, 3], (25, 40)),
    "passenger": (8, [0, 0, 0, 0, 1, 2, 3, 3, 3, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 2, 2, 1, 0, 0], (30, 50)),
    "local": (14, [0, 0, 0, 0, 1, 3, 5, 5, 4, 2, 1, 1, 1, 1, 1, 2, 4, 5, 5, 4, 2, 1, 0, 0], (30, 50)),
    "freight": (10, [3, 3, 3, 3, 3, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 3, 3, 3], (40, 70)),
}
TRAIN_NUMBER_BASE = {"premium": 12000, "mail": 13000, "passenger": 56000, "local": 31000, "freight": 71000}
WEEKDAYS = 0b0011111  # Monday to Friday
EVERY_DAY = 0b1111111
DAY_CHOICES = {
    "premium": [EVERY_DAY],
    "mail": [EVERY_DAY],
    "passenger": [EVERY_DAY],
    "local": [EVERY_DAY, WEEKDAYS, EVERY_DAY],
    "freight": [EVERY_DAY, EVERY_DAY, WEEKDAYS, 0b1100000],
}


def generate_timetable(section_codes: list[str], seed: int = 1) -> list[dict]:
    """Deterministic for a given seed. Returns dicts ready for the upload endpoint."""
    rng = random.Random(seed)
    counters = dict.fromkeys(PATTERNS, 0)
    entries = []
    for section in sorted(section_codes):
        for category, (count, hour_weights, (fastest, slowest)) in PATTERNS.items():
            for _ in range(count):
                hour = rng.choices(range(24), weights=hour_weights)[0]
                minute = rng.choice(range(0, 60, 5))
                leaves = (hour * 60 + minute + rng.randint(fastest, slowest)) % (24 * 60)
                counters[category] += 1
                entries.append(
                    {
                        "train_no": str(TRAIN_NUMBER_BASE[category] + counters[category]),
                        "category": category,
                        "weight": CATEGORY_WEIGHT[category],
                        "section_code": section,
                        "days_of_week": rng.choice(DAY_CHOICES[category]),
                        "enters_at": time(hour, minute).strftime("%H:%M"),
                        "leaves_at": time(leaves // 60, leaves % 60).strftime("%H:%M"),
                    }
                )
    return entries
