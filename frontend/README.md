# MARG SANYOG web interface

React + Vite + TypeScript (React Router, recharts). The Gantt timeline is plain SVG. It talks to
the backend in `../backend`. **All data it shows is synthetic (simulation)**, and a banner says so
on every page.

## Run it

Easiest, from the repository root (starts the backend and the frontend in two windows):

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Or by hand, with the backend already running on <http://127.0.0.1:8000>:

```powershell
cd frontend
npm install        # first time only
npm run dev        # http://localhost:5173
```

Log in as `planner@blockplanner.test` with the password `DemoPass#2026` (the `SEED_PASSWORD`
used when you ran the backend seed script in the root README). If the backend is not on port 8000, copy `.env.example`
to `.env` and set `VITE_API_URL`.

## Pages

| Page | What it does |
| --- | --- |
| Login | Email and password. JWT is kept in memory and mirrored to `sessionStorage` (never `localStorage`). A dead session sends you back here. |
| Dashboard | KPI cards from the latest finished plan, independent vs integrated chart, requests by status. |
| Requests | Table with status, section and department filters. Create, edit, submit, cancel, reject, and a dependency editor. Server validation errors appear under the right field. |
| Plans | Run a plan (horizon, time limit, objective weights), status polling every 2 seconds, list of past runs, one click to load simulated traffic. |
| Plan detail | Tabs: Schedule (Gantt, one row per section, colour by department, hover for member requests), Compare, Conflicts, Explanations, What-if. Override, Approve and Publish with confirmation dialogs. |
| Calendar | Published closures by section and day, with week navigation. |

## Roles

The UI hides or disables what a role cannot do, and a `403` from the server is shown in plain
words. The rules live in `src/lib/permissions.ts` and mirror the backend.

| Role | Can do |
| --- | --- |
| planner, admin | Everything: run plans, what-if, override, approve, publish, reject requests. |
| department user | Create requests, and edit, submit, cancel and set dependencies only for their own department. Read everything else. |
| viewer | Read only. |

## Tests and checks

```powershell
npm test                  # Vitest: API client, token store, role checks, time and Gantt helpers, key components, the homepage and its scene maths
npm run build             # type-check and production build
npm run lint              # oxlint
powershell -ExecutionPolicy Bypass -File scripts\run-smoke.ps1
```

`run-smoke.ps1` is a real-browser check. It starts a throwaway backend (own database, fresh seed,
port 8001) and the dev server, drives headless Chrome through the whole workflow (log in, filter and
create requests, scroll the homepage train and check the track stays in view, run a plan, open every tab, what-if, approve, publish, calendar, and what a viewer
and a department user can see), fails on any console error or page error, saves screenshots to
`screenshots/`, and stops everything. It needs Google Chrome (set `CHROME_PATH` if it is not at the
default location) and does not touch your real database.

## Layout

```text
src/api/         typed client (token handling, 401 refresh, problem+json errors) and endpoint functions
src/auth/        AuthContext (session restore, login, logout)
src/lib/         permissions, time helpers (all in Asia/Kolkata), Gantt layout
src/components/  Layout, Gantt, charts, dialogs, small UI pieces
src/pages/       one folder or file per page
```
