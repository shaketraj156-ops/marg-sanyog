"""Benchmark the planner on synthetic instances of growing size.

    .\\.venv\\Scripts\\python -m scripts.benchmark                 (16, 50 and 200 requests)
    .\\.venv\\Scripts\\python -m scripts.benchmark --sizes 16 50 --time-limit 5

Each instance has about four requests per section over a 7-day horizon, simulated traffic, and one
ordering rule per eight requests. The solver gets a fixed time limit, so the result for the larger
sizes is usually "best found in the time" (FEASIBLE), not a proof of optimality; the script reports
the gap honestly. A total time budget keeps the whole run short: sizes that no longer fit in it
are skipped and said so.

Synthetic data only. No database is used.
"""
import argparse
import math
import os
import platform
import random
import sys
import time

DAYS = 7
DEPARTMENTS = ["ENGG", "TRD", "SNT"]
DURATIONS = [60, 90, 120, 120, 180, 240]


def build_snapshot(size: int, seed: int):
    from app.planner.snapshot import PlanDependency, PlanRequest, Snapshot
    from app.services.timetable_gen import generate_timetable

    rng = random.Random(seed)
    sections = [f"S{n:02d}" for n in range(1, max(4, math.ceil(size / 4)) + 1)]

    # simulated traffic: trains per slot (plain) and weighted, from the synthetic timetable
    cost: dict = {}
    trains: dict = {}
    for entry in generate_timetable(sections, seed=1):
        hours, minutes = map(int, entry["enters_at"].split(":"))
        slot = (hours * 60 + minutes) // 30
        for day in range(DAYS):
            if entry["days_of_week"] >> day & 1:
                cost.setdefault(entry["section_code"], {}).setdefault(day, [0] * 48)[slot] += entry["weight"]
                trains.setdefault(entry["section_code"], {}).setdefault(day, [0] * 48)[slot] += 1

    requests = []
    by_section: dict[str, list[int]] = {s: [] for s in sections}
    for index in range(size):
        section = sections[index % len(sections)]
        earliest = rng.randint(0, 3)
        requests.append(
            PlanRequest(
                id=index + 1,
                dept=rng.choice(DEPARTMENTS),
                section=section,
                duration_minutes=rng.choice(DURATIONS),
                earliest_day=earliest,
                deadline_day=min(DAYS - 1, earliest + rng.randint(1, 3)),
                priority=rng.randint(1, 3),
                pref_day=earliest,
                pref_offset=rng.choice([8, 14, 20]),
            )
        )
        by_section[section].append(index + 1)
    dependencies = []
    pairs = [ids[:2] for ids in by_section.values() if len(ids) >= 2]
    rng.shuffle(pairs)
    for before, after in pairs[: max(1, size // 8)]:
        dependencies.append(PlanDependency(before=before, after=after, relation="finish_before_start", gap_minutes=60))
    return Snapshot(
        days=DAYS,
        slot_minutes=30,
        max_block_minutes=360,
        requests=tuple(requests),
        dependencies=tuple(dependencies),
        crews=dict.fromkeys(DEPARTMENTS, 2),
        cost=cost,
        trains=trains,
    )


def run_one(size: int, time_limit: int, seed: int, workers: int | None) -> dict:
    from app.planner.baseline import baseline_plan
    from app.planner.checker import check_plan
    from app.planner.metrics import compute_metrics
    from app.planner.model import solve
    from app.planner.warmstart import greedy_plan

    started = time.perf_counter()
    snapshot = build_snapshot(size, seed)
    baseline = baseline_plan(snapshot)
    prepared = time.perf_counter()

    first: list[float] = []
    improvements: list[float] = []

    def progress(seconds: float, objective: float) -> None:
        if not first:
            first.append(seconds)
        improvements.append(seconds)

    start = greedy_plan(snapshot)
    solve_started = time.perf_counter()
    result = solve(snapshot, hints=start, time_limit_s=time_limit, workers=workers, progress=progress)
    solve_time = time.perf_counter() - solve_started
    plan, status = result.plan, result.status
    if plan is None and status == "UNKNOWN":
        # what a plan run does: keep the valid starting plan when the solver ran out of time
        plan, status = start, "START-ONLY"

    row = {
        "size": size,
        "sections": len({r.section for r in snapshot.requests}),
        "status": status,
        "prepare_s": round(prepared - started, 1),
        "solve_call_s": round(solve_time, 1),
        "first_solution_s": round(first[0], 1) if first else None,
        "last_improvement_s": round(improvements[-1], 1) if improvements else None,
    }
    if plan is None:
        return row | {"violations": None}
    violations = check_plan(snapshot, plan)
    base, best = compute_metrics(snapshot, baseline), compute_metrics(snapshot, plan)
    gap = None
    if status != "START-ONLY" and result.objective is not None and result.best_bound is not None and result.objective:
        gap = round(100 * max(0.0, result.objective - result.best_bound) / abs(result.objective), 1)
    return row | {
        "violations": len(violations),
        "gap_percent": gap,
        "closures": (base["closures"], best["closures"]),
        "block_hours": (base["block_hours"], best["block_hours"]),
        "trains": (base["trains_affected"], best["trains_affected"]),
        "deferred": best["deferred"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the block planner on synthetic instances.")
    parser.add_argument("--sizes", type=int, nargs="+", default=[16, 50, 200])
    parser.add_argument("--time-limit", type=int, default=10, help="solver time limit per size, seconds")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--workers", type=int, default=None, help="solver workers (default: one per core, at most 8)")
    parser.add_argument("--budget", type=int, default=110, help="stop starting new sizes after this many seconds")
    args = parser.parse_args()

    sys.path.insert(0, os.getcwd())
    from ortools import __version__ as ortools_version

    from app.planner.model import default_workers

    workers = args.workers or default_workers()
    print(f"Synthetic data only. {os.cpu_count()} CPU cores, solver workers {workers}, "
          f"OR-Tools {ortools_version}, Python {platform.python_version()}, "
          f"time limit {args.time_limit} s per size, seed {args.seed}.")
    began = time.perf_counter()
    rows = []
    for size in args.sizes:
        elapsed = time.perf_counter() - began
        if elapsed + args.time_limit + 15 > args.budget:
            print(f"  skipping {size} requests: the {args.budget} s budget would be exceeded")
            continue
        print(f"  running {size} requests ...", flush=True)
        rows.append(run_one(size, args.time_limit, args.seed, workers))

    print()
    head = (f"{'requests':>8} {'sect.':>5} {'status':>9} {'first sol.':>10} {'last impr.':>10} {'gap %':>6} "
            f"{'closures':>10} {'block hours':>14} {'trains':>10} {'deferred':>8} {'violations':>10}")
    print(head)
    print("-" * len(head))
    for r in rows:
        if "closures" not in r:
            print(f"{r['size']:>8} {r['sections']:>5} {r['status']:>9}   (no plan)")
            continue
        pair = lambda p: f"{p[0]:g} -> {p[1]:g}"
        print(f"{r['size']:>8} {r['sections']:>5} {r['status']:>9} {str(r['first_solution_s']) + ' s':>10} "
              f"{str(r['last_improvement_s']) + ' s':>10} {r['gap_percent']!s:>6} "
              f"{pair(r['closures']):>10} {pair(r['block_hours']):>14} {pair(r['trains']):>10} "
              f"{r['deferred']:>8} {r['violations']:>10}")
    print()
    print("closures, block hours and trains: independent planning -> integrated plan")
    print(f"total time {time.perf_counter() - began:.0f} s")
    bad = [r for r in rows if r.get("violations")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
