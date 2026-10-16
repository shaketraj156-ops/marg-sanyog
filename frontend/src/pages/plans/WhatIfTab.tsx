import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../../api'
import type { Plan, PlanMetrics, Schedule, WhatIfResult } from '../../api/types'
import { ConfirmDialog, Empty, ErrorMessage, Field } from '../../components/ui'
import { fmtDateTime, fmtHours, istFromLocalInput } from '../../lib/time'
import { movableRequests } from './moves'

const ROWS: { key: keyof PlanMetrics; label: string; hours?: boolean }[] = [
  { key: 'closures', label: 'Closures' },
  { key: 'block_hours', label: 'Block hours', hours: true },
  { key: 'trains_affected', label: 'Trains affected' },
  { key: 'traffic_cost', label: 'Traffic cost' },
  { key: 'weighted_postponement_days', label: 'Postponement' },
  { key: 'deferred', label: 'Not placed' },
]

interface Props {
  plan: Plan
  schedule: Schedule
  canReview: boolean
  onOverridden(child: Plan): void
}

export function WhatIfTab({ plan, schedule, canReview, onOverridden }: Props) {
  const movable = movableRequests(schedule)
  const [requestId, setRequestId] = useState<number | ''>(movable[0]?.requestId ?? '')
  const [start, setStart] = useState(movable[0]?.startLocal ?? '')
  const [limit, setLimit] = useState(5)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [result, setResult] = useState<WhatIfResult | null>(null)
  const [confirm, setConfirm] = useState(false)

  if (!canReview) {
    return (
      <Empty title="Planners and administrators only">
        What-if moves re-solve the plan. Your role can read plans but not try changes.
      </Empty>
    )
  }
  if (movable.length === 0) return <Empty title="Nothing to move">This plan has no placed requests.</Empty>
  if (!['succeeded', 'approved'].includes(plan.status)) {
    return <Empty title="Not available">Only a succeeded or approved plan can be explored (this one is {plan.status}).</Empty>
  }

  const choose = (id: number) => {
    setRequestId(id)
    setResult(null)
    const found = movable.find((m) => m.requestId === id)
    if (found) setStart(found.startLocal)
  }

  const move = () => ({ request_id: Number(requestId), start: istFromLocalInput(start) })

  const run = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.whatIf(plan.id, { ...move(), time_limit_s: limit }))
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <form className="card stack-small" onSubmit={run}>
        <h2>Try a move (nothing is saved)</h2>
        <p className="muted">
          Pick a request and a new start time. The planner re-solves everything else around it and shows what would
          change. Use "Apply as override" to keep the result as a new plan.
        </p>
        <div className="form-grid">
          <Field label="Request">
            <select value={requestId} onChange={(e) => choose(Number(e.target.value))}>
              {movable.map((m) => (
                <option key={m.requestId} value={m.requestId}>
                  {m.summary}
                </option>
              ))}
            </select>
          </Field>
          <Field label="New start (Asia/Kolkata)" hint="On a 30-minute boundary">
            <input type="datetime-local" step={1800} value={start} onChange={(e) => setStart(e.target.value)} required />
          </Field>
          <Field label="Time limit (seconds)">
            <input
              type="number"
              min={1}
              max={60}
              value={limit}
              onChange={(e) => setLimit(Math.min(60, Math.max(1, Number(e.target.value) || 1)))}
            />
          </Field>
        </div>
        <div className="button-row">
          <button type="submit" className="btn btn-primary" disabled={busy || !start || requestId === ''}>
            {busy ? 'Solving...' : 'Try this move'}
          </button>
        </div>
        <ErrorMessage error={error} />
      </form>

      {result && !result.feasible && (
        <div className="alert alert-warn" role="status">
          <strong>Not possible.</strong> {result.reason}
        </div>
      )}

      {result?.feasible && result.metrics && (
        <div className="card stack-small" aria-live="polite">
          <h2>What would change</h2>
          {result.target && (
            <p>
              R{result.target.request_id}: {result.target.from ? fmtDateTime(result.target.from.start) : 'not placed'} →{' '}
              <strong>{result.target.to ? fmtDateTime(result.target.to.start) : 'not placed'}</strong>
            </p>
          )}
          <table className="table">
            <thead>
              <tr>
                <th>Measure</th>
                <th>Current plan</th>
                <th>With the move</th>
                <th>Difference</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map(({ key, label, hours }) => {
                const diff = result.metrics!.difference[key]
                const show = (v: number) => (hours ? fmtHours(v) : String(v))
                return (
                  <tr key={key}>
                    <td>{label}</td>
                    <td>{show(result.metrics!.current[key])}</td>
                    <td>{show(result.metrics!.whatif[key])}</td>
                    <td className={diff === 0 ? '' : diff < 0 ? 'good-text' : 'bad-text'}>
                      {diff > 0 ? '+' : ''}
                      {hours ? fmtHours(diff) : diff}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="muted">Lower is better for every measure. Solver: {result.solver_status}.</p>
          {result.moved_requests && result.moved_requests.length > 0 ? (
            <>
              <h3>Other requests that would move</h3>
              <ul className="plain-list">
                {result.moved_requests.map((m) => (
                  <li key={m.request_id}>
                    <strong>{m.request}</strong>: {m.from ? fmtDateTime(m.from.start) : 'not placed'} →{' '}
                    {m.to ? fmtDateTime(m.to.start) : 'not placed'}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted">No other request would move.</p>
          )}
          <div className="button-row">
            <button type="button" className="btn btn-primary" onClick={() => setConfirm(true)}>
              Apply as override
            </button>
          </div>
        </div>
      )}

      {confirm && (
        <ConfirmDialog
          title="Apply this move as an override?"
          confirmLabel="Create the override plan"
          onClose={() => setConfirm(false)}
          onConfirm={async () => {
            const child = await api.override(plan.id, [move()], Math.max(limit, 10))
            onOverridden(child)
          }}
        >
          <p>
            This creates a new plan that is a child of plan #{plan.id}. Plan #{plan.id} stays on record unchanged. You
            can approve either one afterwards, but not both.
          </p>
        </ConfirmDialog>
      )}
    </div>
  )
}
