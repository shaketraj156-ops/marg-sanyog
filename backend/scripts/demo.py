"""End-to-end demo on synthetic data.

    .\\.venv\\Scripts\\python -m scripts.demo            (from the backend folder)

It builds a throwaway database (demo.db), seeds the reference data, generates a synthetic
timetable and traffic profile, creates 16 block requests across 4 sections for 7 days, runs the
planner, and prints independent planning (baseline) against the integrated plan.

Everything here is invented. The demo never touches your real database (blockplanner.db).
"""
import argparse
import os
import random
import secrets
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DEMO_DB = BACKEND / "demo.db"
HORIZON_START = date(2026, 10, 19)  # a Monday
DAYS = 7

# Work that each department typically asks for: (work type, hour range for its preferred start)
DEPARTMENTS = {
    "ENGG": ("track", (9, 15)),
    "TRD": ("ohe", (3, 6)),
    "SNT": ("signal", (6, 12)),
}
SECTIONS = ["A-B", "B-C", "C-D", "D-E"]
DURATIONS = [60, 90, 120, 120, 180, 240]


def configure_environment(db_path: Path) -> None:
    """Point the app at the demo database before any app module reads its settings."""
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))  # random, never stored
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))


def build_database(db_path: Path, keep: bool) -> None:
    from alembic import command
    from alembic.config import Config

    if db_path.exists() and not keep:
        db_path.unlink()
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")


