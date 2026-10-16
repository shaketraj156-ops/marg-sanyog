# AI-Powered Automatic Block Planning (backend)

Smart India Hackathon 2026, Problem Statement 26027.

Railway maintenance needs "blocks": a section of line is closed so engineers can work on it.
Engineering, Traction Distribution (TrD) and Signal and Telecom (S&T) normally ask for blocks
separately, so the same section is closed again and again. This backend takes their requests,
plans them together (several departments share one closure window, scheduled when few trains
run), and shows a human planner the result with reasons, so the planner can review, try
changes, approve and publish.

> **All data in this project is synthetic (simulation).** The timetable, traffic, requests and
> every number below come from invented data and stated assumptions. No real railway data was
> used and nothing here controls trains, signals or power. The system proposes; a person approves.

The design is in [`docs/Backend_Specification.md`](docs/Backend_Specification.md).

## What works (and how it was checked)

| Area | Status |
| --- | --- |
| Login, JWT access and rotating refresh tokens, four roles | Built and tested |
| Reference data (departments, sections), seed script | Built and tested |
| Block requests: create, edit, submit, cancel, reject, dependencies with cycle detection, optimistic locking, audit log | Built and tested |
| Planner (OR-Tools CP-SAT), independent-planning baseline, independent checker, metrics | Built and tested |
| Plan runs in a background thread, status polling, idempotency key | Built and tested |
| Synthetic timetable generator, traffic profile, CSV/JSON upload, traffic-aware cost | Built and tested |
| Explanations, conflicts, what-if, override (child plan), approve, publish, published calendar | Built and tested |
| `scripts/demo.py` end-to-end demo | Run, and covered by a smoke test |
| End-to-end check through the real HTTP API (`backend/scripts/e2e_check.py`): real server process, real background solver, all roles, the whole workflow and the failure paths | Run: 17/17 checks; also part of the test suite |
| Solver isolation: each solve runs in a child process, so a native crash fails one run instead of killing the server | Built and tested (crash, exception, hang, cancel) |
| Web interface (`frontend/`): login, dashboard, requests, plans, plan detail with Gantt, calendar | Built; 97 unit and component tests; 19-step real-browser check run in Chrome |

