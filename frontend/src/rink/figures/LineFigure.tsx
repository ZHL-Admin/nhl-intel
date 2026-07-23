import type { ReactNode } from 'react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid } from 'recharts'
import { Figure } from './Figure'
import { FIG, tick, axisLine } from './chartTheme'

interface Row { [k: string]: string | number }
interface Series { key: string; color?: string; context?: boolean }

/**
 * Line figure with the standard treatment. Exactly one highlighted series in its
 * category color; any `context: true` series render in gray.
 */
export default function LineFigure({
  data, x, series, caption, n, height = 300,
}: {
  data: Row[]
  x: string
  series: Series[]
  caption?: ReactNode
  n?: number
  height?: number
}) {
  return (
    <Figure n={n} caption={caption}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={FIG.grid} strokeWidth={2} />
          <XAxis dataKey={x} tick={tick} axisLine={axisLine} tickLine={false} />
          <YAxis tick={tick} axisLine={axisLine} tickLine={false} width={44} />
          {series.map((s) => (
            <Line key={s.key} type="monotone" dataKey={s.key} dot={false} strokeWidth={2}
                  stroke={s.context ? FIG.context : (s.color ?? FIG.orange)}
                  isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Figure>
  )
}
