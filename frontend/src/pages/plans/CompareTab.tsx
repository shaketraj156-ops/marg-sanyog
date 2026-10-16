import { api } from '../../api'
import type { Plan, PlanMetrics, Schedule } from '../../api/types'
import { CompareChart } from '../../components/CompareChart'
import { Gantt } from '../../components/Gantt'
import { ErrorMessage, Loading } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { fmtHours, horizonDays, percentChange } from '../../lib/time'

const ROWS: { key: keyof PlanMetrics; label: string; hours?: boolean }[] = [
  { key: 'closures', label: 'Closures' },
  { key: 'block_hours', label: 'Block hours', hours: true },
  { key: 'trains_affected', label: 'Trains affected' },
  { key: 'traffic_cost', label: 'Traffic cost (weighted trains)' },
  { key: 'weighted_postponement_days', label: 'Postponement (priority-weighted days)' },
  { key: 'deferred', label: 'Requests not placed' },
]

function describeCost(versions: Record<string, string>): string {
  const cost = versions.cost ?? ''
  if (cost.startsWith('delay_model')) return `predicted delay (${cost.replace('delay_model:', 'delay model ')})`
  return versions.ml_fallback ? `train counts (${versions.ml_fallback})` : 'train counts'
}

export function CompareTab({ plan, schedule, sections }: { plan: Plan; schedule: Schedule; sections: string[] }) {
  const baseline = useAsync(() => api.baseline(plan.id), [plan.id])
  const metrics = plan.metrics
  if (!metrics) return null

  return (
    <div className="stack">
      <div className="card">
        <h2>Independent planning vs integrated plan</h2>
        <p className="muted">
          Independent planning: each department picks its own time (its preferred start, or its usual hour) and
          nobody coordinates. The same scoring function is applied to both plans.
        </p>
        <CompareChart baseline={metrics.baseline} integrated={metrics.integrated} />
      </div>

      <div className="card table-card">
        <table className="table">
          <thead>
            <tr>
              <th>Measure</th>
              <th>Independent</th>
              <th>Integrated</th>
              <th>Change</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map(({ key, label, hours }) => {
              const before = metrics.baseline[key]
              const after = metrics.integrated[key]
              const change = percentChange(before, after)
              const show = (v: number) => (hours ? fmtHours(v) : String(v))
              return (
                <tr key={key}>
                  <td>{label}</td>
                  <td>{show(before)}</td>
                  <td>
                    <strong>{show(after)}</strong>
                  </td>
                  <td className={change === null || change === 0 ? '' : change < 0 ? 'good-text' : 'bad-text'}>
                    {change === null ? (after === 0 ? '-' : 'n/a') : `${change > 0 ? '+' : ''}${change}%`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="muted table-foot">
          Solver: {plan.solver_status}
          {metrics.solver?.gap != null && plan.solver_status !== 'OPTIMAL'
            ? ` (stopped at the time limit; gap ${Math.round(metrics.solver.gap)} objective points)`
            : plan.solver_status === 'OPTIMAL'
              ? ' (proved optimal)'
              : ''}
          {metrics.solver ? `, ${metrics.solver.wall_time_s} s` : ''}.
          {metrics.solver?.note ? ` ${metrics.solver.note}` : ''}
          {plan.model_versions?.cost ? ` Cost: ${describeCost(plan.model_versions)}.` : ''}
        </p>
      </div>

      <div className="card">
        {baseline.loading && !baseline.data ? (
          <Loading label="Loading the independent plan" />
        ) : baseline.error ? (
          <ErrorMessage error={baseline.error} onRetry={baseline.reload} />
        ) : (
          baseline.data && (
            <>
              <Gantt
                blocks={baseline.data.blocks}
                horizonStart={plan.horizon_start}
                days={horizonDays(plan)}
                sections={sections}
                title={`Independent planning (${baseline.data.blocks.length} closures)`}
              />
            </>
          )
        )}
      </div>

      <div className="card">
        <Gantt
          blocks={schedule.blocks}
          horizonStart={plan.horizon_start}
          days={horizonDays(plan)}
          sections={sections}
          title={`Integrated plan (${schedule.blocks.length} closures)`}
        />
      </div>
    </div>
  )
}
