from datetime import date, timedelta

import pytest

from app.db.models import Block, TimetableEntry, TrafficProfile
from app.services import traffic_service
from app.services.timetable_gen import generate_timetable
from tests.conftest import HORIZON

URL = "/api/v1/traffic"
MONDAY = date(2026, 10, 19)


def entry(**overrides):
    row = {
        "train_no": "12001",
        "category": "premium",
        "section_code": "A-B",
        "days_of_week": 127,
        "enters_at": "08:00",
        "leaves_at": "08:30",
    }
    row.update(overrides)
    return row


def upload(client, world, entries, who="planner", **extra):
    return client.post(
        f"{URL}/timetable", json={"entries": entries, **extra}, headers=world.h(who)
    )


def rebuild(client, world, start=MONDAY, days=7, who="planner"):
    return client.post(
        f"{URL}/rebuild",
        json={"date_from": start.isoformat(), "date_to": (start + timedelta(days=days - 1)).isoformat()},
        headers=world.h(who),
    )


def profile(client, world, section="A-B", start=MONDAY, days=1, who="viewer"):
    return client.get(
        f"{URL}/profile",
        params={
            "section": section,
            "date_from": start.isoformat(),
            "date_to": (start + timedelta(days=days - 1)).isoformat(),
        },
        headers=world.h(who),
    )


# ---------- upload ----------


def test_upload_json(client, world, db):
    response = upload(client, world, [entry(), entry(train_no="12002", category="freight")])
    assert response.status_code == 201
    assert response.json() == {"inserted": 2}
    rows = db.query(TimetableEntry).order_by(TimetableEntry.id).all()
    assert [r.weight for r in rows] == [5, 1]  # defaults come from the category
    assert rows[0].enters_at.hour == 8


def test_upload_keeps_an_explicit_weight(client, world, db):
    upload(client, world, [entry(weight=9)])
    assert db.query(TimetableEntry).one().weight == 9


def test_upload_appends_unless_replace_is_set(client, world, db):
    upload(client, world, [entry()])
    upload(client, world, [entry(train_no="2")])
    assert db.query(TimetableEntry).count() == 2
    upload(client, world, [entry(train_no="3")], replace=True)
    assert [r.train_no for r in db.query(TimetableEntry)] == ["3"]


def test_unknown_section_is_422_and_nothing_is_saved(client, world, db):
    response = upload(client, world, [entry(), entry(section_code="Z-Z")])
    assert response.status_code == 422
    assert response.json()["title"] == "unknown_section"
    assert db.query(TimetableEntry).count() == 0


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"category": "rocket"}, "entries.0.category"),
        ({"weight": 0}, "entries.0.weight"),
        ({"days_of_week": 0}, "entries.0.days_of_week"),
        ({"days_of_week": 128}, "entries.0.days_of_week"),
        ({"enters_at": "8am"}, "entries.0.enters_at"),
        ({"train_no": ""}, "entries.0.train_no"),
        ({"surprise": 1}, "entries.0.surprise"),
    ],
)
def test_invalid_entries_are_rejected(client, world, overrides, field):
    response = upload(client, world, [entry(**overrides)])
    assert response.status_code == 422
    assert any(e["field"] == field for e in response.json()["errors"]), response.json()


def test_malformed_json_is_400(client, world):
    response = client.post(
        f"{URL}/timetable",
        content=b"{not json",
        headers={**world.h("planner"), "Content-Type": "application/json"},
    )
    assert response.status_code == 400


def test_upload_roles(client, world):
    for who, expected in [("planner", 201), ("admin", 201), ("engg", 403), ("viewer", 403)]:
        assert upload(client, world, [entry()], who=who).status_code == expected
    assert client.post(f"{URL}/timetable", json={"entries": []}).status_code == 401


