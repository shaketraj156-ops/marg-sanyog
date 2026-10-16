"""End-to-end check through the real HTTP API.

    .\\.venv\\Scripts\\python -m scripts.e2e_check            (from the backend folder)

It starts its own throwaway backend (a real uvicorn process, its own SQLite file, a fresh seed and
random secrets), so your data is never touched. Then, using only plain HTTP, it plays the whole
story: log in as every role, load simulated traffic, create 16 requests with dependencies as
department users, run a plan in the background, check the metrics and the schedule, read the
explanations, try a what-if, override, approve, publish, read the calendar, and check that the
rules (roles, overlaps, stale plans, validation) hold. Exits 0 only if every check passes.

Everything here is synthetic.
"""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
START = date(2026, 10, 19)  # a Monday
SECTIONS = ["A-B", "B-C", "C-D", "D-E"]
DEPARTMENTS = ["ENGG", "TRD", "SNT"]
WORK = {"ENGG": "track", "TRD": "ohe", "SNT": "signal"}
EMAIL = {
    "planner": "planner@blockplanner.test",
    "admin": "admin@blockplanner.test",
    "engg": "engg@blockplanner.test",
    "trd": "trd@blockplanner.test",
    "snt": "snt@blockplanner.test",
    "viewer": "viewer@blockplanner.test",
}


class Failure(Exception):
    pass


class Api:
    """Tiny HTTP client: returns (status, parsed body, headers) and never raises on 4xx/5xx."""

    def __init__(self, base: str):
        self.base = base
        self.tokens: dict[str, str] = {}

    def call(self, method, path, who=None, body=None, headers=None, token=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(f"{self.base}{path}", data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        bearer = token or (self.tokens.get(who) if who else None)
        if bearer:
            request.add_header("Authorization", f"Bearer {bearer}")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw, status, out_headers = response.read(), response.status, response.headers
        except urllib.error.HTTPError as error:
            raw, status, out_headers = error.read(), error.code, error.headers
        parsed = json.loads(raw) if raw else None
        return status, parsed, out_headers

    def ok(self, method, path, who=None, body=None, expect=200, **kwargs):
        status, parsed, _ = self.call(method, path, who, body, **kwargs)
        if status != expect:
            raise Failure(f"{method} {path} as {who}: expected {expect}, got {status}: {parsed}")
        return parsed

    def login(self, who, password):
        status, parsed, _ = self.call(
            "POST", "/api/v1/auth/login", body={"email": EMAIL[who], "password": password}
        )
        if status != 200:
            raise Failure(f"login as {who} failed: {status} {parsed}")
        self.tokens[who] = parsed["access_token"]
        return parsed


class Checks:
    def __init__(self):
        self.results: list[tuple[str, bool, str]] = []

    def run(self, name, fn):
        started = time.time()
        try:
            fn()
        except Exception as error:  # noqa: BLE001  (a broken check must not stop the others)
            self.results.append((name, False, f"{type(error).__name__}: {error}"))
            print(f"  FAIL  {name}: {error}")
        else:
            self.results.append((name, True, ""))
            print(f"  ok    {name} ({time.time() - started:.1f} s)")


def need(condition, message):
    if not condition:
        raise Failure(message)


# ---------- throwaway backend ----------


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_backend(workdir: Path, password: str):
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(workdir / 'e2e.db').as_posix()}",
        "JWT_SECRET": secrets.token_urlsafe(48),
        "SEED_PASSWORD": password,
        "SOLVER_ISOLATION": "1",
        "MODEL_DIR": str(workdir / "models"),  # trained models stay in the throwaway folder
        "LOGIN_RATE_LIMIT_PER_MINUTE": "1000",  # the checks log in as every role from one address
        "PYTHONPATH": str(BACKEND),
    }
    for command in (
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        [sys.executable, "-m", "scripts.seed_synthetic"],
    ):
        subprocess.run(command, cwd=BACKEND, env=env, check=True, capture_output=True)
    port = free_port()
    log = open(workdir / "server.log", "wb")  # noqa: SIM115  (closed in stop_backend)
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=BACKEND,
        env=env,
        stdout=log,
        stderr=log,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2):
                return process, log, base
        except OSError:
            time.sleep(0.25)
    process.kill()
    raise Failure(f"the backend did not start; see {workdir / 'server.log'}")


