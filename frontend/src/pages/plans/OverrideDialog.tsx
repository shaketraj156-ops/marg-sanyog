import { useState } from 'react'
import { api } from '../../api'
import type { Move, Plan, Schedule } from '../../api/types'
import { ErrorMessage, Field, Modal } from '../../components/ui'
import { istFromLocalInput } from '../../lib/time'
import { movableRequests } from './moves'

interface Row {
  requestId: number
  start: string
}

/** Several moves at once, applied as one override (a child plan). */
export function OverrideDialog({
  plan,
  schedule,
  onClose,
  onDone,
}: {
  plan: Plan
  schedule: Schedule
  onClose(): void
  onDone(child: Plan): void
}) {
  const movable = movableRequests(schedule)
  const [rows, setRows] = useState<Row[]>(movable[0] ? [{ requestId: movable[0].requestId, start: movable[0].startLocal }] : [])
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const used = new Set(rows.map((r) => r.requestId))
  const free = movable.filter((m) => !used.has(m.requestId))

  const apply = async () => {
    setBusy(true)
    setError(null)
    try {
      const moves: Move[] = rows.map((r) => ({ request_id: r.requestId, start: istFromLocalInput(r.start) }))
      onDone(await api.override(plan.id, moves, 10))
    } catch (e) {
      setError(e)
      setBusy(false)
    }
  }

  return (
    <Modal title={`Override plan #${plan.id}`} onClose={onClose} wide>
      <div className="modal-body">
        <p className="muted">
          Choose the requests to move and their new start times. The planner re-solves the rest and saves the result as
          a new plan. If the moves cannot be combined into a valid plan, nothing is created.
        </p>
        {rows.map((row, index) => (
          <div className="move-row" key={row.requestId}>
            <Field label="Request">
              <select
                value={row.requestId}
                onChange={(e) => {
                  const found = movable.find((m) => m.requestId === Number(e.target.value))
                  if (found) setRows(rows.map((r, i) => (i === index ? { requestId: found.requestId, start: found.startLocal } : r)))
                }}
              >
                {movable
                  .filter((m) => m.requestId === row.requestId || !used.has(m.requestId))
                  .map((m) => (
                    <option key={m.requestId} value={m.requestId}>
                      {m.summary}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="New start (Asia/Kolkata)">
              <input
                type="datetime-local"
                step={1800}
                value={row.start}
                onChange={(e) => setRows(rows.map((r, i) => (i === index ? { ...r, start: e.target.value } : r)))}
              />
            </Field>
            <button type="button" className="btn btn-small" onClick={() => setRows(rows.filter((_, i) => i !== index))}>
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn btn-small"
          disabled={free.length === 0}
          onClick={() => free[0] && setRows([...rows, { requestId: free[0].requestId, start: free[0].startLocal }])}
        >
          Add another move
        </button>
      </div>
      <ErrorMessage error={error} />
      <footer className="modal-footer">
        <button type="button" className="btn" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" onClick={apply} disabled={busy || rows.length === 0}>
          {busy ? 'Solving...' : 'Create the override plan'}
        </button>
      </footer>
    </Modal>
  )
}
