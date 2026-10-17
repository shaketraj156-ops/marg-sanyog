import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import type { BlockRequest, Plan, RequestStatus } from '../api/types'
import { REQUEST_STATUSES } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { CompareChart } from '../components/CompareChart'
import { Empty, ErrorMessage, KpiCard, Loading, StatusBadge } from '../components/ui'
import { useAsync } from '../hooks/useAsync'
import { canRunPlans } from '../lib/permissions'
import { fmtDateTime, fmtHours, percentReduction } from '../lib/time'

const READY = ['succeeded', 'approved', 'published']
const STATUS_COLORS: Record<RequestStatus, string> = {
  draft: '#8794a6',
  submitted: '#124b8f',
  scheduled: '#e08a00',
  published: '#1b8a5a',
  completed: '#0b5d3b',
  cancelled: '#b7c0cc',
  rejected: '#c0392b',
}

async function loadDashboard() {
  const plans = await api.plans({ limit: 50 })
  const latest: Plan | undefined = plans.items.find((p) => READY.includes(p.status) && p.metrics)

  const requests: BlockRequest[] = []
  let cursor: number | null = null
  for (let page = 0; page < 10; page++) {
    const batch = await api.requests({ limit: 200, cursor })
    requests.push(...batch.items)
    cursor = batch.next_cursor
    if (cursor === null) break
  }
  const counts = Object.fromEntries(REQUEST_STATUSES.map((s) => [s, 0])) as Record<RequestStatus, number>
  for (const request of requests) counts[request.status] += 1
  return { latest, counts, total: requests.length, planCount: plans.items.length }
}

function reductionNote(before: number, after: number): { text: string; tone: 'good' | 'bad' | 'neutral' } {
  const cut = percentReduction(before, after)
  if (cut === null) return { text: 'no baseline', tone: 'neutral' }
  if (cut === 0) return { text: 'same as independent', tone: 'neutral' }
  return cut > 0
    ? { text: `${cut}% lower than independent (${before})`, tone: 'good' }
    : { text: `${-cut}% higher than independent (${before})`, tone: 'bad' }
}

export function DashboardPage() {
  const { user } = useAuth()
  const { data, error, loading, reload } = useAsync(loadDashboard, [])

  if (loading && !data) return <Loading label="Loading the dashboard" />
  if (error && !data) return <ErrorMessage error={error} onRetry={reload} />
  if (!data) return null

  const { latest, counts, total } = data
  const metrics = latest?.metrics
  const statusData = REQUEST_STATUSES.map((status) => ({ status, count: counts[status] }))
  const reductions = metrics
    ? [
        percentReduction(metrics.baseline.closures, metrics.integrated.closures),
        percentReduction(metrics.baseline.block_hours, metrics.integrated.block_hours),
        percentReduction(metrics.baseline.trains_affected, metrics.integrated.trains_affected),
      ].filter((v): v is number => v !== null)
    : []
  const closuresNote = metrics && reductionNote(metrics.baseline.closures, metrics.integrated.closures)
  const hoursNote = metrics && reductionNote(metrics.baseline.block_hours, metrics.integrated.block_hours)
  const trainsNote = metrics && reductionNote(metrics.baseline.trains_affected, metrics.integrated.trains_affected)
  const average = reductions.length ? Math.round(reductions.reduce((a, b) => a + b, 0) / reductions.length) : null
  const firstName = user?.name.split(/\s+/)[0] ?? ''
  const waiting = counts.submitted
  const summary =
    total === 0
      ? 'No requests yet. Create one on the Requests page to get started.'
      : `${total} ${total === 1 ? 'request' : 'requests'} in the system, ${waiting} waiting to be planned.`

  return (
    <div className="stack">
      <div className="page-title">
        <h1>Dashboard</h1>
        {latest && (
          <p className="muted">
            Latest plan: <Link to={`/plans/${latest.id}`}>#{latest.id}</Link> <StatusBadge status={latest.status} />{' '}
            horizon {fmtDateTime(latest.horizon_start)} to {fmtDateTime(latest.horizon_end)}
          </p>
        )}
      </div>

      <section className="welcome" aria-label="Welcome">
        <div>
          <h2>Welcome back{firstName ? `, ${firstName}` : ''}</h2>
          <p>{summary}</p>
        </div>
        <div className="welcome-actions">
          {canRunPlans(user) && (
            <Link className="btn btn-accent" to="/plans">
              Run a new plan
            </Link>
          )}
          <Link className="btn btn-light" to="/requests">
            Review requests
          </Link>
          <Link className="btn btn-light" to="/calendar">
            Open calendar
          </Link>
        </div>
      </section>

      {!metrics ? (
        <Empty title="No finished plan yet">
          Create and submit some requests, then <Link to="/plans">run a plan</Link>. The comparison with independent
          planning appears here.
        </Empty>
      ) : (
        <>
          <section className="kpis" aria-label="Key figures of the latest plan">
            <KpiCard
              label="Closures"
              accent="blue"
              value={String(metrics.integrated.closures)}
              note={closuresNote?.text}
              tone={closuresNote?.tone}
            />
            <KpiCard
              label="Block hours"
              accent="amber"
              value={fmtHours(metrics.integrated.block_hours)}
              note={hoursNote?.text}
              tone={hoursNote?.tone}
            />
            <KpiCard
              label="Trains affected"
              accent="purple"
              value={String(metrics.integrated.trains_affected)}
              note={trainsNote?.text}
              tone={trainsNote?.tone}
            />
            <KpiCard
              label="Improvement vs independent"
              accent="green"
              value={average === null ? '-' : `${average}%`}
              note="average reduction of the three measures"
              tone={average !== null && average > 0 ? 'good' : 'neutral'}
            />
          </section>

          <section className="card">
            <h2>Independent planning vs integrated plan</h2>
            <CompareChart baseline={metrics.baseline} integrated={metrics.integrated} />
          </section>
        </>
      )}

      <section className="card">
        <h2>Requests by status</h2>
        {total === 0 ? (
          <Empty title="No requests yet">
            Create requests on the <Link to="/requests">Requests</Link> page.
          </Empty>
        ) : (
          <div className="status-grid">
            <div className="status-tiles">
              {statusData.map(({ status, count }) => (
                <Link key={status} to={`/requests?status=${status}`} className="status-tile">
                  <span className="status-count">{count}</span>
                  <StatusBadge status={status} />
                </Link>
              ))}
            </div>
            <div className="chart" role="img" aria-label="Requests by status">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={statusData} layout="vertical" margin={{ top: 4, right: 36, left: 8, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 14 }} />
                  <YAxis type="category" dataKey="status" width={92} tick={{ fontSize: 15 }} />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                    {statusData.map((row) => (
                      <Cell key={row.status} fill={STATUS_COLORS[row.status]} />
                    ))}
                    <LabelList dataKey="count" position="right" style={{ fontSize: 15, fontWeight: 600 }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
