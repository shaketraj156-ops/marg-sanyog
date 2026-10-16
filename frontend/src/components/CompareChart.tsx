import { Bar, BarChart, CartesianGrid, Legend, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { PlanMetrics } from '../api/types'

export const INDEPENDENT_COLOR = '#8794a6'
export const INTEGRATED_COLOR = '#124b8f'

/** Independent planning against the integrated plan, one pair of bars per measure. */
export function CompareChart({ baseline, integrated }: { baseline: PlanMetrics; integrated: PlanMetrics }) {
  const data = [
    { name: 'Closures', Independent: baseline.closures, Integrated: integrated.closures },
    { name: 'Block hours', Independent: baseline.block_hours, Integrated: integrated.block_hours },
    { name: 'Trains affected', Independent: baseline.trains_affected, Integrated: integrated.trains_affected },
  ]
  return (
    <div className="chart" role="img" aria-label="Independent planning against the integrated plan">
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 24, right: 24, left: 0, bottom: 8 }} barGap={6}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 16 }} />
          <YAxis tick={{ fontSize: 14 }} allowDecimals={false} />
          <Tooltip contentStyle={{ fontSize: 15 }} />
          <Legend wrapperStyle={{ fontSize: 16 }} />
          <Bar dataKey="Independent" fill={INDEPENDENT_COLOR} radius={[4, 4, 0, 0]} isAnimationActive={false}>
            <LabelList dataKey="Independent" position="top" style={{ fontSize: 15, fontWeight: 600 }} />
          </Bar>
          <Bar dataKey="Integrated" fill={INTEGRATED_COLOR} radius={[4, 4, 0, 0]} isAnimationActive={false}>
            <LabelList dataKey="Integrated" position="top" style={{ fontSize: 15, fontWeight: 600 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
