import { useState } from 'react'
import { api } from '../../api'
import { ApiError } from '../../api/client'
import type { BlockRequest, Dependency, Relation } from '../../api/types'
import { RELATIONS } from '../../api/types'
import { ErrorMessage, Modal } from '../../components/ui'

const RELATION_TEXT: Record<Relation, string> = {
  finish_before_start: 'must finish before this one starts',
  not_same_block: 'must not share a day with this one',
  same_block_allowed: 'may share a block (no rule)',
}

interface Props {
  request: BlockRequest
  /** Other requests that can be depended on (the page loads and filters them). */
  candidates: BlockRequest[]
  onSaved(request: BlockRequest): void
  onClose(): void
}

export function DependencyEditor({ request, candidates, onSaved, onClose }: Props) {
  const [rows, setRows] = useState<Dependency[]>(request.dependencies)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const used = new Set(rows.map((r) => r.depends_on))
  const available = candidates.filter((c) => c.id !== request.id && !used.has(c.id))

  const update = (index: number, patch: Partial<Dependency>) =>
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)))

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      onSaved(await api.setDependencies(request.id, rows, request.version))
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, 'error', String(e)))
      setBusy(false)
    }
  }

  return (
    <Modal title={`Dependencies of R${request.id}`} onClose={onClose} wide>
      <div className="modal-body">
        <p className="muted">
          R{request.id} ({request.department}, {request.section_code}) depends on the requests below. A loop of
          dependencies is rejected by the server.
        </p>
        {rows.length === 0 && <p className="empty-inline">No dependencies.</p>}
        {rows.map((row, index) => {
          const target = candidates.find((c) => c.id === row.depends_on)
          return (
            <div className="dep-row" key={row.depends_on}>
              <strong>R{row.depends_on}</strong>
              <span className="muted">{target ? `${target.department} · ${target.section_code}` : ''}</span>
              <select
                aria-label={`Relation to R${row.depends_on}`}
                value={row.relation}
                onChange={(e) => update(index, { relation: e.target.value as Relation })}
              >
                {RELATIONS.map((r) => (
                  <option key={r} value={r}>
                    R{row.depends_on} {RELATION_TEXT[r]}
                  </option>
                ))}
              </select>
              <label className="inline-field">
                Gap (min)
                <input
                  type="number"
                  min={0}
                  max={1440}
                  step={15}
                  disabled={row.relation !== 'finish_before_start'}
                  value={row.min_gap_minutes}
                  onChange={(e) => update(index, { min_gap_minutes: Number(e.target.value) })}
                />
              </label>
              <button
                type="button"
                className="btn btn-small"
                onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
              >
                Remove
              </button>
            </div>
          )
        })}
        <div className="dep-add">
          <select
            aria-label="Add a dependency"
            value=""
            onChange={(e) => {
              const id = Number(e.target.value)
              if (id) setRows((current) => [...current, { depends_on: id, relation: 'finish_before_start', min_gap_minutes: 0 }])
            }}
          >
            <option value="">Add a dependency...</option>
            {available.map((c) => (
              <option key={c.id} value={c.id}>
                R{c.id} · {c.department} · {c.section_code} · {c.work_type} · {c.status}
              </option>
            ))}
          </select>
        </div>
      </div>
      <ErrorMessage error={error} />
      <footer className="modal-footer">
        <button type="button" className="btn" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>
          {busy ? 'Saving...' : 'Save dependencies'}
        </button>
      </footer>
    </Modal>
  )
}