def test_upload_csv(client, world, db):
    csv_text = (
        "train_no,category,section_code,enters_at,leaves_at,weight,days_of_week\n"
        "12001,premium,A-B,08:00,08:30,,\n"
        "56001,passenger,B-C,09:15,09:50,4,31\n"
    )
    response = client.post(
        f"{URL}/timetable", content=csv_text, headers={**world.h("planner"), "Content-Type": "text/csv"}
    )
    assert response.status_code == 201
    assert response.json() == {"inserted": 2}
    first, second = db.query(TimetableEntry).order_by(TimetableEntry.id).all()
    assert (first.weight, first.days_of_week) == (5, 127)
    assert (second.weight, second.days_of_week) == (4, 31)
    assert second.enters_at.minute == 15


def test_csv_with_a_bom_and_replace_flag(client, world, db):
    upload(client, world, [entry()])
    body = "﻿train_no,category,section_code,enters_at,leaves_at\n9,mail,A-B,01:00,01:30\n"
    response = client.post(
        f"{URL}/timetable?replace=true",
        content=body.encode("utf-8"),
        headers={**world.h("planner"), "Content-Type": "text/csv; charset=utf-8"},
    )
    assert response.status_code == 201
    assert [r.train_no for r in db.query(TimetableEntry)] == ["9"]


def test_csv_errors_name_the_row(client, world, db):
    csv_text = (
        "train_no,category,section_code,enters_at,leaves_at\n"
        "1,premium,A-B,08:00,08:30\n"
        "2,rocket,A-B,09:00,09:30\n"
        "3,mail,A-B,noon,09:30\n"
    )
    response = client.post(
        f"{URL}/timetable", content=csv_text, headers={**world.h("planner"), "Content-Type": "text/csv"}
    )
    assert response.status_code == 422
    fields = [e["field"] for e in response.json()["errors"]]
    assert "row 3: category" in fields and "row 4: enters_at" in fields
    assert db.query(TimetableEntry).count() == 0


def test_csv_missing_columns(client, world):
    response = client.post(
        f"{URL}/timetable",
        content="train_no,category\n1,mail\n",
        headers={**world.h("planner"), "Content-Type": "text/csv"},
    )
    assert response.status_code == 422
    assert "section_code" in response.json()["errors"][0]["message"]


