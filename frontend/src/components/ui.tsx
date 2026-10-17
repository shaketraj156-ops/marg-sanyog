import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { describeError } from '../lib/errors'
import { deptColor } from '../lib/gantt'

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}...
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  )
}

export function ErrorMessage({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null
  return (
    <div className="alert alert-error" role="alert">
      <span>{describeError(error)}</span>
      {onRetry && (
        <button type="button" className="btn btn-small" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

const STATUS_TONE: Record<string, string> = {
  draft: 'neutral',
  submitted: 'info',
  scheduled: 'warn',
  published: 'good',
  completed: 'good',
  cancelled: 'muted',
  rejected: 'bad',
  queued: 'neutral',
  running: 'info',
  succeeded: 'good',
  approved: 'warn',
  failed: 'bad',
  infeasible: 'bad',
  superseded: 'muted',
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge badge-${STATUS_TONE[status] ?? 'neutral'}`}>{status}</span>
}

export function DeptChip({ dept }: { dept: string }) {
  return (
    <span className="chip" style={{ borderColor: deptColor(dept) }}>
      <i className="dot" style={{ background: deptColor(dept) }} />
      {dept}
    </span>
  )
}

export function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string
  error?: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className={`field${error ? ' field-invalid' : ''}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && !error && <span className="field-hint">{hint}</span>}
      {error && (
        <span className="field-error" role="alert">
          {error}
        </span>
      )}
    </label>
  )
}

export function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    ref.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        className={`modal${wide ? ' modal-wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={ref}
      >
        <header className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="btn btn-ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        {children}
      </div>
    </div>
  )
}

export function ConfirmDialog({
  title,
  confirmLabel,
  tone = 'primary',
  onConfirm,
  onClose,
  children,
}: {
  title: string
  confirmLabel: string
  tone?: 'primary' | 'danger'
  onConfirm: () => Promise<void>
  onClose: () => void
  children: ReactNode
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      await onConfirm()
    } catch (e) {
      setError(e)
      setBusy(false)
    }
  }
  return (
    <Modal title={title} onClose={onClose}>
      <div className="modal-body">{children}</div>
      <ErrorMessage error={error} />
      <footer className="modal-footer">
        <button type="button" className="btn" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" className={`btn btn-${tone}`} onClick={run} disabled={busy}>
          {busy ? 'Working...' : confirmLabel}
        </button>
      </footer>
    </Modal>
  )
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: T; label: string }[]
  active: T
  onChange: (id: T) => void
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          type="button"
          aria-selected={tab.id === active}
          className={`tab${tab.id === active ? ' tab-active' : ''}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

export function KpiCard({
  label,
  value,
  note,
  tone = 'neutral',
  accent = 'blue',
}: {
  label: string
  value: string
  note?: string
  tone?: 'neutral' | 'good' | 'bad'
  accent?: 'blue' | 'amber' | 'green' | 'purple'
}) {
  return (
    <div className={`kpi kpi-${accent}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {note && <div className={`kpi-note kpi-note-${tone}`}>{note}</div>}
    </div>
  )
}