Everything above was run on **SQLite**. See [Limitations](#limitations) for what was not run.

## Setup on Windows (no Docker, no Redis)

Open PowerShell and run these one at a time.

```powershell
cd C:\Users\Dell\OneDrive\Documents\GitHub\hack-day\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python -m alembic upgrade head
$env:SEED_PASSWORD = "pick-a-password"
.\.venv\Scripts\python -m scripts.seed_synthetic
Remove-Item Env:SEED_PASSWORD
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs>. If you pulled new code, run `alembic upgrade head` again to
add new tables, and `pip install -e ".[dev]"` again to add new packages.

Demo users (all use the password you chose for `SEED_PASSWORD`):

| Email | Role |
| --- | --- |
| `admin@blockplanner.test` | admin |
| `planner@blockplanner.test` | planner |
| `engg@blockplanner.test`, `trd@blockplanner.test`, `snt@blockplanner.test` | department users |
| `viewer@blockplanner.test` | viewer (read-only) |

## Web interface

Start everything with one command from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

It applies any pending database migrations, then opens the backend (<http://127.0.0.1:8000/docs>) and
the frontend (<http://localhost:5173>) in two windows. Log in as `planner@blockplanner.test`.
Details, pages and role rules are in [`frontend/README.md`](frontend/README.md).

To check the interface in a real browser (needs Google Chrome):

```powershell
cd frontend
powershell -ExecutionPolicy Bypass -File scripts\run-smoke.ps1
```

## Demo

### One command

```powershell
cd backend
.\.venv\Scripts\python -m scripts.demo
```

It builds its own throwaway database (`demo.db`, your real data is never touched), generates a
synthetic timetable and traffic for 4 sections, creates 16 requests across 7 days, runs the
planner (30 second limit) and prints independent planning against the integrated plan, the
schedule, and the reasons. Use `--time-limit 10` for a faster run.

A typical result (seed 7, 30 second limit, 8 workers; numbers vary slightly between runs because
the solver stops at its time limit, and it reports honestly when it has not proved optimality):

| | Independent | Integrated |
| --- | ---: | ---: |
| Closures | 15 | 10 |
| Block hours | 35.0 | 24.0 |
| Trains affected | 56 | 17 |

These come from synthetic data and say nothing about real railway performance.

### Through the API (the story to tell)

In <http://127.0.0.1:8000/docs>, click **Authorize** after logging in.

1. `POST /api/v1/auth/login` as `planner@blockplanner.test`, paste the `access_token` into **Authorize**.
2. `POST /api/v1/traffic/synthetic`, then `POST /api/v1/traffic/rebuild` with
   `{"date_from": "2026-10-19", "date_to": "2026-10-25"}` to load simulated traffic.
3. Log in as `engg@`, `trd@` and `snt@` and `POST /api/v1/requests`, then
   `POST /api/v1/requests/{id}/submit` for each (or create them as the planner with `department_code`).
4. As the planner: `POST /api/v1/plans` with
   `{"horizon_start": "2026-10-19T00:00:00+05:30", "horizon_end": "2026-10-26T00:00:00+05:30", "time_limit_s": 20}`.
   It answers `202`; poll `GET /api/v1/plans/{id}` until `status` is `succeeded`.
5. Show the comparison in `metrics` (baseline against integrated), `GET .../schedule`,
   `GET .../explanations` and `GET .../conflicts`.
6. Try a change without saving it: `POST .../whatif`. Apply a change: `POST .../overrides`
   (creates a child plan).
7. `POST .../approve`, then `POST .../publish`, then `GET /api/v1/blocks` for the calendar.

## API overview

Base path `/api/v1`. Errors use `application/problem+json` with a stable `title` code.
Roles: **A** admin, **P** planner, **D** department user (own department), **V** viewer.

| Area | Endpoints | Who |
| --- | --- | --- |
| Health | `GET /health` (no prefix) | public |
| Auth | `POST /auth/login`, `POST /auth/refresh`, `GET /me` | public, public, all |
| Reference | `GET /sections`, `GET /sections/{id}`, `GET /departments` | all |
| Requests | `POST /requests`, `GET /requests`, `GET /requests/{id}`, `PATCH /requests/{id}`, `POST /requests/{id}/submit`, `POST /requests/{id}/cancel`, `PUT /requests/{id}/dependencies` | D (own), P, A write; all read |
| | `POST /requests/{id}/reject` | P, A |
| Traffic | `POST /traffic/timetable` (JSON or CSV), `POST /traffic/synthetic`, `POST /traffic/rebuild` | P, A |
| | `GET /traffic/profile` | all |
| Plans | `POST /plans` (returns 202, accepts `Idempotency-Key`) | P, A |
| | `GET /plans`, `GET /plans/{id}`, `/schedule`, `/baseline`, `/conflicts`, `/explanations` | all |
| Review | `POST /plans/{id}/whatif`, `/overrides`, `/approve`, `/publish` | P, A |
| Calendar | `GET /blocks` (published blocks) | all |

Interactive documentation: <http://127.0.0.1:8000/docs>.

## How the planner works

1. **Snapshot.** A run reads every `submitted` request, their dependencies and the traffic
   profile into one immutable object and stores it with a hash. The stored plan is the record.
2. **Baseline (independent planning).** Each request goes at its preferred start, or at its
   department's default hour, with no coordination. Only requests that truly overlap in time share
   a closure.
3. **Model (CP-SAT).** For each request choose a day and a start slot; requests on the same
   section and day share one closure window; crews are limited (2 per department); same-department
   work on one section cannot overlap; dependencies are `finish_before_start` with a gap or
   `not_same_block`. The objective is `150 x closures + 10 x traffic cost + 20 x priority x
   postponement days + total window length + 1000 x priority x deferral`. A request may be
   deferred (with a reason) instead of making the problem infeasible.
4. **Checker.** An independent verifier re-checks every constraint without the solver. A plan that
   fails is never saved; the run fails instead.
5. **Metrics.** One function scores both plans: closures, block hours, trains affected.

Time is stored in UTC and shown in Asia/Kolkata. The planning grid is 30-minute slots.

## Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q          # about 4 minutes; the solver tests take most of it
.\.venv\Scripts\python -m ruff check .
```

`tests/e2e/test_live_flow.py` runs `scripts/e2e_check.py`, which starts its own throwaway server and
plays the whole story over real HTTP (about 40 seconds). You can run it alone:
`.\.venv\Scripts\python -m scripts.e2e_check`.

Tests use in-memory SQLite. To run the same suite on Postgres, point `TEST_DATABASE_URL` at a
**throwaway** database (the tests create and drop tables in it). That path has not been run.

## Decisions made while building (and why)

- **Plans are readable by every signed-in role.** The spec's endpoint table lists P, A, V but its
  permission table says every role may read plans. Department users need to see what happened to
  their requests, so the permissive reading was used.
- **Baseline closures merge only overlapping work.** Two jobs that merely touch end to start are
  two block applications. Merging them would make independent planning look coordinated.
- **Deadline outside the horizon means the request is skipped for the run** (`OUT_OF_HORIZON`), as
  the spec says. It stays `submitted` for a later plan.
- **A train counts in the slot where it enters the section**, so a closure affects the trains that
  arrive while it lasts. Plain counts are reported as "trains affected"; weighted counts
  (premium 5, mail 4, passenger 3, local 2, freight 1) are the planner's cost.
- **Dependencies only bind requests in the same run.** A dependency on a request that is not part
  of the run (for example already published) is ignored.
- **Override and what-if re-solve from the stored snapshot**, with the current plan as a hint, so
  they answer for the data the plan was made from.
- **Approving checks the plan is still current.** If a placed request was cancelled or edited after
  the run, approval returns `409 stale_plan`.
- **The overlap rule for published blocks is enforced in code** (publish is all or nothing).
  Migration `0004` also adds a Postgres exclusion constraint as a backstop.
- **Publishing does not supersede earlier published runs.** Overlaps are refused instead.
- **Every solve runs in a child process** (`SOLVER_ISOLATION=1`, the default). OR-Tools is native
  code and once aborted the whole process (found by the end-to-end check, caused by a
  `repair_hint` setting that has been removed). With isolation a crash fails that one run with a
  clear message and the server keeps working. It costs about a second per solve; the unit tests
  switch it off for speed and have their own tests for it.
- **One solve at a time per process** (the solver uses the CPU cores); other runs wait as `queued`.
  A run left `queued` or `running` when the server stops is marked `failed` on the next start.
- **Slot size is fixed to the configured `SLOT_MINUTES` (30)** so the traffic profile and plans
  always agree.

## Limitations

Honest list of what is not done or not verified:

- **Never run on Postgres or in Docker.** Everything was run on SQLite. The Postgres exclusion
  constraint, JSONB columns and the `docker-compose.yml` are written but untested. Docker was not
  available on the development machine.
- **Plan jobs run in a thread inside the API process** (no Celery, no Redis). They do not survive
  a restart, there is no `GET /plans/{id}/events` stream and no `POST /plans/{id}/cancel`. Poll
  `GET /plans/{id}` instead.
- **Solve quality depends on time and cores.** On the 16-request demo the solver usually ends at
  its time limit with a good plan and a reported gap, not a proof of optimality. One worker is much
  weaker than eight. Larger sizes are measured in the benchmark section once it has been run.
- **Not implemented from the spec:** resources and crew calendars (crews are a flat 2 per
  department), `section_links`, multi-section and power blocks (`needs_power_block` is stored but
  not planned), block actuals, a reader for the audit log, user management endpoints, server-sent
  events, plan cancellation, `Retry` and queues.
- **Allowed-hours masks, rolling horizon and decomposition** (spec section 18) are not done.
- **Traffic counts trains by entry slot.** A train already in the section when a closure starts is
  not counted.
- **Synthetic data only.** Train patterns, durations and department habits are invented; real rules
  (minimum gap between blocks, standard corridor windows, work that may never share a block) are
  open questions in the spec and are not modelled.
- Migrations were only run on SQLite.

## Future work

- Machine learning (delay and overrun predictors behind the cost interface, with fallback).
- Hardening: login rate limiting and lockout, readiness check, structured request logging,
  benchmarks, security review.
- Real queue (Celery and Redis), progress streaming, cancellation.
- Resource calendars, power blocks across feeding sections, block actuals feeding the models.
- Adapters for the real Traffic Management System and Traction Distribution Management System.
- Notifications, single sign-on, multi-division rolling-horizon planning.
