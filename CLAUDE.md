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

| Milestone | State |
| --- | --- |
| M0 skeleton, M1 auth/reference | done, committed |
| M2 requests, M3 planner, M4 traffic, M5 review workflow | done, committed |
| Demo script, README, CLAUDE.md | done |
| F1 frontend, F2 end-to-end check, M7 hardening, M6 ML | planned, in this order |

Last full test run before this file was written: 437 passed (backend).

## Known issues

- `tests/db/test_demo.py` failed once under heavy machine load and passed on every rerun
  (cause not found); it now prints the full demo output when an assertion fails.
- Nothing has been run on Postgres or Docker.
