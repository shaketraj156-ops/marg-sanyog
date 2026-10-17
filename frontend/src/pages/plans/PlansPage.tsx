import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import type { Plan, PlanWeights } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { Empty, ErrorMessage, Field, Loading, StatusBadge } from '../../components/ui'
import { usePolling, useAsync } from '../../hooks/useAsync'
import { canRunPlans } from '../../lib/permissions'
import { addDays, fmtDate, fmtDateTime, istMidnight, nextMonday, percentReduction } from '../../lib/time'

const ACTIVE = ['queued', 'running']
const DEFAULT_WEIGHTS: PlanWeights = { block: 150, traffic: 10, delay: 20, defer: 1000 }
const WEIGHT_HELP: Record<keyof PlanWeights, string> = {
  block: 'cost of each closure',
  traffic: 'cost per weighted train affected',
  delay: 'cost per priority-weighted day of postponement',
  defer: 'cost of leaving a request unplanned',
}

export function PlansPage() {
  const { user } = useAuth()
  const plans = useAsync(() => api.plans({ limit: 50 }), [])
  const [activeId, setActiveId] = useState<number | null>(null)
  const active = useAsync<Plan | null>(() => (activeId ? api.plan(activeId) : Promise.resolve(null)), [activeId])

  const anyRunning =
    (plans.data?.items.some((p) => ACTIVE.includes(p.status)) ?? false) ||
    (active.data ? ACTIVE.includes(active.data.status) : false)
  // Poll every 2 seconds while a run is queued or running.
  usePolling(
    () => {
      plans.reload()
      if (activeId) active.reload()
    },
    2000,
    anyRunning,
  )

  const [start, setStart] = useState(nextMonday())
  const [days, setDays] = useState(7)
  const [timeLimit, setTimeLimit] = useState(30)
  const [weights, setWeights] = useState<PlanWeights>(DEFAULT_WEIGHTS)
  const [advanced, setAdvanced] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [info, setInfo] = useState<string | null>(null)

  if (!user) return null
  const mayRun = canRunPlans(user)
  const end = addDays(start, days)

  const run = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      const accepted = await api.createPlan({
        horizon_start: istMidnight(start),
        horizon_end: istMidnight(end),
        time_limit_s: timeLimit,
        weights,
      })
      setActiveId(accepted.id)
      plans.reload()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const loadTraffic = async () => {
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      const made = await api.syntheticTraffic()
      const built = await api.rebuildTraffic(start, addDays(end, -1))
      setInfo(
        `Simulated timetable loaded (${made.inserted} trains). Traffic profile rebuilt for ${built.days} days (${built.rows} slot rows).`,
      )
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const current = active.data

  return (
    <div className="stack">
      <div className="page-title">
        <div>
          <h1>Plans</h1>
          <p className="page-sub">Run the optimizer over a week of submitted requests, then review, approve and publish the result.</p>
        </div>
      </div>

      <section className="card">
        <h2>Run a plan</h2>
        {!mayRun ? (
          <p className="muted">Only planners and administrators can run plans. You can open any past plan below.</p>
        ) : (
          <form onSubmit={run} className="stack-small">
            <div className="form-grid">
              <Field label="Horizon starts (midnight, Asia/Kolkata)">
                <input type="date" value={start} onChange={(e) => setStart(e.target.value)} required />
              </Field>
              <Field label="Number of days" hint={`Ends ${fmtDate(end)}`}>
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={days}
                  onChange={(e) => setDays(Math.min(31, Math.max(1, Number(e.target.value) || 1)))}
                />
              </Field>
              <Field label="Solver time limit (seconds)" hint="More time can find a better plan">
                <input
                  type="number"
                  min={1}
                  max={600}
                  value={timeLimit}
                  onChange={(e) => setTimeLimit(Math.min(600, Math.max(1, Number(e.target.value) || 1)))}
                />
              </Field>
            </div>
            <button type="button" className="link" onClick={() => setAdvanced((v) => !v)}>
              {advanced ? 'Hide' : 'Show'} objective weights
            </button>
            {advanced && (
              <div className="form-grid">
                {(Object.keys(DEFAULT_WEIGHTS) as (keyof PlanWeights)[]).map((key) => (
                  <Field key={key} label={`Weight: ${key}`} hint={WEIGHT_HELP[key]}>
                    <input
                      type="number"
                      min={0}
                      value={weights[key]}
                      onChange={(e) => setWeights({ ...weights, [key]: Math.max(0, Number(e.target.value) || 0) })}
                    />
                  </Field>
                ))}
              </div>
            )}
            <div className="button-row">
              <button type="submit" className="btn btn-primary" disabled={busy || (current ? ACTIVE.includes(current.status) : false)}>
                Run plan
              </button>
              <button type="button" className="btn" onClick={loadTraffic} disabled={busy}>
                Load simulated traffic for this horizon
              </button>
            </div>
            {info && (
              <div className="alert alert-ok" role="status">
                {info}
              </div>
            )}
            <ErrorMessage error={error} />
          </form>
        )}

        {current && (
          <div className="run-status" aria-live="polite">
            <strong>Run #{current.id}</strong> <StatusBadge status={current.status} />{' '}
            {ACTIVE.includes(current.status) && (
              <span className="muted">
                <span className="spinner" aria-hidden="true" /> solving, up to {current.time_limit_s} seconds. This page
                checks every 2 seconds.
                <span className="progress" aria-hidden="true">
                  <i />
                </span>
              </span>
            )}
            {current.status === 'succeeded' && (
              <span>
                {' '}
                <Link to={`/plans/${current.id}`}>Open the plan</Link>
                {current.metrics &&
                  ` · closures ${current.metrics.baseline.closures} → ${current.metrics.integrated.closures}`}
              </span>
            )}
            {['failed', 'infeasible'].includes(current.status) && (
              <span className="error-text"> {current.error ?? 'The run did not produce a plan.'}</span>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h2>Past runs</h2>
        {plans.loading && !plans.data ? (
          <Loading label="Loading plans" />
        ) : plans.error && !plans.data ? (
          <ErrorMessage error={plans.error} onRetry={plans.reload} />
        ) : !plans.data || plans.data.items.length === 0 ? (
          <Empty title="No plans yet">
            {mayRun ? 'Run the first plan with the form above.' : 'A planner has not run a plan yet.'}
          </Empty>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Plan</th>
                <th>Status</th>
                <th>Horizon</th>
                <th>Closures</th>
                <th>Block hours</th>
                <th>Trains</th>
                <th>Solver</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {plans.data.items.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link to={`/plans/${p.id}`}>#{p.id}</Link>
                    {p.parent_id && <span className="muted"> (override of #{p.parent_id})</span>}
                  </td>
                  <td>
                    <StatusBadge status={p.status} />
                  </td>
                  <td>
                    {fmtDate(p.horizon_start)} to {fmtDate(p.horizon_end)}
                  </td>
                  <td>{pair(p, 'closures')}</td>
                  <td>{pair(p, 'block_hours')}</td>
                  <td>{pair(p, 'trains_affected')}</td>
                  <td>{solverBadge(p.solver_status)}</td>
                  <td>{fmtDateTime(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted table-foot">Closures, hours and trains: independent → integrated.</p>
      </section>
    </div>
  )
}

function pair(plan: Plan, key: 'closures' | 'block_hours' | 'trains_affected') {
  if (!plan.metrics) return '-'
  const before = plan.metrics.baseline[key]
  const after = plan.metrics.integrated[key]
  const cut = percentReduction(before, after)
  return (
    <span className="metric">
      <span className="metric-before">{before}</span> → <span className="metric-after">{after}</span>
      {cut !== null && cut !== 0 && (
        <small className={`metric-delta ${cut > 0 ? 'good-text' : 'bad-text'}`}>
          {cut > 0 ? `-${cut}%` : `+${-cut}%`}
        </small>
      )}
    </span>
  )
}

function solverBadge(status: string | null) {
  if (!status) return '-'
  const tone = status.toLowerCase() === 'optimal' ? 'good' : status.toLowerCase() === 'feasible' ? 'warn' : 'neutral'
  return <span className={`badge badge-${tone}`}>{status}</span>
}
