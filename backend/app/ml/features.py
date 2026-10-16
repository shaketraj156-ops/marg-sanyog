"""Feature definitions shared by training and prediction, so the two can never disagree."""

SLOT_MINUTES = 30

# Delay model: how many train-minutes are lost if a block closes a section for a window.
DELAY_FEATURES = [
    "section_idx",
    "hour",
    "weekday",
    "window_slots",
    "trains",
    "weighted",
    "mean_weight",
]

# Overrun model: actual duration divided by planned duration.
WORK_TYPES = ["track", "ohe", "signal", "bridge", "other"]
OVERRUN_FEATURES = ["work_type_idx", "section_idx", "planned_minutes", "month", "crew_size"]


def delay_row(
    section_idx: int,
    start_slot: int,
    slots: int,
    weekday: int,
    trains_cum: list[int],
    weighted_cum: list[int],
    slot_minutes: int = SLOT_MINUTES,
) -> list[float]:
    """Features of one closure window. trains_cum and weighted_cum are prefix sums of the
    per-slot counts (cum[k] = total of the first k slots), so the window totals are differences."""
    trains = trains_cum[start_slot + slots] - trains_cum[start_slot]
    weighted = weighted_cum[start_slot + slots] - weighted_cum[start_slot]
    return [
        float(section_idx),
        start_slot * slot_minutes / 60,
        float(weekday),
        float(slots),
        float(trains),
        float(weighted),
        weighted / trains if trains else 0.0,  # average weight of the trains: a premium-share signal
    ]


def overrun_row(
    work_type: str, section_idx: int, planned_minutes: int, month: int, crew_size: int
) -> list[float]:
    return [
        float(WORK_TYPES.index(work_type)),
        float(section_idx),
        float(planned_minutes),
        float(month),
        float(crew_size),
    ]
