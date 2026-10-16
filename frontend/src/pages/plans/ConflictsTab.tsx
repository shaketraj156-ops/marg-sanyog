import { api } from '../../api'
import type { Plan } from '../../api/types'
import { Empty, ErrorMessage, Loading } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'

const TITLES: Record<string, string> = {
  SECTION_COMPETITION: 'Several requests want the same section',
  DEPENDENCY: 'Ordering rule between requests',
  UNPLACED: 'Request that could not be planned',
}

const RESOLUTION_TONE: Record<string, string> = {
  MERGED: 'good',
  ORDERED: 'good',
  SEPARATED_DAYS: 'good',
  SEPARATED: 'info',
  DEFERRED: 'warn',
}

export function ConflictsTab({ plan }: { plan: Plan }) {
  const { data, error, loading, reload } = useAsync(() => api.conflicts(plan.id), [plan.id])
  if (loading && !data) return <Loading label="Loading conflicts" />
  if (error) return <ErrorMessage error={error} onRetry={reload} />
  if (!data) return null
  if (data.conflicts.length === 0) {
    return <Empty title="No conflicts">No two requests competed for the same section, and no ordering rules applied.</Empty>
  }
  return (
    <div className="stack-small">
      <p className="muted">Conflicts found in the input and how the plan resolved each one.</p>
      {data.conflicts.map((c, index) => (
        <article className="card conflict" key={index}>
          <header>
            <span className="badge badge-neutral">{c.type.replaceAll('_', ' ').toLowerCase()}</span>
            <h3>{TITLES[c.type] ?? c.type}</h3>
          </header>
          <p>{c.detail}</p>
          <p>
            <span className={`badge badge-${RESOLUTION_TONE[c.resolution] ?? 'neutral'}`}>{c.resolution}</span>{' '}
            {c.resolution_detail}
          </p>
          <p className="muted">
            Requests: {c.request_ids.map((id) => `R${id}`).join(', ')}
            {c.departments ? ` · Departments: ${c.departments.join(', ')}` : ''}
          </p>
        </article>
      ))}
    </div>
  )
}
