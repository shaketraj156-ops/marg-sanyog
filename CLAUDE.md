# CLAUDE.md

Guidance for working in this repository.

## What this is

Backend for an AI-powered railway block planner (Smart India Hackathon 2026, PS 26027). Design:
`docs/Backend_Specification.md`. User-facing docs: `README.md`. **All data is synthetic.**
`index.html` at the repo root is an unrelated static landing-page prototype (AEROVECT).

## Hard constraints (decided by the user)

- SQLite, **no Docker, no Redis, no Celery**. Plan jobs run in a background thread.
- Synthetic data only. Never commit `.env`, `*.db` or tokens. Never commit secrets.
- Do not claim something works unless it was run. Untested parts go in the README.
- If a step fails twice: commit what works, note it under "Known issues", move on.

## Commands (Windows PowerShell, from `backend/`)

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --reload     # http://127.0.0.1:8000/docs
.\.venv\Scripts\python -m pytest -q                         # ~4 min, solver tests are slow
.\.venv\Scripts\python -m ruff check . --fix
.\.venv\Scripts\python -m scripts.demo                      # 16 requests, baseline vs integrated
```

`JWT_SECRET` has no default; copy `.env.example` to `.env` (gitignored). The shell tool here has
trouble with very long multi-heredoc commands: prefer the Write/Edit tools for files.

## Frontend (`frontend/`)

React + Vite + TypeScript, React Router, recharts, Vitest. Start both apps with `.\start.ps1`
(repo root). `npm test`, `npm run build`, `npm run lint` from `frontend/`.
`scripts/run-smoke.ps1` is the real-browser check (headless Chrome, throwaway backend on 8001, frontend on 5174).
Routes: `/` is the public homepage (`src/pages/home/`, ported from the root `index.html`); `/login`; the app is under `/dashboard`, `/requests`, `/plans`, `/calendar`.
Homepage: a pinned GSAP ScrollTrigger hero. `scene/HeroScene.tsx` draws a side-view SVG scene (`xMidYMax meet`, never cropped: an earlier `slice` version cut the track off on short wide windows). The train stays centred and the world slides past; `scene/frame.ts` and `scene/geometry.ts` are pure functions with tests; stop times are `ARRIVE`/`DEPART` in `src/lib/home.ts`. Reduced motion or width under 800 shows a still scene and a plain step list.
Rules that matter: tokens only in memory + `sessionStorage`; role rules in `src/lib/permissions.ts`
mirror the backend; times are shown straight from the API's `+05:30` strings (no browser time zone);
`erasableSyntaxOnly` is on (no enums or constructor parameter properties); write Python edit scripts
with `encoding="utf-8"` (Windows defaults to cp1252 and corrupts non-ASCII text).

## Layout (`backend/`)

- `app/main.py` app, routers, lifespan (marks unfinished plan runs failed on start).
- `app/api/deps.py` `get_db`, `get_current_user`, `require_role`. `app/api/v1/*` routers.
- `app/core/` `security.py` (argon2id, JWT), `errors.py` (problem+json, `ProblemError`), `timeutil.py` (IST).
- `app/db/` `base.py` (UTCDateTime, Json, Pk types), `models/` one file per aggregate, `session.py`.
- `app/schemas/` Pydantic models. `app/services/` business rules (no HTTP, no solver):
  `request_service` (state machine, version locking via `version_id_col`), `plan_service`
  (snapshot, save, render), `plan_runner` (thread, one solve at a time, `submit` is patched in tests),
  `review_service` (what-if, override, approve, publish, conflicts), `explain` (reason codes),
  `traffic_service`, `timetable_gen`, `audit`, `validation` (cycle detection).
- `app/planner/` **pure Python, no DB or HTTP imports**: `snapshot`, `plan`, `baseline`, `model`
  (CP-SAT), `checker`, `metrics`, `costs`, `slots`.
- `migrations/versions/0001..0006`. `scripts/` `seed_synthetic.py`, `demo.py`.
- `tests/` `api`, `db`, `planner`, `unit`. `conftest.py` has the `world` fixture (users per role),
  `inline_planner` (runs plan jobs inline against the test DB) and `create_plan`.

## Conventions and gotchas

- Timestamps are UTC in the database, shown in Asia/Kolkata (+05:30). SQLite drops time zones, so
  use `UTCDateTime` from `app.db.base` for new timestamp columns.
- Errors: raise `ProblemError(status, code, detail, extra=...)`; `ValidationProblem(field, msg)` for 422 field errors.
- Roles: `admin`, `planner`, `dept_user` (own department only, enforced in services), `viewer`.
- Every plan must pass `planner.checker.check_plan` before it is saved.
- CP-SAT with one worker is deterministic but weak; tests use `SOLVER_WORKERS=1` (set in conftest).
  A test that needs a proved optimum should raise workers and the time limit.
- Keep the model's redundant bounds and full hints (`app/planner/model.py`): without them the
  solver cannot prove optimality even on tiny instances.
- Ruff runs with a broad rule set; `Depends(...)` defaults are allowed via `extend-immutable-calls`.
- Add a migration for every schema change; `tests/db/test_migrations.py` checks migrations match the models.

## Status

All planned stages are done and committed. Nothing is in progress.

| Stage | State |
| --- | --- |
| M0 skeleton, M1 auth/reference | done |
| M2 requests, M3 planner, M4 traffic, M5 review workflow | done |
| Demo script (`scripts/demo.py`), `scripts/load_demo_data.py`, README, CLAUDE.md | done |
| F1 frontend (`frontend/`) | done: 148 Vitest tests, build OK, 22/22 browser steps (includes the public homepage) (`frontend/scripts/run-smoke.ps1`) |
| F2 end-to-end check (`backend/scripts/e2e_check.py`) | done: 18/18 over real HTTP; also `tests/e2e` |
| M7 hardening (login lockout, `/ready`, JSON logs, `scripts/benchmark.py`, greedy warm start) | done; benchmark in the README |
| M6 ML (`app/ml/`; `/ml/models`, `/ml/train`) | done |

Last full runs: backend 601 passed, frontend 101 passed, e2e 18/18, browser 19/19.

Start everything with `.\start.ps1` (repo root). Presentation steps are in the README ("Demo").

Not done (see the README's Limitations and Future work): Postgres/Docker never run; no solver
decomposition for 200+ requests; the overrun model is trained but not used by the planner; no
resources, power blocks, block actuals, event streaming or plan cancellation.

## Gotchas learned the hard way

- ML (`app/ml/`): the planner hook is `plan_service.build_snapshot -> ml.predict.choose_cost`; it must
  never raise (every failure becomes a fallback to train counts plus a log line and a counter).
  A model is activated only if it beats its baseline (`train.MIN_IMPROVEMENT`). Tests keep model
  files in a temp `MODEL_DIR` (conftest); the real folder `backend/models/` is gitignored.

- The solver starts from `planner/warmstart.greedy_plan` (always valid, checker-verified), not from
  the baseline. If the solver returns nothing in time, `plan_runner` keeps that plan and notes it.
  Presolve is deliberately light (`cp_model_probing_level=0`, one pass): do not undo it without
  re-running `scripts/benchmark.py` (200 requests took 11 s just to start searching otherwise).
- Tests set `LOGIN_RATE_LIMIT_PER_MINUTE=100000`; the login guard is cached, so a fixture clears
  `get_login_guard` between tests. Scripts that log in a lot (smoke, e2e) raise the limit too.

- **Never set `solver.parameters.repair_hint`**: with several workers OR-Tools aborts the whole
  process on tiny models. Solves run in a child process by default (`app/planner/isolated.py`,
  chosen in `app/services/solving.py`); tests set `SOLVER_ISOLATION=0`.
- The Bash tool rewrites backslashes in heredocs (`scripts\run` became a carriage return). Use the
  Write/Edit tools for anything containing Windows paths, or build the text with `chr(92)`.
- Python edit scripts: always `read_text(encoding="utf-8")` and `write_text(..., encoding="utf-8")`.
- Chrome for the browser smoke test is at `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`.

## Known issues

- `tests/db/test_demo.py` failed once under heavy machine load and passed on every rerun
  (cause not found); it now prints the full demo output when an assertion fails.
- Nothing has been run on Postgres or Docker.
