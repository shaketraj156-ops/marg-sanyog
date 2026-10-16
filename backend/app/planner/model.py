"""CP-SAT model: choose a day and start slot per request, merge requests that share a section
and day into one closure window, and minimise closures, traffic cost and postponement."""
import os
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.planner.costs import CostProvider, TrafficCountCost
from app.planner.plan import Placement, Plan, span_blocks
from app.planner.slots import prefix_sums
from app.planner.snapshot import DEPENDENCY_UNMET, NO_CAPACITY, Snapshot


@dataclass
class SolveResult:
    status: str  # OPTIMAL, FEASIBLE, INFEASIBLE, UNKNOWN, MODEL_INVALID
    plan: Plan | None = None
    objective: float | None = None
    best_bound: float | None = None
    wall_time_s: float = 0.0
    message: str | None = None  # why a solve ended without an answer (crash, time-out)

    @property
    def gap(self) -> float | None:
        if self.objective is None or self.best_bound is None:
            return None
        return max(0.0, self.objective - self.best_bound)


class StopOnFlag(cp_model.CpSolverSolutionCallback):
    """Lets a caller cancel a running solve, and watch its progress."""

    def __init__(
        self,
        should_stop: Callable[[], bool],
        progress: Callable[[float, float], None] | None = None,
    ):
        super().__init__()
        self.should_stop = should_stop
        self.progress = progress

    def on_solution_callback(self):
        if self.progress is not None:
            self.progress(self.WallTime(), self.ObjectiveValue())  # (seconds, objective)
        if self.should_stop():
            self.StopSearch()


def default_workers() -> int:
    return min(8, os.cpu_count() or 1)


