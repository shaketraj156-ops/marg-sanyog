import { useState } from 'react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { CalendarBlock } from '../api/types'
import { deptColor } from '../lib/gantt'
import { DeptChip, Empty, ErrorMessage, Field, Loading } from '../components/ui'
import { useAsync } from '../hooks/useAsync'
import { addDays, fmtDate, fmtTime, mondayOf, nextMonday, plural } from '../lib/time'

async function loadCalendar() {
  const [blocks, sections] = await Promise.all([api.blocks(), api.sections()])
  return { blocks: blocks.blocks, sections: sections.map((s) => s.code) }
}

export function CalendarPage() {
  const { data, error, loading, reload } = useAsync(loadCalendar, [])
  const [weekStart, setWeekStart] = useState<string | null>(null)
  const [section, setSection] = useState('')

  if (loading && !data) return <Loading label="Loading the calendar" />
  if (error && !data) return <ErrorMessage error={error} onRetry={reload} />
  if (!data) return null

  const first = data.blocks[0]?.start.slice(0, 10)
  const monday = weekStart ?? (first ? mondayOf(first) : nextMonday())
  const days = Array.from({ length: 7 }, (_, i) => addDays(monday, i))
  const isWeekend = (day: string) => [0, 6].includes(new Date(`${day}T00:00:00Z`).getUTCDay())
  const departments = [...new Set(data.blocks.flatMap((b) => b.members.map((m) => m.dept)))].sort()
  const rows = (section ? data.sections.filter((s) => s === section) : data.sections).sort()
  const inCell = (code: string, day: string): CalendarBlock[] =>
    data.blocks.filter((b) => b.section_code === code && b.start.slice(0, 10) === day)

  return (
    <div className="stack">
      <div className="page-title">
        <h1>Published calendar</h1>
        <button type="button" className="btn" onClick={reload}>
          Refresh
        </button>
      </div>
      <p className="page-sub">
        Closures that were approved and published, by section and day. Times are Asia/Kolkata.
      </p>

      <div className="card filters">
        <div className="button-row">
          <button type="button" className="btn" onClick={() => setWeekStart(addDays(monday, -7))}>
            ← Previous week
          </button>
          <button type="button" className="btn" onClick={() => setWeekStart(first ? mondayOf(first) : nextMonday())}>
            First published week
          </button>
          <button type="button" className="btn" onClick={() => setWeekStart(addDays(monday, 7))}>
            Next week →
          </button>
          <strong className="week-label">
            {fmtDate(days[0])} to {fmtDate(days[6])}
          </strong>
        </div>
        <Field label="Section">
          <select value={section} onChange={(e) => setSection(e.target.value)}>
            <option value="">All sections</option>
            {data.sections.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>
      </div>

      {departments.length > 0 && (
        <div className="legend" aria-label="Departments">
          <span className="muted">Departments:</span>
          {departments.map((dept) => (
            <DeptChip key={dept} dept={dept} />
          ))}
        </div>
      )}

      {data.blocks.length === 0 ? (
        <Empty title="Nothing is published yet">
          Run a plan, approve it and publish it on the <Link to="/plans">Plans</Link> page.
        </Empty>
      ) : (
        <div className="card table-card">
          <table className="table calendar">
            <thead>
              <tr>
                <th>Section</th>
                {days.map((day) => (
                  <th key={day} className={isWeekend(day) ? 'weekend' : undefined}>
                    {fmtDate(day)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((code) => (
                <tr key={code}>
                  <th scope="row">{code}</th>
                  {days.map((day) => {
                    const blocks = inCell(code, day)
                    return (
                      <td
                        key={day}
                        className={`${blocks.length ? 'cell-busy' : 'cell-free'}${isWeekend(day) ? ' weekend' : ''}`}
                      >
                        {blocks.length === 0 && <span className="muted">-</span>}
                        {blocks.map((b) => (
                          <div
                            className="cal-block"
                            key={b.id}
                            style={{ '--dept': deptColor(b.members[0]?.dept ?? '') } as CSSProperties}
                          >
                            <strong>
                              {fmtTime(b.start)}-{fmtTime(b.end)}
                            </strong>
                            <span className="muted">{plural(b.trains_affected, 'train')}</span>
                            <div>
                              {[...new Set(b.members.map((m) => m.dept))].map((dept) => (
                                <DeptChip key={dept} dept={dept} />
                              ))}
                            </div>
                            <Link to={`/plans/${b.plan_id}`} className="muted">
                              plan #{b.plan_id}
                            </Link>
                          </div>
                        ))}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
