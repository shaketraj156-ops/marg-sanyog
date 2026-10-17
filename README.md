# AI-Powered Automatic Block Planning

Railway maintenance needs "blocks": a section of line is closed so engineers can work on it.
Engineering, Traction Distribution (TrD) and Signal and Telecom (S&T) normally ask for blocks
separately, so the same section is closed again and again. This system takes their requests,
plans them together (several departments share one closure window, scheduled when few trains
run), and shows a human planner the result with reasons, so the planner can review, try
changes, approve and publish. It has a Python backend (`backend/`, FastAPI and an OR-Tools
optimizer) and a React web interface (`frontend/`).

> **All data in this project is synthetic (simulation).** The timetable, traffic, requests and
> every number below come from invented data and stated assumptions. No real railway data was
> used and nothing here controls trains, signals or power. The system proposes; a person approves.

The design is in [`docs/Backend_Specification.md`](docs/Backend_Specification.md). Hosting on Render and Vercel is covered in [`docs/Deployment.md`](docs/Deployment.md).

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
| End-to-end check through the real HTTP API (`backend/scripts/e2e_check.py`): real server process, real background solver, all roles, the whole workflow and the failure paths | Run: 18/18 checks; also part of the test suite |
| Machine learning (light): synthetic data, delay and overrun models vs baselines, time-based split, registry, `/ml/models`, `/ml/train`, delay-model cost with fallback | Built and tested (leakage and fallback tests; checked over real HTTP) |
| Hardening: login lockout and rate limit, `/ready`, JSON request logs with request ids, benchmark script | Built and tested (see [Hardening](#hardening-light) and [Benchmark](#benchmark)) |
| Solver isolation: each solve runs in a child process, so a native crash fails one run instead of killing the server | Built and tested (crash, exception, hang, cancel) |
| Web interface (`frontend/`): public homepage (scroll-driven train), login (with a one-click read-only demo), a short train welcome after sign-in, a 3D railway background that can be switched off, dashboard, requests, plans, plan detail with Gantt, calendar | Built; 148 unit and component tests; 22-step real-browser check run in Chrome (zero console errors) |

**Test counts at the last full run:** backend 601 tests, frontend 148 tests, end-to-end check 18/18
over real HTTP, browser check 22/22. Everything above was run on **SQLite**. See
[Limitations](#limitations) for what was not run and [Known issues](#known-issues).

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

For the web interface, install its packages once (needs Node 20 or newer):

```powershell
cd ..\frontend
npm install
```

After that, `start.ps1` (below) starts everything.

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

### Present it in the web interface (recommended)

1. Start everything: `powershell -ExecutionPolicy Bypass -File .\start.ps1` (two windows open).
2. First time only, put demo data in the application's database (16 synthetic requests with two
   ordering rules, simulated traffic for 19 to 25 October 2026):
   `cd backend` then `.\.venv\Scripts\python -m scripts.load_demo_data`.
3. Open <http://localhost:5173> and **log in as `planner@blockplanner.test`**.
4. **Dashboard:** empty at first ("No finished plan yet").
5. **Requests:** show the 16 submitted requests, filter by section or status, open "New request"
   and try a duration of 5 to see the server's rule shown under the field. Open a request's
   dependency editor.
6. **Plans:** the date is already the next Monday; for the demo data set it to **2026-10-19**.
   Set the time limit to 20 to 30 seconds and press **Run plan**. The page shows progress every 2
   seconds and offers the plan when it finishes.
7. **Plan detail, Schedule:** the Gantt shows one row per section, bars coloured by department;
   hover a bar to see the requests that share it.
8. **Compare:** independent planning against the integrated plan (chart, table, and both
   timelines). **Conflicts** and **Explanations** show why, with the numbers behind each reason.
9. **What-if:** pick a request and a new start, press "Try this move" (nothing is saved), and read
   the difference. **Override...** applies moves and creates a child plan.
10. **Approve**, then **Publish**, each with a confirmation. Open **Calendar** for the published
    closures by section and day, and **Dashboard** for the headline numbers.
11. **Roles:** log out and log in as `viewer@blockplanner.test` (read-only) or `engg@blockplanner.test`
    (can edit only Engineering's requests) to show the buttons that disappear.

Optional: log in as `admin@blockplanner.test` and call `POST /api/v1/ml/train` in the API
documentation to train the delay model; the next plan then reports it used predicted delay.

### One command in the terminal

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
| Health | `GET /health` (liveness), `GET /ready` (database, tables, solver, plan queue; 503 when not ready), both without the `/api/v1` prefix | public |
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
| ML | `GET /ml/models` | P, A |
| | `POST /ml/train` (trains on synthetic data, registers the result) | A |

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

The web interface has its own checks:

```powershell
cd frontend
npm test                                                        # 148 unit and component tests
npm run build                                                   # type-check and production build
powershell -ExecutionPolicy Bypass -File scripts\run-smoke.ps1  # real browser (Chrome), 22 steps
```

Tests use in-memory SQLite. To run the same suite on Postgres, point `TEST_DATABASE_URL` at a
**throwaway** database (the tests create and drop tables in it). That path has not been run.

## Hardening (light)

- **Login protection.** After 5 failed logins for one email the account is locked for 15 minutes
  (`429 too_many_attempts` with a `Retry-After` header, even for the right password), and one
  address may try at most 10 logins per minute (`429 rate_limited`). The counters are in memory and
  keyed by email, so an email that does not exist behaves exactly like one that does. Settings:
  `LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_SECONDS`, `LOGIN_RATE_LIMIT_PER_MINUTE`.
- **`GET /ready`.** Checks that the database answers, the tables exist, the solver loads and the
  plan queue is moving (a run waiting more than 10 minutes with nothing running means "stalled").
- **JSON logs with a request id.** One JSON line per request (`ts`, `level`, `request_id`, `method`,
  `path`, `status`, `duration_ms`, `user_id`). The id is also returned in the `X-Request-ID` header
  (a safe id sent by the caller is kept). Passwords, tokens, request bodies and query strings are
  never logged. An unexpected error returns a problem response that quotes the request id and hides
  the details.

## Benchmark

`backend/scripts/benchmark.py` solves synthetic instances (about four requests per section over 7
days, simulated traffic, one ordering rule per eight requests) with a fixed solver time limit, runs
the independent checker on every result, and has a total time budget so it never runs long:

```powershell
cd backend
.\.venv\Scripts\python -m scripts.benchmark            # 16, 50 and 200 requests, 10 s each
.\.venv\Scripts\python -m scripts.benchmark --sizes 50 200 --time-limit 30 --budget 105
```

Measured on the development machine (12 cores, 8 solver workers, OR-Tools 9.15, Python 3.14),
checker violations 0 in every run. Closures, block hours and trains are independent planning →
integrated plan. "First" is when the solver found its first plan. **Times vary from run to run**
because other programs use the same cores; treat these as typical, not exact.

| Requests (sections) | Time limit | Result | First | Gap | Closures | Block hours | Trains |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 16 (4) | 10 s | proved optimal in some runs, otherwise best found with gap 10% | 0.3 to 0.7 s | 0 to 11% | 16 → 8 | 33.5 → 25 | 37 → 9 to 11 |
| 50 (13) | 10 s | best found, not proved | 1.1 s | 40 to 47% | 43 → 22 | 103.5 → 84 | 136 → 106 to 132 |
| 50 (13) | 30 s | best found, not proved | 2.4 s | 27% | 43 → 24 | 103.5 → 85 | 136 → 53 |
| 200 (50) | 10 s | essentially the valid starting plan (first plan at 5 to 10 s) | 5 to 10 s | very large | 167 → 143 | 386 → 430 | 665 → 643 |
| 200 (50) | 30 s | best found, not proved | 5.4 s | 59% | 167 → 143 | 386 → 428.5 | 665 → 639 |

What this shows, honestly:

- At **16 requests** the planner gives a clearly better plan quickly and often proves it optimal.
- At **50 requests** it is clearly better than independent planning (closures roughly halved) but
  the solver cannot prove optimality in 10 or 30 seconds; more time keeps improving it.
- At **200 requests** the single model is too big to solve well in 30 seconds. The first plan takes
  5 to 10 seconds to appear (expanding the model dominates), closures fall by about 14% but block
  hours rise slightly because a few requests are deferred. The honest conclusion matches the
  spec's: at this size the planner needs decomposition by division or corridor and a rolling
  horizon (not built), or a much longer time limit.
- A run **never ends empty-handed**: a quick greedy pass builds a valid starting plan (checked by
  the independent checker), the solver improves it, and if the time limit ends before the solver
  has anything better, that valid starting plan is used and the run says so.

## Machine learning (light)

Two small models from spec section 11, trained with scikit-learn on **synthetic data generated
here** (an invented process the models have to learn; nothing about real railways):

| Model | Predicts | Baseline it must beat | Measured on the last 20% of the period |
| --- | --- | --- | --- |
| Delay | train-minutes lost by a closure window | delay proportional to the raw train count in the window | error (MAE) 3.9 against 9.6 minutes, 60% lower |
| Overrun | 75th percentile of actual / planned duration | the 75th percentile per kind of work | pinball loss 0.048 against 0.056, 14% lower; 73.6% of outcomes fell under the prediction (target 75%) |

(120 days of synthetic history, seed 1; each model trains in about a second.)

- **Time-based split.** Both models are trained on the first 80% of the days and tested on the last
  20%, never on a random split, so the test period is entirely later than the training period.
  Tests prove there is no leakage: a model trained on shuffled targets cannot beat the baseline, and
  scrambling the targets of the test period does not change the trained model at all.
- **Registry.** `POST /api/v1/ml/train` (admin only) trains, saves the file under `MODEL_DIR`, and
  adds a versioned row to the `ml_models` table. A model becomes the **active** one of its kind only
  if it beats its baseline by at least 2% (the overrun model must also be well calibrated); a worse
  model is kept for inspection and the earlier active model stays. The database allows only one
  active model per kind. `GET /api/v1/ml/models` lists them with their metrics.
- **The planner uses the delay model only when it can.** Before solving, `DelayModelCost` turns the
  active delay model into the same per-slot cost arrays the train counts would give (the extra
  predicted delay of covering that slot, summed over a window: an additive approximation that fits
  the solver). If there is no active model, no traffic data, an unknown section, or the file is
  missing, corrupt or fails, the plan uses the train-count cost, logs `ml_inference_fallback`, and
  records which cost it used in the plan (`model_versions`, shown on the Compare tab). Setting
  `ML_COST_ENABLED=0` switches the model off.
- **Not wired in:** the overrun model is trained and registered, but the planner does not yet
  replace planned durations with its buffered ones.
- **Model files are pickles** (joblib). Only files this application wrote, named in the registry and
  inside `MODEL_DIR`, are loaded; never put files from elsewhere there.

Try it: log in as `admin@blockplanner.test`, `POST /api/v1/ml/train` with `{}`, then run a plan and
look at `model_versions` in `GET /api/v1/plans/{id}`.

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
- **The solver starts from a valid greedy plan, not from the baseline.** The baseline ignores crews,
  block limits and dependencies, so it is not a valid plan. The greedy plan is, and it gives the
  solver a complete hint. Presolve is limited (`cp_model_probing_level=0`, one presolve pass)
  because on big models the expansion of the cost lookups, not the search, was taking the whole
  time limit; the light setting also found better plans at 16 and 50 requests.
- **One solve at a time per process** (the solver uses the CPU cores); other runs wait as `queued`.
  A run left `queued` or `running` when the server stops is marked `failed` on the next start.
- **Slot size is fixed to the configured `SLOT_MINUTES` (30)** so the traffic profile and plans
  always agree.

## Limitations

Honest list of what is not done or not verified:

- **Never run on Postgres or in Docker.** Everything was run on SQLite. The Postgres exclusion
  constraint and JSONB columns are written but untested. Docker was not
  available on the development machine.
- **The homepage was only checked in Chrome** (headless, 1440x900, 1536x730 and 1280x560, plus the
  22-step smoke run). Firefox, Safari, touch devices and real phones were not tried; under 800 px
  wide, it shows a still scene and a plain list instead of the scroll animation. The homepage
  train, the welcome after sign-in and the 3D background run even when the operating system reports
  "reduce motion" (many laptops report it without the user choosing it). The welcome and background
  were not checked on those laptops, and the background needs WebGL; automated browsers skip both.
- **Plan jobs run in a thread inside the API process** (no Celery, no Redis). They do not survive
  a restart, there is no `GET /plans/{id}/events` stream and no `POST /plans/{id}/cancel`. Poll
  `GET /plans/{id}` instead.
- **Solve quality depends on time, cores and size.** Small instances (16 requests) are solved well
  and often proved optimal; at 50 requests the plan is good but not proved; at 200 requests the
  result within 30 seconds is weak (see [Benchmark](#benchmark)). One worker is much weaker than
  eight. Decomposition by division and a rolling horizon, which the spec proposes for scale, are
  not built.
- **Login limits live in one process's memory.** They reset when the server restarts and would not
  be shared between several API processes (that needs Redis, which this project does not use).
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
- **The models learned an invented process.** Their accuracy numbers say the machinery works (it
  beats its baselines on a held-out later period, without leakage), not that delay or overrun on
  real railways can be predicted this well. Real data (block actuals, the Traffic Management System)
  is needed, as the spec says. The delay model sees the average train weight instead of the full
  category mix, because the traffic profile does not store categories.

- **Web interface:** checked in Chrome only (not Firefox, Safari or a phone). It is built for a laptop
  or projector. There are no translations, and it polls every 2 seconds instead of streaming
  progress. The Gantt is a plain SVG drawing, not a drag-and-drop editor: moves are made through
  the What-if and Override forms.

## Known issues

- `tests/db/test_demo.py` (the demo script as a subprocess) failed once while the machine was heavily
  loaded and passed on every rerun; the cause was not found. It now prints the full output when it
  fails.
- A plan of about 200 requests with a short time limit returns mostly the valid starting plan (see
  [Benchmark](#benchmark)); this is a known limit of the single model, not a bug.
- Nothing has been run on Postgres or in Docker (see Limitations).
- The shell tool used during development rewrote some backslashes; `CLAUDE.md` records how to
  avoid it. All Windows paths in this README were checked after writing.

## Future work

- ML: use the overrun model's buffered durations in the plan, retrain from recorded block actuals
  instead of synthetic data, a model for asset risk, drift monitoring, and a `/metrics` endpoint
  (the fallback counter exists but is not exposed).
- More hardening: Prometheus metrics, a Redis-backed login limiter, an audit-log reader, a security
  review, load tests of the API (only the solver is benchmarked).
- Decomposition by division or corridor and a rolling horizon, so 200 or more requests plan well.
- Real queue (Celery and Redis), progress streaming, cancellation.
- Resource calendars, power blocks across feeding sections, block actuals feeding the models.
- Adapters for the real Traffic Management System and Traction Distribution Management System.
- Notifications, single sign-on, multi-division rolling-horizon planning.

---

All results, numbers and screens in this document come from simulated data.
