import type { ReactNode } from 'react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, ReferenceLine } from 'recharts'
import { Figure } from './Figure'
import { FIG, tick, axisLine } from './chartTheme'

interface Row { [k: string]: string | number }

/**
 * Bar figure with the standard treatment. `diverging` colors each bar orange
 * (>=0) / blue (<0) — the site's diverging pair — for luck-style values.
 */
export default function BarFigure({
  data, x, y, caption, n, height = 300, color = FIG.orange, diverging = false, unit = '',
}: {
  data: Row[]
  x: string
  y: string
  caption?: ReactNode
  n?: number
  height?: number
  color?: string
  diverging?: boolean
  unit?: string
}) {
  return (
    <Figure n={n} caption={caption}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={FIG.grid} strokeWidth={2} vertical={false} />
          <XAxis dataKey={x} tick={tick} axisLine={axisLine} tickLine={false} interval={0} />
          <YAxis tick={tick} axisLine={axisLine} tickLine={false} width={44}
                 tickFormatter={(v) => `${v}${unit}`} />
          {diverging && <ReferenceLine y={0} stroke={FIG.ink} />}
          <Bar dataKey={y} isAnimationActive={false}>
            {data.map((row, i) => (
              <Cell key={i} fill={diverging ? (Number(row[y]) >= 0 ? FIG.orange : FIG.blue) : color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Figure>
  )
}