def make_requests(db, planner, seed: int) -> list[int]:
    """16 requests, 4 per section, with overlapping date windows so coordination pays off."""
    from app.core.timeutil import IST
    from app.schemas.request import BlockRequestIn, DependenciesIn, DependencyIn
    from app.services import request_service as svc

    rng = random.Random(seed)
    ids: list[int] = []
    by_section: dict[str, list[int]] = {s: [] for s in SECTIONS}
    dept_cycle = list(DEPARTMENTS)
    for index in range(16):
        section = SECTIONS[index % 4]
        dept = dept_cycle[(index // 4 + index) % 3]
        work_type, (first_hour, last_hour) = DEPARTMENTS[dept]
        earliest = rng.randint(0, 3)
        deadline = min(DAYS - 1, earliest + rng.randint(1, 3))
        preferred_day = rng.randint(earliest, deadline)
        hour = rng.randint(first_hour, last_hour)
        preferred = datetime.combine(
            HORIZON_START + timedelta(days=preferred_day), datetime.min.time(), tzinfo=IST
        ).replace(hour=hour, minute=rng.choice([0, 30]))
        body = BlockRequestIn(
            section_code=section,
            work_type=work_type,
            duration_minutes=rng.choice(DURATIONS),
            earliest_date=HORIZON_START + timedelta(days=earliest),
            deadline_date=HORIZON_START + timedelta(days=deadline),
            priority=rng.randint(1, 3),
            preferred_start=preferred,
            description=f"Synthetic {work_type} work on {section}",
            department_code=dept,
        )
        request, _ = svc.create_request(db, planner, body)
        ids.append(request.id)
        by_section[section].append(request.id)

    # Two ordering rules, for example "track work must finish before signal testing".
    for section in SECTIONS[:2]:
        first, second = by_section[section][:2]
        svc.replace_dependencies(
            db,
            planner,
            second,
            DependenciesIn(
                dependencies=[DependencyIn(depends_on=first, min_gap_minutes=60)]
            ),
        )
    for request_id in ids:
        svc.submit_request(db, planner, request_id, None)
    return ids


def money(value) -> str:
    return f"{value:,.1f}" if isinstance(value, float) else f"{value:,}"


def print_comparison(metrics: dict) -> None:
    rows = [
        ("Closures", "closures"),
        ("Block hours", "block_hours"),
        ("Trains affected", "trains_affected"),
        ("Traffic cost (weighted)", "traffic_cost"),
        ("Postponement (priority-weighted days)", "weighted_postponement_days"),
        ("Requests deferred", "deferred"),
    ]
    print()
    print(f"{'':40}{'Independent':>13}{'Integrated':>12}{'Change':>14}")
    print("-" * 79)
    for title, key in rows:
        before, after = metrics["baseline"][key], metrics["integrated"][key]
        change = ""
        if before:
            change = f"{(after - before) / before * 100:+.0f}%"
        elif after:
            change = "n/a"
        print(f"{title:40}{money(before):>13}{money(after):>12}{change:>14}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the block planner demo on synthetic data.")
    parser.add_argument("--seed", type=int, default=7, help="seed for the synthetic requests")
    parser.add_argument("--time-limit", type=int, default=30, help="solver time limit in seconds")
    parser.add_argument("--keep", action="store_true", help="reuse the demo database")
    parser.add_argument("--db", type=Path, default=DEMO_DB, help="demo database file (default demo.db)")
    args = parser.parse_args()
    db_path = args.db.resolve()

    configure_environment(db_path)
    build_database(db_path, args.keep)

    from sqlalchemy import select

    from app.config import get_settings
    from app.core.timeutil import IST
    from app.db.models import User
    from app.db.session import get_session
    from app.planner.model import default_workers
    from app.schemas.plan import PlanCreateIn
    from app.schemas.traffic import TimetableEntryIn
    from app.services import plan_runner, plan_service, review_service, traffic_service
    from app.services.timetable_gen import generate_timetable
    from scripts.seed_synthetic import seed

    with get_session() as db:
        seed(db, secrets.token_urlsafe(16))  # demo users get a random, discarded password
        planner = db.scalar(select(User).where(User.email == "planner@blockplanner.test"))

        print("Synthetic data only. Building the demo ...")
        timetable = [TimetableEntryIn(**e) for e in generate_timetable(SECTIONS, seed=1)]
        traffic_service.add_entries(db, timetable, replace=True)
        profile = traffic_service.rebuild_profile(
            db, HORIZON_START, HORIZON_START + timedelta(days=DAYS - 1)
        )
        print(f"  timetable: {len(timetable)} trains across {len(SECTIONS)} sections; "
              f"traffic profile: {profile['rows']} slot rows for {DAYS} days")
        ids = make_requests(db, planner, args.seed)
        print(f"  requests: {len(ids)} submitted across {len(SECTIONS)} sections "
              f"(2 with ordering rules)")

        body = PlanCreateIn(
            horizon_start=datetime.combine(HORIZON_START, datetime.min.time(), tzinfo=IST),
            horizon_end=datetime.combine(
                HORIZON_START + timedelta(days=DAYS), datetime.min.time(), tzinfo=IST
            ),
            time_limit_s=args.time_limit,
        )
        run, _ = plan_service.create_run(db, planner, body, None)
        workers = get_settings().solver_workers or default_workers()
        print(f"Solving (up to {args.time_limit} s, {workers} workers) ...")
        plan_runner.run_plan(run.id)
        db.expire_all()
        run = plan_service.get_run_or_404(db, run.id)

        if run.status != "succeeded":
            print(f"The plan run ended as {run.status}: {run.error}")
            return 1

        solver = run.metrics["solver"]
        proof = "proved optimal" if run.solver_status == "OPTIMAL" else (
            f"best found in the time limit (gap {solver['gap']:.0f} objective points)"
        )
        print(f"Plan {run.id}: {run.solver_status} - {proof}, {solver['wall_time_s']} s")
        print_comparison(run.metrics)

        print("Integrated schedule")
        print("-" * 79)
        schedule = plan_service.schedule(db, run)
        for block in schedule["blocks"]:
            day = datetime.fromisoformat(block["start"])
            members = "; ".join(
                f"{m['request']} {m['dept']} {m['start']}-{m['end']}" for m in block["members"]
            )
            print(
                f"{day:%a %d %b}  {block['section_code']}  {block['start'][11:16]}-{block['end'][11:16]}"
                f"  {block['trains_affected']:>3} trains  {members}"
            )
        for item in schedule["deferred"]:
            print(f"NOT PLACED  {item['request']}  ({item['reason']})")

        print()
        print("Why (reason codes)")
        print("-" * 79)
        shown: dict[str, int] = {}
        for explanation in review_service.explanations(db, run, None, None, None):
            if shown.get(explanation.code, 0) < 3:
                shown[explanation.code] = shown.get(explanation.code, 0) + 1
                print(f"[{explanation.code}] {explanation.text}")

        print()
        print(f"Done. Plan {run.id} is in {db_path.name}. Re-run with --keep to reuse the data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