def test_csv_bad_number(client, world):
    csv_text = "train_no,category,section_code,enters_at,leaves_at,weight\n1,mail,A-B,01:00,01:30,heavy\n"
    response = client.post(
        f"{URL}/timetable", content=csv_text, headers={**world.h("planner"), "Content-Type": "text/csv"}
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "row 2: weight"


def test_synthetic_timetable(client, world, db):
    response = client.post(f"{URL}/synthetic", json={"seed": 5}, headers=world.h("planner"))
    assert response.status_code == 201
    expected = generate_timetable(["A-B", "B-C", "C-D", "D-E"], seed=5)
    assert response.json() == {"inserted": len(expected)}
    assert db.query(TimetableEntry).count() == len(expected)
    # replace is the default, so a second call does not double the timetable
    client.post(f"{URL}/synthetic", headers=world.h("admin"))
    assert db.query(TimetableEntry).count() == len(expected)
    assert client.post(f"{URL}/synthetic", headers=world.h("engg")).status_code == 403


# ---------- the profile ----------


def test_profile_counts_trains_in_the_entry_slot(client, world):
    upload(
        client,
        world,
        [
            entry(train_no="1", enters_at="08:00"),
            entry(train_no="2", enters_at="08:25", category="freight"),
            entry(train_no="3", enters_at="08:30", category="local"),
        ],
    )
    assert rebuild(client, world).status_code == 200
    day = profile(client, world).json()["days"][0]
    assert day["trains"][16] == 2 and day["weighted"][16] == 5 + 1  # 08:00-08:30
    assert day["trains"][17] == 1 and day["weighted"][17] == 2  # 08:30-09:00
    assert sum(day["trains"]) == 3
    assert len(day["trains"]) == 48


def test_profile_respects_days_of_week(client, world):
    upload(client, world, [entry(days_of_week=0b0000001)])  # Mondays only
    rebuild(client, world, days=7)
    body = profile(client, world, days=7).json()
    totals = {d["date"]: sum(d["trains"]) for d in body["days"]}
    assert totals[MONDAY.isoformat()] == 1
    assert sum(totals.values()) == 1


def test_rebuild_is_idempotent(client, world, db):
    upload(client, world, [entry(), entry(train_no="2", enters_at="03:00")])
    first = rebuild(client, world).json()
    second = rebuild(client, world).json()
    assert first == second == {"days": 7, "sections": 1, "rows": 14}
    assert db.query(TrafficProfile).count() == 14


def test_rebuild_only_touches_its_date_range(client, world, db):
    upload(client, world, [entry()])
    rebuild(client, world, days=3)
    upload(client, world, [entry(train_no="2", enters_at="02:00")])
    rebuild(client, world, start=MONDAY + timedelta(days=1), days=1)
    days = {d["date"]: sum(d["trains"]) for d in profile(client, world, days=3).json()["days"]}
    assert days[MONDAY.isoformat()] == 1  # untouched
    assert days[(MONDAY + timedelta(days=1)).isoformat()] == 2  # rebuilt with the new train
    assert days[(MONDAY + timedelta(days=2)).isoformat()] == 1  # untouched


def test_rebuild_after_the_timetable_changes(client, world):
    upload(client, world, [entry()])
    rebuild(client, world, days=1)
    upload(client, world, [], replace=True)
    rebuild(client, world, days=1)
    assert sum(profile(client, world).json()["days"][0]["trains"]) == 0


def test_profile_matches_the_generator(client, world):
    """Every section, day and slot of the stored profile equals an independent count."""
    sections = ["A-B", "B-C", "C-D", "D-E"]
    generated = generate_timetable(sections, seed=11)
    assert upload(client, world, generated).status_code == 201
    assert rebuild(client, world, days=7).status_code == 200
    for section in sections:
        body = profile(client, world, section=section, days=7).json()
        for offset, day in enumerate(body["days"]):
            weekday = (MONDAY + timedelta(days=offset)).weekday()
            expected_trains, expected_weighted = [0] * 48, [0] * 48
            for e in generated:
                if e["section_code"] == section and e["days_of_week"] >> weekday & 1:
                    hours, minutes = map(int, e["enters_at"].split(":"))
                    slot = (hours * 60 + minutes) // 30
                    expected_trains[slot] += 1
                    expected_weighted[slot] += e["weight"]
            assert day["trains"] == expected_trains, (section, day["date"])
            assert day["weighted"] == expected_weighted, (section, day["date"])


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"date_from": "2026-10-20", "date_to": "2026-10-19"}, "date_to"),
        ({"date_from": "2026-10-01", "date_to": "2027-01-01"}, "date_to"),
    ],
)
def test_rebuild_range_validation(client, world, body, field):
    response = client.post(f"{URL}/rebuild", json=body, headers=world.h("planner"))
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field


def test_rebuild_roles(client, world):
    assert rebuild(client, world, who="engg").status_code == 403
    assert rebuild(client, world, who="viewer").status_code == 403
    assert rebuild(client, world, who="admin").status_code == 200


def test_profile_validation_and_roles(client, world):
    assert profile(client, world, section="Z-Z").status_code == 404
    assert profile(client, world, days=40).status_code == 422
    assert client.get(f"{URL}/profile", params={"section": "A-B"}, headers=world.h("viewer")).status_code == 422
    for who in ("engg", "viewer", "planner"):
        assert profile(client, world, who=who).status_code == 200
    assert client.get(f"{URL}/profile?section=A-B&date_from=2026-10-19&date_to=2026-10-19").status_code == 401


def test_empty_profile_is_all_zeros(client, world):
    day = profile(client, world).json()["days"][0]
    assert day["trains"] == [0] * 48 and day["weighted"] == [0] * 48


def test_load_arrays_returns_only_sections_with_traffic(client, world, db):
    upload(client, world, [entry()])
    rebuild(client, world)
    cost, trains = traffic_service.load_arrays(db, ["A-B", "B-C"], MONDAY, 7, 30)
    assert set(cost) == set(trains) == {"A-B"}
    assert set(cost["A-B"]) == set(range(7))  # the entry runs every day of the week
    assert len(cost["A-B"][0]) == 48


