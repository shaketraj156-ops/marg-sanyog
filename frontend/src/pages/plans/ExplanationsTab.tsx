import { useState } from 'react'
import { api } from '../../api'
import type { Plan } from '../../api/types'
import { Empty, ErrorMessage, Loading } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'

const CODE_HELP: Record<string, string> = {
  MERGED: 'Several requests share one block',
  LOW_TRAFFIC: 'The window is among the quietest',
  DEADLINE_DRIVEN: 'Placed after its earliest date',
  DEPENDENCY_ORDER: 'Placed after another request',
  DEFERRED: 'Not placed, with the reason',
  OVERRIDE: 'Moved by a planner',
}

function show(value: unknown): string {
  if (Array.isArray(value)) return value.map((v) => (typeof v === 'number' ? `R${v}` : String(v))).join(', ')
  if (value === null || value === undefined) return '-'
  return String(value)
}

export function ExplanationsTab({ plan }: { plan: Plan }) {
  const { data, error, loading, reload } = useAsync(() => api.explanations(plan.id), [plan.id])
  const [code, setCode] = useState('')
  if (loading && !data) return <Loading label="Loading explanations" />
  if (error) return <ErrorMessage error={error} onRetry={reload} />
  if (!data) return null
  if (data.items.length === 0) return <Empty title="No explanations">This plan has nothing to explain yet.</Empty>

  const codes = [...new Set(data.items.map((i) => i.code))]
  const items = code ? data.items.filter((i) => i.code === code) : data.items
  return (
    <div className="stack-small">
      <p className="muted">
        Every reason comes with the numbers it was computed from. Nothing here is free-form text about the data.
      </p>
      <div className="chip-row" role="group" aria-label="Filter by reason code">
        <button type="button" className={`chip-button${code === '' ? ' active' : ''}`} onClick={() => setCode('')}>
          All ({data.items.length})
        </button>
        {codes.map((c) => (
          <button
            key={c}
            type="button"
            className={`chip-button${code === c ? ' active' : ''}`}
            onClick={() => setCode(c)}
            title={CODE_HELP[c]}
          >
            {c} ({data.items.filter((i) => i.code === c).length})
          </button>
        ))}
      </div>
      {items.map((item) => (
        <article className="card explanation" key={item.id}>
          <header>
            <span className={`badge badge-code code-${item.code}`}>{item.code}</span>
            {item.request_id && <span className="muted">R{item.request_id}</span>}
          </header>
          <p>{item.text}</p>
          <dl className="numbers">
            {Object.entries(item.numbers).map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll('_', ' ')}</dt>
                <dd>{show(value)}</dd>
              </div>
            ))}
          </dl>
        </article>
      ))}
    </div>
  )
}