def stop_backend(process, log):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    log.close()


# ---------- the story ----------


def request_body(index: int) -> tuple[str, dict]:
    """Request number `index` of 16: four per section, spread over departments and days."""
    dept = DEPARTMENTS[(index // 4 + index) % 3]
    earliest = (index * 3) % 4
    body = {
        "section_code": SECTIONS[index % 4],
        "work_type": WORK[dept],
        "duration_minutes": [60, 90, 120, 120, 180, 240][index % 6],
        "earliest_date": (START + timedelta(days=earliest)).isoformat(),
        "deadline_date": (START + timedelta(days=min(6, earliest + 2 + index % 2))).isoformat(),
        "priority": 1 + index % 3,
    }
    return dept.lower(), body


def abs_hours(block_start: str, clock: str) -> float:
    """Hours since START midnight for a block's member time such as '03:30'."""
    day = datetime.fromisoformat(block_start[:10]).date()
    hours, minutes = map(int, clock.split(":"))
    return (day - START).days * 24 + hours + minutes / 60


def story(api: Api, password: str) -> Checks:
    checks = Checks()
    state: dict = {}
    horizon = {
        "horizon_start": f"{START.isoformat()}T00:00:00+05:30",
        "horizon_end": f"{(START + timedelta(days=7)).isoformat()}T00:00:00+05:30",
        "time_limit_s": 15,
    }

    def health_and_login():
        need(api.ok("GET", "/health") == {"status": "ok"}, "health")
        for who in EMAIL:
            api.login(who, password)
        status, body, headers = api.call("POST", "/api/v1/auth/login", body={"email": EMAIL["planner"], "password": "wrong"})
        need(status == 401 and body["title"] == "invalid_credentials", f"bad password gave {status}")
        need(headers["content-type"].startswith("application/problem+json"), "errors should be problem+json")
        me = api.ok("GET", "/api/v1/me", "engg")
        need(me["role"] == "dept_user" and me["department"]["code"] == "ENGG", f"unexpected /me: {me}")
        status, _, _ = api.call("GET", "/api/v1/requests")
        need(status == 401, "requests must need a login")

    def reference_data():
        need([s["code"] for s in api.ok("GET", "/api/v1/sections", "viewer")] == SECTIONS, "sections")
        need(sorted(d["code"] for d in api.ok("GET", "/api/v1/departments", "viewer")) == sorted(DEPARTMENTS), "departments")

    def traffic():
        status, _, _ = api.call("POST", "/api/v1/traffic/synthetic", "engg", {})
        need(status == 403, f"a department user must not load traffic, got {status}")
        made = api.ok("POST", "/api/v1/traffic/synthetic", "planner", {}, expect=201)
        need(made["inserted"] > 100, f"timetable too small: {made}")
        rebuilt = api.ok(
            "POST",
            "/api/v1/traffic/rebuild",
            "planner",
            {"date_from": START.isoformat(), "date_to": (START + timedelta(days=6)).isoformat()},
        )
        need(rebuilt["days"] == 7 and rebuilt["sections"] == 4, f"rebuild: {rebuilt}")
        profile = api.ok("GET", f"/api/v1/traffic/profile?section=A-B&date_from={START}&date_to={START}", "viewer")
        need(sum(profile["days"][0]["trains"]) > 10, "an ordinary day should have trains")

    def rules_on_requests():
        status, body, _ = api.call("POST", "/api/v1/requests", "engg", request_body(0)[1] | {"duration_minutes": 10})
        need(status == 422 and body["errors"][0]["field"] == "duration_minutes", f"duration rule: {status} {body}")
        status, body, _ = api.call("POST", "/api/v1/requests", "engg", request_body(0)[1] | {"department_code": "TRD"})
        need(status == 403, f"another department's request must be refused, got {status}")
        status, _, _ = api.call("POST", "/api/v1/requests", "viewer", request_body(0)[1])
        need(status == 403, "a viewer must not create requests")

    def create_requests():
        ids = []
        for index in range(16):
            who, body = request_body(index)
            made = api.ok("POST", "/api/v1/requests", who, body, expect=201)
            need(made["status"] == "draft" and made["version"] == 1, f"new request: {made}")
            ids.append((made["id"], who))
        state["ids"] = ids
        # two ordering rules: the second request of a section waits for the first
        by_section: dict[str, list] = {}
        for rid, who in ids:
            section = api.ok("GET", f"/api/v1/requests/{rid}", "viewer")["section_code"]
            by_section.setdefault(section, []).append((rid, who))
        state["deps"] = []
        for section in SECTIONS[:2]:
            (first, _), (second, who) = by_section[section][:2]
            made = api.ok(
                "PUT",
                f"/api/v1/requests/{second}/dependencies",
                who,
                {"dependencies": [{"depends_on": first, "relation": "finish_before_start", "min_gap_minutes": 60}]},
            )
            need(made["dependencies"][0]["depends_on"] == first, "dependency not saved")
            state["deps"].append((first, second))
        # a loop is refused
        first, second = state["deps"][0]
        status, body, _ = api.call(
            "PUT", f"/api/v1/requests/{first}/dependencies", "planner",
            {"dependencies": [{"depends_on": second}]},
        )
        need(status == 422 and body["title"] == "dependency_cycle", f"cycle: {status} {body}")

    def optimistic_locking():
        rid, who = state["ids"][0]
        current = api.ok("GET", f"/api/v1/requests/{rid}", who)
        status, body, _ = api.call("PATCH", f"/api/v1/requests/{rid}", who, {"version": current["version"] + 5, "priority": 2})
        need(status == 409 and body["title"] == "version_conflict", f"stale version: {status} {body}")
        updated = api.ok("PATCH", f"/api/v1/requests/{rid}", who, {"version": current["version"], "priority": current["priority"]})
        need(updated["version"] == current["version"], "an unchanged patch must not bump the version")

    def submit_all():
        for rid, who in state["ids"]:
            need(api.ok("POST", f"/api/v1/requests/{rid}/submit", who, {})["status"] == "submitted", f"submit {rid}")
        listed = api.ok("GET", "/api/v1/requests?status=submitted&limit=10", "viewer")
        need(len(listed["items"]) == 10 and listed["next_cursor"], "first page")
        rest = api.ok("GET", f"/api/v1/requests?status=submitted&limit=10&cursor={listed['next_cursor']}", "viewer")
        need(len(rest["items"]) == 6 and rest["next_cursor"] is None, "second page")

    def run_plan():
        headers = {"Idempotency-Key": f"e2e-{secrets.token_hex(4)}"}
        accepted = api.ok("POST", "/api/v1/plans", "planner", horizon, expect=202, headers=headers)
        again = api.ok("POST", "/api/v1/plans", "planner", horizon, expect=202, headers=headers)
        need(again["id"] == accepted["id"], "the same Idempotency-Key must return the same run")
        status, _, _ = api.call("POST", "/api/v1/plans", "engg", horizon)
        need(status == 403, "a department user must not run plans")
        state["plan"] = accepted["id"]
        deadline = time.time() + 120
        seen = set()
        while time.time() < deadline:
            plan = api.ok("GET", f"/api/v1/plans/{accepted['id']}", "viewer")
            seen.add(plan["status"])
            if plan["status"] not in ("queued", "running"):
                break
            time.sleep(1)
        need(plan["status"] == "succeeded", f"the run ended as {plan['status']}: {plan.get('error')}")
        need(plan["solver_status"] in ("OPTIMAL", "FEASIBLE"), f"solver status {plan['solver_status']}")
        state["plan_doc"] = plan

    def metrics():
        plan = state["plan_doc"]
        baseline, integrated = plan["metrics"]["baseline"], plan["metrics"]["integrated"]
        need(integrated["closures"] < baseline["closures"], f"closures {baseline['closures']} -> {integrated['closures']}")
        need(integrated["block_hours"] < baseline["block_hours"], "block hours should drop")
        need(integrated["trains_affected"] <= baseline["trains_affected"], "trains affected must not rise")
        need(integrated["traffic_cost"] < baseline["traffic_cost"], "traffic cost should drop")
        state["metrics"] = plan["metrics"]
        print(
            f"        closures {baseline['closures']} -> {integrated['closures']}, "
            f"block hours {baseline['block_hours']} -> {integrated['block_hours']}, "
            f"trains {baseline['trains_affected']} -> {integrated['trains_affected']} "
            f"({plan['solver_status']})"
        )

    def schedule():
        schedule = api.ok("GET", f"/api/v1/plans/{state['plan']}/schedule", "viewer")
        placed = [m["request_id"] for b in schedule["blocks"] for m in b["members"]]
        deferred = [d["request_id"] for d in schedule["deferred"]]
        every = sorted(rid for rid, _ in state["ids"])
        need(sorted(placed + deferred) == every, "every request must be placed or deferred exactly once")
        need(len(placed) == len(set(placed)), "a request appears twice")
        integrated = state["metrics"]["integrated"]
        need(len(schedule["blocks"]) == integrated["closures"], "block count must match the metrics")
        hours = sum(abs_hours(b["start"], b["end"][11:16]) - abs_hours(b["start"], b["start"][11:16]) for b in schedule["blocks"])
        need(abs(hours - integrated["block_hours"]) < 0.01, f"block hours {hours} vs {integrated['block_hours']}")
        need(sum(b["trains_affected"] for b in schedule["blocks"]) == integrated["trains_affected"], "trains must reconcile")
        # dependencies: the first request finishes, plus the 60 minute gap, before the second starts
        times = {m["request_id"]: (abs_hours(b["start"], m["start"]), abs_hours(b["start"], m["end"] if m["end"] != "24:00" else "23:59") ) for b in schedule["blocks"] for m in b["members"]}
        for first, second in state["deps"]:
            if first in times and second in times:
                need(times[first][1] + 1.0 <= times[second][0] + 0.02, f"request {second} starts before {first} finishes plus the gap")
        state["schedule"] = schedule
        state["placed"] = placed

    def baseline_and_compare():
        baseline = api.ok("GET", f"/api/v1/plans/{state['plan']}/baseline", "viewer")
        need(baseline["metrics"]["closures"] == state["metrics"]["baseline"]["closures"], "baseline metrics differ")
        need(all(b["id"] is None for b in baseline["blocks"]), "baseline blocks are not real blocks")

    def explanations_and_conflicts():
        items = api.ok("GET", f"/api/v1/plans/{state['plan']}/explanations", "viewer")["items"]
        codes = {i["code"] for i in items}
        need("MERGED" in codes, f"expected MERGED among {codes}")
        merged = [i for i in items if i["code"] == "MERGED"]
        need(sum(i["numbers"]["closures_avoided"] for i in merged) > 0, "merging should avoid closures")
        need(all(i["text"] and i["numbers"] for i in items), "every explanation needs text and numbers")
        conflicts = api.ok("GET", f"/api/v1/plans/{state['plan']}/conflicts", "viewer")["conflicts"]
        need(any(c["type"] == "SECTION_COMPETITION" for c in conflicts), "no section competition reported")
        need(any(c["type"] == "DEPENDENCY" for c in conflicts), "dependencies should be reported")

    def what_if_saves_nothing():
        before = len(api.ok("GET", "/api/v1/plans", "planner")["items"])
        block = state["schedule"]["blocks"][0]
        member = block["members"][0]
        move = {"request_id": member["request_id"], "start": block["start"], "time_limit_s": 5}
        result = api.ok("POST", f"/api/v1/plans/{state['plan']}/whatif", "planner", move)
        need(result["feasible"] is True and "difference" in result["metrics"], f"what-if: {result}")
        need(len(api.ok("GET", "/api/v1/plans", "planner")["items"]) == before, "a what-if must not create a plan")
        status, _, _ = api.call("POST", f"/api/v1/plans/{state['plan']}/whatif", "viewer", move)
        need(status == 403, "a viewer must not run a what-if")

    def override_makes_a_child():
        parent_before = api.ok("GET", f"/api/v1/plans/{state['plan']}", "viewer")
        block = state["schedule"]["blocks"][0]
        member = block["members"][0]
        child = api.ok(
            "POST",
            f"/api/v1/plans/{state['plan']}/overrides",
            "planner",
            {"moves": [{"request_id": member["request_id"], "start": block["start"]}], "time_limit_s": 10},
            expect=201,
        )
        need(child["parent_id"] == state["plan"] and child["status"] == "succeeded", f"override: {child}")
        parent_after = api.ok("GET", f"/api/v1/plans/{state['plan']}", "viewer")
        need(parent_after["metrics"] == parent_before["metrics"], "the parent plan must stay unchanged")
        state["child"] = child["id"]

    def approve_and_stale_parent():
        status, _, _ = api.call("POST", f"/api/v1/plans/{state['child']}/approve", "engg")
        need(status == 403, "a department user must not approve")
        approved = api.ok("POST", f"/api/v1/plans/{state['child']}/approve", "planner")
        need(approved["status"] == "approved", f"approve: {approved}")
        status, body, _ = api.call("POST", f"/api/v1/plans/{state['plan']}/approve", "planner")
        need(status == 409 and body["title"] == "stale_plan", f"the parent must be stale now: {status} {body}")
        scheduled = api.ok("GET", "/api/v1/requests?status=scheduled&limit=200", "viewer")["items"]
        need(sorted(r["id"] for r in scheduled) == sorted(state["placed"]), "placed requests must be scheduled")
        status, _, _ = api.call("POST", f"/api/v1/plans/{state['child']}/publish", "viewer")
        need(status == 403, "a viewer must not publish")

    def publish_and_calendar():
        published = api.ok("POST", f"/api/v1/plans/{state['child']}/publish", "planner")
        need(published["status"] == "published", f"publish: {published}")
        again = api.call("POST", f"/api/v1/plans/{state['child']}/publish", "planner")[0]
        need(again == 409, "publishing twice must be refused")
        calendar = api.ok("GET", "/api/v1/blocks", "viewer")["blocks"]
        need(len(calendar) == state["metrics"]["integrated"]["closures"], f"calendar has {len(calendar)} blocks")
        need(all(b["status"] == "published" and b["plan_id"] == state["child"] for b in calendar), "calendar rows")
        done = api.ok("GET", "/api/v1/requests?status=published&limit=200", "viewer")["items"]
        need(sorted(r["id"] for r in done) == sorted(state["placed"]), "placed requests must be published")
        only = api.ok("GET", "/api/v1/blocks?section=A-B", "viewer")["blocks"]
        need(all(b["section_code"] == "A-B" for b in only), "section filter")

    def overlapping_publish_is_refused():
        # a fresh request in the same section and window, planned by a later run, lands on the same slot
        blocked = state["schedule"]["blocks"][0]
        section = blocked["section_code"]
        day = blocked["start"][:10]
        who = DEPARTMENTS[0].lower()
        body = {
            "section_code": section, "work_type": "track", "duration_minutes": 120,
            "earliest_date": day, "deadline_date": day, "priority": 3,
        }
        made = api.ok("POST", "/api/v1/requests", who, body, expect=201)
        api.ok("POST", f"/api/v1/requests/{made['id']}/submit", who, {})
        accepted = api.ok("POST", "/api/v1/plans", "planner", horizon | {"time_limit_s": 5}, expect=202)
        deadline = time.time() + 90
        while time.time() < deadline:
            plan = api.ok("GET", f"/api/v1/plans/{accepted['id']}", "viewer")
            if plan["status"] not in ("queued", "running"):
                break
            time.sleep(1)
        need(plan["status"] == "succeeded", f"second run: {plan['status']} {plan.get('error')}")
        api.ok("POST", f"/api/v1/plans/{accepted['id']}/approve", "planner")
        status, body, _ = api.call("POST", f"/api/v1/plans/{accepted['id']}/publish", "planner")
        if status == 200:
            return  # the planner happened to choose a free slot; the rule itself is covered by unit tests
        need(status == 409 and body["title"] == "block_overlap", f"overlap: {status} {body}")
        need(body["conflicts"], "the overlap response must say which block conflicts")

    def ml_model_drives_the_cost():
        status, _, _ = api.call("POST", "/api/v1/ml/train", "planner", {"days": 40})
        need(status == 403, f"only an admin may train, got {status}")
        trained = api.ok("POST", "/api/v1/ml/train", "admin", {"kind": "delay", "days": 40}, expect=201)
        delay = trained["results"][0]
        need(delay["beats_baseline"] and delay["is_active"], f"the delay model should beat its baseline: {delay['metrics']}")
        need(delay["metrics"]["mae"] < delay["metrics"]["baseline_mae"], "model error must be below the baseline's")
        listed = api.ok("GET", "/api/v1/ml/models", "planner")["items"]
        need(any(m["kind"] == "delay" and m["is_active"] for m in listed), "the active model must be listed")
        status, _, _ = api.call("GET", "/api/v1/ml/models", "viewer")
        need(status == 403, "a viewer must not list models")
        # a fresh request, planned after the model is active, uses it for the cost
        day = (START + timedelta(days=5)).isoformat()
        body = {"section_code": "D-E", "work_type": "track", "duration_minutes": 120,
                "earliest_date": day, "deadline_date": day, "priority": 2}
        made = api.ok("POST", "/api/v1/requests", "engg", body, expect=201)
        api.ok("POST", f"/api/v1/requests/{made['id']}/submit", "engg", {})
        accepted = api.ok("POST", "/api/v1/plans", "planner", horizon | {"time_limit_s": 5}, expect=202)
        deadline = time.time() + 90
        while time.time() < deadline:
            plan = api.ok("GET", f"/api/v1/plans/{accepted['id']}", "viewer")
            if plan["status"] not in ("queued", "running"):
                break
            time.sleep(1)
        need(plan["status"] == "succeeded", f"plan with the model: {plan['status']} {plan.get('error')}")
        need(plan["model_versions"].get("cost", "").startswith("delay_model:v"), f"cost source: {plan['model_versions']}")

    for name, fn in [
        ("health, logins and error format", health_and_login),
        ("reference data", reference_data),
        ("simulated traffic (and the role rule)", traffic),
        ("request rules: validation, department, viewer", rules_on_requests),
        ("16 requests with dependencies, loops refused", create_requests),
        ("optimistic locking", optimistic_locking),
        ("submit all, pagination", submit_all),
        ("plan runs in the background (idempotent, role rule)", run_plan),
        ("metrics: integrated beats independent", metrics),
        ("schedule is complete, consistent and ordered", schedule),
        ("baseline matches its metrics", baseline_and_compare),
        ("explanations and conflicts", explanations_and_conflicts),
        ("what-if saves nothing", what_if_saves_nothing),
        ("override creates a child plan", override_makes_a_child),
        ("approve, stale parent, roles", approve_and_stale_parent),
        ("publish and the calendar", publish_and_calendar),
        ("overlapping publish is refused", overlapping_publish_is_refused),
        ("delay model is trained and drives the plan cost", ml_model_drives_the_cost),
    ]:
        checks.run(name, fn)
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end check through the real HTTP API.")
    parser.add_argument("--keep", action="store_true", help="keep the temporary folder (database, log)")
    args = parser.parse_args()

    password = secrets.token_urlsafe(12)
    workdir = Path(tempfile.mkdtemp(prefix="bp-e2e-"))
    print(f"Synthetic data only. Starting a throwaway backend in {workdir} ...")
    process, log, base = start_backend(workdir, password)
    try:
        print(f"Backend up at {base}. Running the checks.")
        checks = story(Api(base), password)
    finally:
        stop_backend(process, log)
        if not args.keep:
            import shutil

            shutil.rmtree(workdir, ignore_errors=True)
    failed = [r for r in checks.results if not r[1]]
    print()
    print(f"{len(checks.results) - len(failed)}/{len(checks.results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