def solve(
    snapshot: Snapshot,
    *,
    hints: Plan | None = None,
    fixed: dict[int, tuple[int, int]] | None = None,
    costs: CostProvider | None = None,
    time_limit_s: float = 60,
    seed: int = 1,
    workers: int | None = None,
    should_stop: Callable[[], bool] = lambda: False,
    progress: Callable[[float, float], None] | None = None,
) -> SolveResult:
    """fixed maps request id -> (day, start slot) to pin requests, as what-if and override do."""
    costs = costs or TrafficCountCost(snapshot)
    per_day, horizon_days = snapshot.per_day, snapshot.days
    forced = snapshot.forced_deferrals()
    model = cp_model.CpModel()

    x, placed, offset, day, start, interval, dur, lowest = {}, {}, {}, {}, {}, {}, {}, {}
    for request in snapshot.requests:
        i = request.id
        dur[i] = snapshot.dur(request)
        lo, hi = snapshot.window(request)
        lowest[i] = lo
        placed[i] = model.NewBoolVar(f"placed_{i}")  # False means deferred
        days = [] if i in forced else list(range(lo, hi + 1))
        if i in forced:
            model.Add(placed[i] == 0)
        for d in days:
            x[i, d] = model.NewBoolVar(f"x_{i}_{d}")
        model.Add(sum(x[i, d] for d in days) == placed[i])
        offset[i] = model.NewIntVar(0, max(0, per_day - dur[i]), f"off_{i}")
        day[i] = model.NewIntVar(lo, hi, f"day_{i}")
        model.Add(day[i] == sum(d * x[i, d] for d in days)).OnlyEnforceIf(placed[i])
        model.Add(day[i] == lo).OnlyEnforceIf(placed[i].Not())
        model.Add(offset[i] == 0).OnlyEnforceIf(placed[i].Not())
        start[i] = model.NewIntVar(0, horizon_days * per_day, f"start_{i}")
        model.Add(start[i] == day[i] * per_day + offset[i])
        interval[i] = model.NewOptionalFixedSizeIntervalVar(
            start[i], dur[i], placed[i], f"iv_{i}"
        )

    by_section = defaultdict(list)
    by_dept = defaultdict(list)
    by_dept_section = defaultdict(list)
    for request in snapshot.requests:
        by_section[request.section].append(request.id)
        by_dept[request.dept].append(request.id)
        by_dept_section[request.dept, request.section].append(request.id)

    # One closure window per section and day, covering every request assigned there.
    terms = []
    closure = {}
    for section, ids in by_section.items():
        for d in sorted({d for (i, d) in x if i in set(ids)}):
            members = [i for i in ids if (i, d) in x]
            used = model.NewBoolVar(f"closure_{section}_{d}")
            window_start = model.NewIntVar(0, per_day, f"bs_{section}_{d}")
            window_end = model.NewIntVar(0, per_day, f"be_{section}_{d}")
            for i in members:
                model.AddImplication(x[i, d], used)
                model.Add(window_start <= offset[i]).OnlyEnforceIf(x[i, d])
                model.Add(offset[i] + dur[i] <= window_end).OnlyEnforceIf(x[i, d])
            model.AddBoolOr([x[i, d] for i in members]).OnlyEnforceIf(used)
            model.Add(window_end - window_start <= snapshot.max_block_slots).OnlyEnforceIf(used)
            # Redundant but valuable: they tighten the lower bound so optimality can be proved.
            model.Add(window_end >= window_start)
            model.Add(window_start == 0).OnlyEnforceIf(used.Not())
            model.Add(window_end == 0).OnlyEnforceIf(used.Not())
            terms.append(snapshot.weight("block") * used)
            terms.append(window_end - window_start)
            cumulative = prefix_sums(costs.cost(section, d))
            at_start = at_end = None
            if cumulative[-1] > 0:
                at_start = model.NewIntVar(0, cumulative[-1], f"cs_{section}_{d}")
                at_end = model.NewIntVar(0, cumulative[-1], f"ce_{section}_{d}")
                model.AddElement(window_start, cumulative, at_start)
                model.AddElement(window_end, cumulative, at_end)
                model.Add(at_end >= at_start)  # cumulative traffic never decreases
                terms.append(snapshot.weight("traffic") * (at_end - at_start))
            closure[section, d] = (used, window_start, window_end, at_start, at_end, cumulative)

    # People: a department's work on one section cannot overlap; crews are limited.
    for ids in by_dept_section.values():
        if len(ids) > 1:
            model.AddNoOverlap([interval[i] for i in ids])
    for dept, ids in by_dept.items():
        model.AddCumulative(
            [interval[i] for i in ids], [1] * len(ids), snapshot.crew_limit(dept)
        )

    for dep in snapshot.dependencies:
        if dep.before not in placed or dep.after not in placed:
            continue
        if dep.relation == "finish_before_start":
            model.AddImplication(placed[dep.after], placed[dep.before])  # no orphan follow-ups
            model.Add(
                start[dep.before] + dur[dep.before] + snapshot.gap_slots(dep) <= start[dep.after]
            ).OnlyEnforceIf([placed[dep.before], placed[dep.after]])
        elif dep.relation == "not_same_block":
            model.Add(day[dep.before] != day[dep.after]).OnlyEnforceIf(
                [placed[dep.before], placed[dep.after]]
            )

    for request in snapshot.requests:
        i = request.id
        terms.append(snapshot.weight("delay") * request.priority * (day[i] - lowest[i]))
        terms.append(snapshot.weight("defer") * request.priority * (1 - placed[i]))
    model.Minimize(sum(terms))

    for i, (pinned_day, pinned_offset) in (fixed or {}).items():
        if i not in dur or (i, pinned_day) not in x:
            return SolveResult("INFEASIBLE")
        if not 0 <= pinned_offset <= per_day - dur[i]:
            return SolveResult("INFEASIBLE")
        model.Add(placed[i] == 1)
        model.Add(x[i, pinned_day] == 1)
        model.Add(offset[i] == pinned_offset)

    if hints is not None:
        for i, placed_var in placed.items():
            placement = hints.placements.get(i)
            if placement is None or (i, placement.day) not in x:
                # deferred requests sit at their lowest day and offset 0 (as the model forces)
                model.AddHint(placed_var, 0)
                model.AddHint(day[i], lowest[i])
                model.AddHint(offset[i], 0)
                model.AddHint(start[i], lowest[i] * per_day)
                continue
            hinted_offset = min(placement.offset, per_day - dur[i])
            model.AddHint(placed_var, 1)
            model.AddHint(day[i], placement.day)
            model.AddHint(offset[i], hinted_offset)
            model.AddHint(start[i], placement.day * per_day + hinted_offset)
            for (j, d), var in x.items():
                if j == i:
                    model.AddHint(var, int(d == placement.day))
        hinted = {(b.section, b.day): b for b in span_blocks(hints.placements.values())}
        for key, (used, w_start, w_end, at_start, at_end, cumulative) in closure.items():
            block = hinted.get(key)
            model.AddHint(used, int(block is not None))
            model.AddHint(w_start, block.start if block else 0)
            model.AddHint(w_end, block.end if block else 0)
            if at_start is not None:
                model.AddHint(at_start, cumulative[block.start] if block else 0)
                model.AddHint(at_end, cumulative[block.end] if block else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.random_seed = seed
    # Presolve is the slow part on big models (the cost lookups expand to tens of thousands of
    # variables). Skipping probing and limiting presolve to one pass gets the first plan in a few
    # seconds instead of more than ten at 200 requests, and found better plans at 16 and 50 too.
    solver.parameters.cp_model_probing_level = 0
    solver.parameters.max_presolve_iterations = 1
    # Do not set repair_hint: with several workers it aborts the whole process on tiny models
    # (OR-Tools 9.15: "Check failed: heuristics.fixed_search != nullptr"). The hints are complete.
    solver.parameters.num_workers = workers or default_workers()
    status = solver.Solve(model, StopOnFlag(should_stop, progress))
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(name, wall_time_s=solver.WallTime())

    plan = Plan()
    for request in snapshot.requests:
        i = request.id
        if solver.Value(placed[i]):
            plan.placements[i] = Placement(
                i, request.section, solver.Value(day[i]), solver.Value(offset[i]), dur[i]
            )
    for request in snapshot.requests:
        if request.id not in plan.placements:
            plan.deferred[request.id] = _deferral_reason(snapshot, plan, forced, request.id)
    plan.blocks = span_blocks(plan.placements.values())  # tight windows around the members
    return SolveResult(
        name,
        plan,
        solver.ObjectiveValue(),
        solver.BestObjectiveBound(),
        solver.WallTime(),
    )


def _deferral_reason(snapshot: Snapshot, plan: Plan, forced: dict[int, str], request_id: int) -> str:
    if request_id in forced:
        return forced[request_id]
    for dep in snapshot.dependencies:
        if (
            dep.relation == "finish_before_start"
            and dep.after == request_id
            and dep.before not in plan.placements
        ):
            return DEPENDENCY_UNMET
    return NO_CAPACITY
