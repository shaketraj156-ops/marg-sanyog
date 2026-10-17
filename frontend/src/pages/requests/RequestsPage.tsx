import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import type { BlockRequest } from '../../api/types'
import { REQUEST_STATUSES } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { ConfirmDialog, DeptChip, Empty, ErrorMessage, Field, Loading, Modal, StatusBadge } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { deptColor } from '../../lib/gantt'
import { canActOnRequest, canCreateRequests, canRejectRequests, stateActions } from '../../lib/permissions'
import { fmtDate, fmtDateTime, fmtDuration } from '../../lib/time'
import { DependencyEditor } from './DependencyEditor'
import { RequestForm } from './RequestForm'
import { describeError } from '../../lib/errors'

type Dialog =
  | { kind: 'create' }
  | { kind: 'edit'; request: BlockRequest }
  | { kind: 'deps'; request: BlockRequest }
  | { kind: 'cancel'; request: BlockRequest }
  | { kind: 'reject'; request: BlockRequest }
  | { kind: 'detail'; request: BlockRequest }

async function loadAll(filters: { status: string; section: string; department: string }) {
  const items: BlockRequest[] = []
  let cursor: number | null = null
  for (let page = 0; page < 5; page++) {
    const batch = await api.requests({ ...filters, limit: 200, cursor })
    items.push(...batch.items)
    cursor = batch.next_cursor
    if (cursor === null) break
  }
  return { items, truncated: cursor !== null }
}

