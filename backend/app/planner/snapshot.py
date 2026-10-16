"""Immutable input for one planning run. No database or HTTP imports in this package."""
import hashlib
import json
from dataclasses import asdict, dataclass, field

from app.planner.slots import duration_slots, slots_per_day

OUT_OF_HORIZON = "OUT_OF_HORIZON"
TOO_LONG = "TOO_LONG"
DEPENDENCY_UNMET = "DEPENDENCY_UNMET"
NO_CAPACITY = "NO_CAPACITY"

DEFAULT_WEIGHTS = {"block": 150, "traffic": 10, "delay": 20, "defer": 1000}


@dataclass(frozen=True)
class PlanRequest:
    id: int
    dept: str
    section: str
    duration_minutes: int
    earliest_day: int  # day index from the horizon start; may lie outside the horizon
    deadline_day: int
    priority: int
    version: int = 1
    pref_day: int | None = None  # preferred start, used only by the baseline
    pref_offset: int | None = None


@dataclass(frozen=True)
class PlanDependency:
    before: int  # request that must come first
    after: int
    relation: str  # finish_before_start | not_same_block | same_block_allowed
    gap_minutes: int = 0


@dataclass(frozen=True)
class Snapshot:
    days: int
    slot_minutes: int
    max_block_minutes: int
    requests: tuple[PlanRequest, ...]
    dependencies: tuple[PlanDependency, ...] = ()
    crews: dict[str, int] = field(default_factory=dict)  # crews available per department
    default_crews: int = 2
    weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    # section -> day -> list of per-slot values; missing entries mean "no traffic"
    cost: dict[str, dict[int, list[int]]] = field(default_factory=dict)  # weighted trains
    trains: dict[str, dict[int, list[int]]] = field(default_factory=dict)  # plain train counts

    # ----- derived values -----

    @property
    def per_day(self) -> int:
        return slots_per_day(self.slot_minutes)

    @property
    def max_block_slots(self) -> int:
        return self.max_block_minutes // self.slot_minutes

    def dur(self, request: PlanRequest) -> int:
        return duration_slots(request.duration_minutes, self.slot_minutes)

    def gap_slots(self, dependency: PlanDependency) -> int:
        return duration_slots(dependency.gap_minutes, self.slot_minutes)

    def crew_limit(self, dept: str) -> int:
        return self.crews.get(dept, self.default_crews)

    def weight(self, name: str) -> int:
        return self.weights.get(name, DEFAULT_WEIGHTS[name])

    def window(self, request: PlanRequest) -> tuple[int, int]:
        """Allowed days, clamped into the horizon."""
        last = self.days - 1
        lo = min(max(request.earliest_day, 0), last)
        hi = min(max(request.deadline_day, 0), last)
        return lo, max(lo, hi)

    def cost_at(self, section: str, day: int) -> list[int]:
        return self.cost.get(section, {}).get(day) or [0] * self.per_day

    def trains_at(self, section: str, day: int) -> list[int]:
        return self.trains.get(section, {}).get(day) or [0] * self.per_day

    def forced_deferrals(self) -> dict[int, str]:
        """Requests the planner must not place, with the reason code."""
        forced: dict[int, str] = {}
        longest = min(self.per_day, self.max_block_slots)
        for request in self.requests:
            if request.deadline_day > self.days - 1 or request.deadline_day < 0:
                forced[request.id] = OUT_OF_HORIZON
            elif self.dur(request) > longest:
                forced[request.id] = TOO_LONG
        # Follow-up work of a deferred request is deferred as well (no orphan follow-ups).
        changed = True
        while changed:
            changed = False
            for dep in self.dependencies:
                if (
                    dep.relation == "finish_before_start"
                    and dep.before in forced
                    and dep.after not in forced
                ):
                    forced[dep.after] = DEPENDENCY_UNMET
                    changed = True
        return forced

    # ----- storage -----

    def to_dict(self) -> dict:
        data = asdict(self)
        for section in ("cost", "trains"):
            data[section] = {
                s: {str(d): v for d, v in days.items()} for s, days in getattr(self, section).items()
            }
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        def arrays(raw):
            return {s: {int(d): list(v) for d, v in days.items()} for s, days in raw.items()}

        return cls(
            days=data["days"],
            slot_minutes=data["slot_minutes"],
            max_block_minutes=data["max_block_minutes"],
            requests=tuple(PlanRequest(**r) for r in data["requests"]),
            dependencies=tuple(PlanDependency(**d) for d in data["dependencies"]),
            crews=dict(data["crews"]),
            default_crews=data["default_crews"],
            weights=dict(data["weights"]),
            cost=arrays(data.get("cost", {})),
            trains=arrays(data.get("trains", {})),
        )

    def input_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
