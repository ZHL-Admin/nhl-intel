import type { ReactNode } from 'react'
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, ReferenceLine, ZAxis } from 'recharts'
import { Figure } from './Figure'
import { FIG, tick, axisLine } from './chartTheme'

interface Point { x: number; y: number }

/**
 * Scatter figure with the standard treatment. Optional `trend` draws a straight
 * segment (e.g. a near-flat regression line) in ink.
 */
export default function ScatterFigure({
  data, caption, n, height = 320, color = FIG.orange, xLabel, yLabel, trend,
}: {
  data: Point[]
  caption?: ReactNode
  n?: number
  height?: number
  color?: string
  xLabel?: string
  yLabel?: string
  trend?: { from: [number, number]; to: [number, number] }
}) {
  return (
    <Figure n={n} caption={caption}>
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 8, right: 12, bottom: 20, left: 4 }}>
          <CartesianGrid stroke={FIG.grid} strokeWidth={2} />
          <XAxis type="number" dataKey="x" tick={tick} axisLine={axisLine} tickLine={false}
                 label={xLabel ? { value: xLabel, position: 'bottom', offset: 2, style: { fontFamily: tick.fontFamily, fontSize: 10, fill: FIG.muted } } : undefined} />
          <YAxis type="number" dataKey="y" tick={tick} axisLine={axisLine} tickLine={false} width={44}
                 label={yLabel ? { value: yLabel, angle: -90, position: 'insideLeft', style: { fontFamily: tick.fontFamily, fontSize: 10, fill: FIG.muted } } : undefined} />
          <ZAxis range={[36, 36]} />
          {trend && (
            <ReferenceLine ifOverflow="extendDomain" stroke={FIG.ink} strokeWidth={2}
              segment={[{ x: trend.from[0], y: trend.from[1] }, { x: trend.to[0], y: trend.to[1] }]} />
          )}
          <Scatter data={data} fill={color} fillOpacity={0.85} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </Figure>
  )
}