export function RequestsPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const filters = {
    status: params.get('status') ?? '',
    section: params.get('section') ?? '',
    department: params.get('department') ?? '',
  }
  const list = useAsync(() => loadAll(filters), [filters.status, filters.section, filters.department])
  const reference = useAsync(async () => ({ sections: await api.sections(), departments: await api.departments() }), [])
  const everything = useAsync(() => loadAll({ status: '', section: '', department: '' }), [])

  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [notice, setNotice] = useState<{ tone: 'good' | 'warn' | 'bad'; text: string } | null>(null)
  const [actionError, setActionError] = useState<unknown>(null)

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const refresh = () => {
    list.reload()
    everything.reload()
  }

  const saved = (request: BlockRequest, message: string) => {
    setDialog(null)
    setActionError(null)
    const warning = request.warnings[0]
    setNotice(warning ? { tone: 'warn', text: `${message} Warning: ${warning.detail}.` } : { tone: 'good', text: message })
    refresh()
  }

  const submit = async (request: BlockRequest) => {
    setActionError(null)
    try {
      const updated = await api.submitRequest(request.id, request.version)
      saved(updated, `R${updated.id} was submitted for planning.`)
    } catch (e) {
      setActionError(e)
    }
  }

  if (!user) return null
  const sections = reference.data?.sections ?? []
  const departments = reference.data?.departments ?? []
  const allItems = everything.data?.items

  return (
    <div className="stack">
      <div className="page-title">
        <div>
          <h1>Block requests</h1>
          <p className="page-sub">Maintenance closures asked for by Engineering, TrD and S&amp;T. Submitted requests are planned together.</p>
        </div>
        {canCreateRequests(user) ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setDialog({ kind: 'create' })}
            disabled={!reference.data}
          >
            New request
          </button>
        ) : (
          <span className="muted">Read-only view: your role cannot create requests.</span>
        )}
      </div>

      {notice && (
        <div className={`alert alert-${notice.tone === 'good' ? 'ok' : notice.tone === 'warn' ? 'warn' : 'error'}`} role="status">
          <span>{notice.text}</span>
          <button type="button" className="btn btn-small" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
      <ErrorMessage error={actionError} />

      {allItems && (
        <div className="stat-strip" aria-label="Requests at a glance">
          <button
            type="button"
            className={`stat-tile${!filters.status ? ' active' : ''}`}
            onClick={() => setFilter('status', '')}
          >
            <span className="stat-num">{allItems.length}</span>
            <span className="stat-name">all requests</span>
          </button>
          {(['draft', 'submitted', 'scheduled', 'published'] as const).map((status) => (
            <button
              key={status}
              type="button"
              className={`stat-tile${filters.status === status ? ' active' : ''}`}
              onClick={() => setFilter('status', status)}
            >
              <span className="stat-num">{allItems.filter((r) => r.status === status).length}</span>
              <span className="stat-name">{status}</span>
            </button>
          ))}
        </div>
      )}

      <div className="filters card">
        <Field label="Status">
          <select value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
            <option value="">All</option>
            {REQUEST_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Section">
          <select value={filters.section} onChange={(e) => setFilter('section', e.target.value)}>
            <option value="">All</option>
            {sections.map((s) => (
              <option key={s.id} value={s.code}>
                {s.code}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Department">
          <select value={filters.department} onChange={(e) => setFilter('department', e.target.value)}>
            <option value="">All</option>
            {departments.map((d) => (
              <option key={d.id} value={d.code}>
                {d.code}
              </option>
            ))}
          </select>
        </Field>
        {(filters.status || filters.section || filters.department) && (
          <button type="button" className="btn btn-small" onClick={() => setParams({}, { replace: true })}>
            Clear filters
          </button>
        )}
      </div>

      {list.loading && !list.data ? (
        <Loading label="Loading requests" />
      ) : list.error ? (
        <ErrorMessage error={list.error} onRetry={list.reload} />
      ) : list.data && list.data.items.length === 0 ? (
        <Empty title="No requests match">
          {filters.status || filters.section || filters.department
            ? 'Try clearing the filters.'
            : 'Create the first request with the button above.'}
        </Empty>
      ) : (
        list.data && (
          <div className="card table-card">
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Dept</th>
                  <th>Section</th>
                  <th>Work</th>
                  <th>Duration</th>
                  <th>Window</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Deps</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((r) => {
                  const mine = canActOnRequest(user, r)
                  const allowed = stateActions(r)
                  return (
                    <tr key={r.id} className="req-row" style={{ '--dept': deptColor(r.department) } as CSSProperties}>
                      <td>
                        <button type="button" className="link" onClick={() => setDialog({ kind: 'detail', request: r })}>
                          R{r.id}
                        </button>
                      </td>
                      <td>
                        <DeptChip dept={r.department} />
                      </td>
                      <td>{r.section_code}</td>
                      <td>
                        <span className="tag">{r.work_type}</span>
                      </td>
                      <td>{fmtDuration(r.duration_minutes)}</td>
                      <td>
                        {fmtDate(r.earliest_date)} to {fmtDate(r.deadline_date)}
                      </td>
                      <td>
                        <span className={`prio prio-${r.priority}`}>{r.priority}</span>
                      </td>
                      <td>
                        <StatusBadge status={r.status} />
                      </td>
                      <td>{r.dependencies.length || '-'}</td>
                      <td className="actions">
                        {mine && allowed.edit && (
                          <button type="button" className="btn btn-small" onClick={() => setDialog({ kind: 'edit', request: r })}>
                            Edit
                          </button>
                        )}
                        {mine && allowed.edit && (
                          <button type="button" className="btn btn-small" onClick={() => setDialog({ kind: 'deps', request: r })}>
                            Dependencies
                          </button>
                        )}
                        {mine && allowed.submit && (
                          <button type="button" className="btn btn-small btn-primary" onClick={() => submit(r)}>
                            Submit
                          </button>
                        )}
                        {canRejectRequests(user) && allowed.reject && (
                          <button type="button" className="btn btn-small" onClick={() => setDialog({ kind: 'reject', request: r })}>
                            Reject
                          </button>
                        )}
                        {mine && allowed.cancel && (
                          <button type="button" className="btn btn-small btn-danger-outline" onClick={() => setDialog({ kind: 'cancel', request: r })}>
                            Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="muted table-foot">
              {list.data.items.length} request{list.data.items.length === 1 ? '' : 's'}
              {list.data.truncated ? ' (showing the first 1000)' : ''}
            </p>
          </div>
        )
      )}

      {dialog?.kind === 'create' && user && reference.data && (
        <RequestForm
          mode="create"
          user={user}
          sections={sections}
          departments={departments}
          onClose={() => setDialog(null)}
          onSaved={(r) => saved(r, `Draft R${r.id} was created. Submit it when it is ready.`)}
        />
      )}
      {dialog?.kind === 'edit' && user && reference.data && (
        <RequestForm
          mode="edit"
          request={dialog.request}
          user={user}
          sections={sections}
          departments={departments}
          onClose={() => setDialog(null)}
          onSaved={(r) => saved(r, `R${r.id} was updated.`)}
        />
      )}
      {dialog?.kind === 'deps' && (
        <DependencyEditor
          request={dialog.request}
          candidates={(everything.data?.items ?? []).filter((c) => c.status !== 'cancelled')}
          onClose={() => setDialog(null)}
          onSaved={(r) => saved(r, `Dependencies of R${r.id} were saved.`)}
        />
      )}
      {dialog?.kind === 'cancel' && (
        <ConfirmDialog
          title={`Cancel R${dialog.request.id}?`}
          confirmLabel="Cancel the request"
          tone="danger"
          onClose={() => setDialog(null)}
          onConfirm={async () => {
            const updated = await api.cancelRequest(dialog.request.id, dialog.request.version)
            saved(updated, `R${updated.id} was cancelled.`)
          }}
        >
          <p>
            R{dialog.request.id} ({dialog.request.department}, {dialog.request.section_code}) will no longer be planned.
            This cannot be undone.
          </p>
        </ConfirmDialog>
      )}
      {dialog?.kind === 'reject' && (
        <RejectDialog
          request={dialog.request}
          onClose={() => setDialog(null)}
          onDone={(r) => saved(r, `R${r.id} was rejected.`)}
        />
      )}
      {dialog?.kind === 'detail' && <DetailDialog request={dialog.request} onClose={() => setDialog(null)} />}
    </div>
  )
}

function RejectDialog({
  request,
  onClose,
  onDone,
}: {
  request: BlockRequest
  onClose(): void
  onDone(request: BlockRequest): void
}) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const reject = async () => {
    setBusy(true)
    setError(null)
    try {
      onDone(await api.rejectRequest(request.id, reason.trim(), request.version))
    } catch (e) {
      setError(e)
      setBusy(false)
    }
  }
  return (
    <Modal title={`Reject R${request.id}`} onClose={onClose}>
      <div className="modal-body">
        <Field label="Reason (recorded in the audit log)">
          <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
        </Field>
      </div>
      {error ? <div className="alert alert-error" role="alert">{describeError(error)}</div> : null}
      <footer className="modal-footer">
        <button type="button" className="btn" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" className="btn btn-danger" onClick={reject} disabled={busy || !reason.trim()}>
          Reject request
        </button>
      </footer>
    </Modal>
  )
}

function DetailDialog({ request: r, onClose }: { request: BlockRequest; onClose(): void }) {
  const rows: [string, string][] = [
    ['Department', r.department],
    ['Section', r.section_code],
    ['Work type', r.work_type],
    ['Duration', fmtDuration(r.duration_minutes)],
    ['Window', `${fmtDate(r.earliest_date)} to ${fmtDate(r.deadline_date)}`],
    ['Priority', String(r.priority)],
    ['Power block', r.needs_power_block ? 'needed' : 'no'],
    ['Preferred start', fmtDateTime(r.preferred_start)],
    ['Description', r.description ?? '-'],
    ['Version', String(r.version)],
    ['Created', fmtDateTime(r.created_at)],
    ['Updated', fmtDateTime(r.updated_at)],
  ]
  return (
    <Modal title={`Request R${r.id}`} onClose={onClose}>
      <div className="modal-body">
        <p>
          <StatusBadge status={r.status} />
        </p>
        <dl className="details">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        <h3>Dependencies</h3>
        {r.dependencies.length === 0 ? (
          <p className="muted">None.</p>
        ) : (
          <ul>
            {r.dependencies.map((d) => (
              <li key={d.depends_on}>
                depends on R{d.depends_on}: {d.relation.replaceAll('_', ' ')}
                {d.relation === 'finish_before_start' && d.min_gap_minutes ? `, gap ${d.min_gap_minutes} min` : ''}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  )
}