def test_uploads_and_rebuilds_are_audited(client, world, db):
    from app.db.models import AuditLog

    upload(client, world, [entry()])
    rebuild(client, world)
    actions = [r.action for r in db.query(AuditLog).order_by(AuditLog.id)]
    assert actions == ["traffic.timetable", "traffic.rebuild"]


# ---------- the planner uses the traffic ----------


def test_the_planner_moves_work_into_the_quiet_hours(
    client, world, submit_request, inline_planner, monkeypatch
):
    from app.config import get_settings

    # Asserting the optimal window needs a proved optimum, which one worker is too slow to reach.
    monkeypatch.setattr(get_settings(), "solver_workers", 8)
    client.post(f"{URL}/synthetic", json={"seed": 1}, headers=world.h("planner"))
    rebuild(client, world, days=7)
    for who, section in [("engg", "A-B"), ("trd", "B-C"), ("snt", "C-D")]:
        submit_request(who, section_code=section, duration_minutes=120, earliest_date="2026-10-19", deadline_date="2026-10-23")
    created = client.post(
        "/api/v1/plans", json={**HORIZON, "time_limit_s": 30}, headers=world.h("planner")
    ).json()
    plan = client.get(f"/api/v1/plans/{created['id']}", headers=world.h("viewer")).json()
    assert plan["status"] == "succeeded"
    assert plan["solver_status"] == "OPTIMAL"
    baseline, integrated = plan["metrics"]["baseline"], plan["metrics"]["integrated"]
    # The planner minimises the weighted traffic cost, so that must drop strictly; the plain
    # train count can tie when a cheaper window happens to hold equally many (lighter) trains.
    assert integrated["traffic_cost"] < baseline["traffic_cost"]
    assert integrated["trains_affected"] <= baseline["trains_affected"]
    assert baseline["trains_affected"] > 0

    schedule = client.get(f"/api/v1/plans/{created['id']}/schedule", headers=world.h("viewer")).json()
    for block in schedule["blocks"]:
        # On its chosen day, each closure sits in the cheapest window of its length.
        day = date.fromisoformat(block["start"][:10])
        weighted = profile(client, world, section=block["section_code"], start=day).json()["days"][0]["weighted"]
        first = int(block["start"][11:13]) * 2 + int(block["start"][14:16]) // 30
        last = int(block["end"][11:13]) * 2 + int(block["end"][14:16]) // 30
        width = last - first
        chosen = sum(weighted[first:last])
        cheapest = min(sum(weighted[i : i + width]) for i in range(48 - width + 1))
        assert chosen == cheapest, (block["section_code"], day, first, last)
    assert sum(b["trains_affected"] for b in schedule["blocks"]) == integrated["trains_affected"]


def test_block_rows_store_the_trains_affected(client, world, submit_request, inline_planner, db):
    upload(client, world, [entry(enters_at="00:10"), entry(train_no="2", enters_at="00:40")])
    rebuild(client, world)
    submit_request("engg", duration_minutes=60, earliest_date="2026-10-19", deadline_date="2026-10-19")
    created = client.post("/api/v1/plans", json=HORIZON, headers=world.h("planner")).json()
    block = db.query(Block).filter_by(plan_run_id=created["id"]).one()
    assert block.trains_affected >= 0
    plan = client.get(f"/api/v1/plans/{created['id']}", headers=world.h("viewer")).json()
    assert plan["metrics"]["integrated"]["trains_affected"] == block.trains_affected


def test_plans_without_traffic_still_work(client, world, submit_request, inline_planner):
    submit_request("engg")
    created = client.post("/api/v1/plans", json=HORIZON, headers=world.h("planner")).json()
    plan = client.get(f"/api/v1/plans/{created['id']}", headers=world.h("viewer")).json()
    assert plan["status"] == "succeeded"
    assert plan["metrics"]["integrated"]["trains_affected"] == 0
