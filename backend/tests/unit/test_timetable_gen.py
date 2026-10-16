from collections import Counter

from app.db.models.traffic import CATEGORIES, CATEGORY_WEIGHT
from app.schemas.traffic import TimetableEntryIn
from app.services.timetable_gen import PATTERNS, generate_timetable

SECTIONS = ["A-B", "B-C", "C-D", "D-E"]


def test_generation_is_deterministic_for_a_seed():
    assert generate_timetable(SECTIONS, seed=3) == generate_timetable(SECTIONS, seed=3)
    assert generate_timetable(SECTIONS, seed=3) != generate_timetable(SECTIONS, seed=4)


def test_section_order_does_not_matter():
    assert generate_timetable(SECTIONS, seed=1) == generate_timetable(SECTIONS[::-1], seed=1)


def test_every_section_gets_the_same_category_mix():
    entries = generate_timetable(SECTIONS)
    per_section = Counter(e["section_code"] for e in entries)
    assert set(per_section.values()) == {sum(count for count, _, _ in PATTERNS.values())}
    for section in SECTIONS:
        categories = Counter(e["category"] for e in entries if e["section_code"] == section)
        assert categories == {name: spec[0] for name, spec in PATTERNS.items()}


def test_entries_are_valid_upload_rows():
    for entry in generate_timetable(SECTIONS):
        row = TimetableEntryIn(**entry)
        assert row.category in CATEGORIES
        assert row.weight == CATEGORY_WEIGHT[row.category]
        assert 1 <= row.days_of_week <= 127


def test_train_numbers_are_unique():
    numbers = [e["train_no"] for e in generate_timetable(SECTIONS)]
    assert len(numbers) == len(set(numbers))


def test_premium_trains_weigh_more_than_freight():
    assert CATEGORY_WEIGHT["premium"] > CATEGORY_WEIGHT["freight"]


def test_the_small_hours_are_quieter_than_the_day():
    entries = generate_timetable(SECTIONS, seed=1)

    def weighted_per_hour(hours):
        total = sum(
            e["weight"]
            for e in entries
            if int(e["enters_at"][:2]) in hours and e["days_of_week"] == 127
        )
        return total / len(hours)

    assert weighted_per_hour(range(1, 5)) < weighted_per_hour(range(7, 20))


def test_times_are_hh_mm_on_five_minute_marks():
    for entry in generate_timetable(SECTIONS):
        for key in ("enters_at", "leaves_at"):
            hours, minutes = entry[key].split(":")
            assert 0 <= int(hours) < 24 and 0 <= int(minutes) < 60
        assert int(entry["enters_at"][3:]) % 5 == 0
