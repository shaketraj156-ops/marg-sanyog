"""Synthetic training data. Invented: no real railway data exists in this project.

The generators hide a "true" process the models have to learn, so there is a real signal to
find and a fair baseline to beat. Every row carries the date it belongs to, because the models
are always evaluated with a time-based split (train on the past, test on the future)."""
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from app.ml.features import WORK_TYPES, delay_row, overrun_row
from app.planner.slots import prefix_sums
from app.services.timetable_gen import generate_timetable

START = date(2026, 1, 5)  # a Monday
SLOTS = 48
WINDOWS_PER_SECTION_DAY = 12
REQUESTS_PER_DAY = 30


@dataclass
class Dataset:
    X: np.ndarray
    y: np.ndarray
    days: np.ndarray  # day index of each row, the order of time
    feature_names: list[str]
    extra: dict[str, np.ndarray]  # untransformed columns the baselines need


def _base_arrays(section_codes: list[str], seed: int):
    """Per section and weekday: trains and weighted trains per slot, from a synthetic timetable."""
    arrays = {s: {w: ([0] * SLOTS, [0] * SLOTS) for w in range(7)} for s in section_codes}
    for entry in generate_timetable(section_codes, seed=seed):
        hours, minutes = map(int, entry["enters_at"].split(":"))
        slot = (hours * 60 + minutes) // 30
        for weekday in range(7):
            if entry["days_of_week"] >> weekday & 1:
                trains, weighted = arrays[entry["section_code"]][weekday]
                trains[slot] += 1
                weighted[slot] += entry["weight"]
    return arrays


PEAKS = ((7, 10), (17, 20))
SECTION_FACTOR = (0.8, 1.0, 1.25, 1.4)


def true_delay(section_idx: int, start: int, slots: int, weekday: int, trains, weighted, rng) -> float:
    """The hidden process: delay grows with weighted traffic, more than linearly when trains bunch
    up, is worse at the commuter peaks, differs by section, and is a little lower at weekends."""
    minutes = 3.0  # fixed cost of closing and reopening
    for k in range(start, start + slots):
        hour = k / 2
        peak = 1.6 if any(a <= hour < b for a, b in PEAKS) else 1.0
        minutes += weighted[k] * 1.8 * peak + 0.35 * trains[k] ** 2
    minutes *= SECTION_FACTOR[section_idx % 4] * (0.85 if weekday >= 5 else 1.0)
    return max(0.0, rng.gauss(minutes, 0.08 * minutes + 1.0))


def generate_delay_data(section_codes: list[str], seed: int = 1, days: int = 120) -> Dataset:
    rng = random.Random(seed)
    base = _base_arrays(sorted(section_codes), seed)
    rows, targets, day_index, trains_raw = [], [], [], []
    for day in range(days):
        weekday = (START + timedelta(days=day)).weekday()
        for section_idx, section in enumerate(sorted(section_codes)):
            trains, weighted = (list(a) for a in base[section][weekday])
            # day-to-day variation: the odd extra train (a special, a late freight)
            for _ in range(int(rng.random() < 0.6) * rng.randint(1, 3)):
                slot = rng.randrange(SLOTS)
                trains[slot] += 1
                weighted[slot] += rng.choice([1, 2, 3, 4, 5])
            trains_cum, weighted_cum = prefix_sums(trains), prefix_sums(weighted)
            for _ in range(WINDOWS_PER_SECTION_DAY):
                slots = rng.randint(1, 12)
                start = rng.randint(0, SLOTS - slots)
                rows.append(delay_row(section_idx, start, slots, weekday, trains_cum, weighted_cum))
                targets.append(true_delay(section_idx, start, slots, weekday, trains, weighted, rng))
                day_index.append(day)
                trains_raw.append(trains_cum[start + slots] - trains_cum[start])
    from app.ml.features import DELAY_FEATURES

    return Dataset(
        np.array(rows),
        np.array(targets),
        np.array(day_index),
        list(DELAY_FEATURES),
        {"trains": np.array(trains_raw, dtype=float)},
    )


BASE_RATIO = {"track": 1.15, "ohe": 1.25, "signal": 1.05, "bridge": 1.4, "other": 1.1}


def true_overrun_ratio(work_type: str, planned: int, month: int, crew: int, rng) -> float:
    """Actual duration divided by planned: depends on the kind of work, the monsoon months, the
    size of the job and how many people are on it. Always a little noisy."""
    ratio = BASE_RATIO[work_type]
    ratio *= 1.15 if 6 <= month <= 9 else 1.0
    ratio *= 1 + 0.03 * (planned - 120) / 60
    ratio /= 1 + 0.06 * (crew - 2)
    return max(0.7, ratio * math.exp(rng.gauss(0, 0.12)))


def generate_overrun_data(section_codes: list[str], seed: int = 1, days: int = 120) -> Dataset:
    rng = random.Random(seed + 1000)
    sections = sorted(section_codes)
    rows, targets, day_index, kinds = [], [], [], []
    for day in range(days):
        month = (START + timedelta(days=day)).month
        for _ in range(REQUESTS_PER_DAY):
            work_type = rng.choice(WORK_TYPES)
            section_idx = rng.randrange(len(sections))
            planned = rng.choice([60, 90, 120, 120, 180, 240, 300])
            crew = rng.randint(1, 4)
            rows.append(overrun_row(work_type, section_idx, planned, month, crew))
            targets.append(true_overrun_ratio(work_type, planned, month, crew, rng))
            day_index.append(day)
            kinds.append(WORK_TYPES.index(work_type))
    from app.ml.features import OVERRUN_FEATURES

    return Dataset(
        np.array(rows),
        np.array(targets),
        np.array(day_index),
        list(OVERRUN_FEATURES),
        {"work_type_idx": np.array(kinds)},
    )


def time_split(days: np.ndarray, test_fraction: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """Boolean masks (train, test) that split by time: everything in the test set is later than
    everything in the training set. Never a random split, which would leak the future."""
    unique = np.unique(days)
    cutoff = unique[int(len(unique) * (1 - test_fraction))]
    return days < cutoff, days >= cutoff
