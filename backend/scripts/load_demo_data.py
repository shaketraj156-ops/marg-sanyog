"""Put demo data into the application's own database, for a presentation in the web interface.

    .\\.venv\\Scripts\\python -m scripts.load_demo_data           (from the backend folder)

It loads a simulated timetable and traffic for 7 days from Monday 19 October 2026 and creates 16
synthetic block requests across the 4 demo sections, all submitted and ready to plan. Then open
the web interface, log in as the planner and run a plan.

Unlike scripts/demo.py (which uses its own throwaway database) this writes to the database in your
settings (DATABASE_URL). It refuses to run if requests already exist, unless you pass --add.
The reference data and demo users must exist first (scripts/seed_synthetic.py).

Everything here is synthetic.
"""
import argparse
import sys
from datetime import timedelta


def main() -> int:
    parser = argparse.ArgumentParser(description="Load synthetic demo requests and traffic.")
    parser.add_argument("--seed", type=int, default=7, help="seed for the synthetic requests")
    parser.add_argument("--add", action="store_true", help="add even if requests already exist")
    args = parser.parse_args()

    from sqlalchemy import func, select

    from app.db.models import BlockRequest, Section, User
    from app.db.session import get_session
    from app.schemas.traffic import TimetableEntryIn
    from app.services import traffic_service
    from app.services.timetable_gen import generate_timetable
    from scripts.demo import DAYS, HORIZON_START, SECTIONS, make_requests

    with get_session() as db:
        planner = db.scalar(select(User).where(User.email == "planner@blockplanner.test"))
        have = set(db.scalars(select(Section.code)))
        if planner is None or not set(SECTIONS) <= have:
            print(
                "The demo users and sections are missing. Run the seed script first:\n"
                "  $env:SEED_PASSWORD = 'pick-a-password'\n"
                "  .\\.venv\\Scripts\\python -m scripts.seed_synthetic",
                file=sys.stderr,
            )
            return 1
        existing = db.scalar(select(func.count()).select_from(BlockRequest))
        if existing and not args.add:
            print(
                f"This database already has {existing} requests, so nothing was loaded.\n"
                "Use --add to add 16 more anyway.",
                file=sys.stderr,
            )
            return 1

        timetable = [TimetableEntryIn(**e) for e in generate_timetable(SECTIONS, seed=1)]
        traffic_service.add_entries(db, timetable, replace=True)
        profile = traffic_service.rebuild_profile(
            db, HORIZON_START, HORIZON_START + timedelta(days=DAYS - 1)
        )
        ids = make_requests(db, planner, args.seed)
        print(
            f"Loaded {len(timetable)} simulated trains ({profile['rows']} traffic slot rows for "
            f"{DAYS} days) and {len(ids)} submitted requests (R{ids[0]} to R{ids[-1]})."
        )
        print("Next: open http://localhost:5173, log in as planner@blockplanner.test, go to Plans.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
