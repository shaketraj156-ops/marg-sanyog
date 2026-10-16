from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import PlanRun
from app.main import app
from tests.conftest import HORIZON


def make_run(db, user_id, status="queued", age_seconds=0):
    run = PlanRun(
        created_by=user_id,
        horizon_start=datetime(2026, 10, 18, 18, 30, tzinfo=UTC),
        horizon_end=datetime(2026, 10, 25, 18, 30, tzinfo=UTC),
        weights={},
        status=status,
    )
    db.add(run)
    db.commit()
    run.created_at = datetime.now(UTC) - timedelta(seconds=age_seconds)
    db.commit()
    return run


def test_ready_when_everything_is_fine(client, world):
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["schema"] == "ok"
    assert body["checks"]["solver"] == "ok"
    assert body["checks"]["planner"] == {"status": "ok", "queued": 0, "running": 0, "oldest_queued_seconds": 0}


def test_ready_needs_no_login(client):
    assert client.get("/ready").status_code == 200


def test_the_plan_queue_is_reported(client, world, db):
    make_run(db, 1, "queued", age_seconds=30)
    make_run(db, 1, "running")
    planner = client.get("/ready").json()["checks"]["planner"]
    assert (planner["queued"], planner["running"]) == (1, 1)
    assert planner["status"] == "ok"
    assert 25 <= planner["oldest_queued_seconds"] <= 120


def test_a_queue_that_is_not_moving_is_not_ready(client, world, db):
    make_run(db, 1, "queued", age_seconds=3600)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["planner"]["status"] == "stalled"


def test_a_long_queue_behind_a_running_plan_is_still_ready(client, world, db):
    make_run(db, 1, "running")
    make_run(db, 1, "queued", age_seconds=3600)
    assert client.get("/ready").status_code == 200


def test_not_ready_when_the_database_cannot_be_reached(client):
    class Broken:
        def execute(self, *args, **kwargs):
            raise RuntimeError("connection lost")

        def rollback(self):
            pass

        def close(self):
            pass

    app.dependency_overrides[get_db] = lambda: iter([Broken()])
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"
    assert client.get("/health").status_code == 200  # liveness does not depend on the database


def test_not_ready_when_the_tables_are_missing(client):
    engine = create_engine("sqlite://")  # empty database: migrations were not run

    def empty_database():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = empty_database
    response = client.get("/ready")
    assert response.status_code == 503
    checks = response.json()["checks"]
    assert checks["database"] == "ok"
    assert "alembic upgrade head" in checks["schema"]


def test_plans_can_still_be_created_while_ready(client, world, inline_planner):
    assert client.post("/api/v1/plans", json=HORIZON, headers=world.h("planner")).status_code == 202
    assert client.get("/ready").json()["checks"]["planner"]["queued"] == 0
