import { Link } from 'react-router-dom'
import type { Plan, Schedule } from '../../api/types'
import { Gantt } from '../../components/Gantt'
import { DeptChip, Empty } from '../../components/ui'
import { horizonDays } from '../../lib/time'
import { fmtDate, fmtTime } from '../../lib/time'

const REASON_TEXT: Record<string, string> = {
  OUT_OF_HORIZON: "deadline is outside the plan's dates",
  TOO_LONG: 'longer than the block maximum',
  DEPENDENCY_UNMET: 'waits for a request that could not be placed',
  NO_CAPACITY: 'no room within its dates (crews or block limit)',
}

export function ScheduleTab({ plan, schedule, sections }: { plan: Plan; schedule: Schedule; sections: string[] }) {
  return (
    <div className="stack">
      {schedule.blocks.length === 0 ? (
        <Empty title="Nothing to schedule">This plan has no requests to place.</Empty>
      ) : (
        <div className="card">
          <Gantt
            blocks={schedule.blocks}
            horizonStart={plan.horizon_start}
            days={horizonDays(plan)}
            sections={sections}
            title="Integrated schedule"
            defaultView="auto"
          />
        </div>
      )}

      {schedule.blocks.length > 0 && (
        <div className="card table-card">
          <h2>Closures</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Section</th>
                <th>Day</th>
                <th>Window</th>
                <th>Trains</th>
                <th>Requests</th>
              </tr>
            </thead>
            <tbody>
              {schedule.blocks.map((b, i) => (
                <tr key={`${b.id}-${i}`}>
                  <td>{b.section_code}</td>
                  <td>{fmtDate(b.start)}</td>
                  <td>
                    {fmtTime(b.start)}-{fmtTime(b.end)}
                  </td>
                  <td>{b.trains_affected}</td>
                  <td>
                    {b.members.map((m) => (
                      <span key={m.request_id} className="member">
                        <Link to={`/requests?section=${b.section_code}`}>{m.request}</Link> <DeptChip dept={m.dept} />{' '}
                        <span className="muted">
                          {m.start}-{m.end}
                        </span>
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {schedule.deferred.length > 0 && (
        <div className="card">
          <h2>Not placed ({schedule.deferred.length})</h2>
          <ul className="plain-list">
            {schedule.deferred.map((d) => (
              <li key={d.request_id}>
                <strong>{d.request}</strong> <span className="badge badge-warn">{d.reason}</span>{' '}
                <span className="muted">{REASON_TEXT[d.reason] ?? ''}. It stays submitted for a later plan.</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
