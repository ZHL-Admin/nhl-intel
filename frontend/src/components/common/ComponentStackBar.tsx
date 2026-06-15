/**
 * Diverging stacked bar of signed components on a shared scale (Phase 3.1).
 *
 * Each component contributes a coloured segment; positive segments stack rightward from a
 * centre zero line, negative segments stack leftward. A tick marks the net total, with an
 * optional uncertainty whisker (+/- se). Built generic so Phase 4 reuses it for player
 * composite stacks. The `domain` is passed in so every row in a table shares one scale.
 */
import './ComponentStackBar.css'

export interface StackSegment {
  key: string
  label: string
  value: number
  color: string
}

interface ComponentStackBarProps {
  segments: StackSegment[]
  total: number
  /** Shared [min, max] scale across rows; typically symmetric around 0. */
  domain: [number, number]
  se?: number | null
  height?: number
  formatValue?: (v: number) => string
}

const fmtDefault = (v: number) => (v >= 0 ? '+' : '') + v.toFixed(2)

export default function ComponentStackBar({
  segments,
  total,
  domain,
  se,
  height = 22,
  formatValue = fmtDefault,
}: ComponentStackBarProps) {
  const [min, max] = domain
  const span = max - min || 1
  const pct = (v: number) => ((v - min) / span) * 100
  const zero = pct(0)

  // stack positives rightward and negatives leftward from zero
  const bars: { left: number; width: number; seg: StackSegment }[] = []
  let posCursor = 0
  let negCursor = 0
  for (const seg of segments) {
    if (seg.value >= 0) {
      const left = pct(posCursor)
      const right = pct(posCursor + seg.value)
      bars.push({ left, width: right - left, seg })
      posCursor += seg.value
    } else {
      const right = pct(negCursor)
      const left = pct(negCursor + seg.value)
      bars.push({ left, width: right - left, seg })
      negCursor += seg.value
    }
  }

  const totalX = pct(total)
  const seLeft = se ? pct(total - se) : null
  const seRight = se ? pct(total + se) : null

  return (
    <div className="component-stack-bar" style={{ height }}>
      <div className="component-stack-bar__zero" style={{ left: `${zero}%` }} />
      {se != null && seLeft != null && seRight != null && (
        <div
          className="component-stack-bar__whisker"
          style={{ left: `${seLeft}%`, width: `${seRight - seLeft}%` }}
        />
      )}
      {bars.map(({ left, width, seg }) => (
        <div
          key={seg.key}
          className="component-stack-bar__seg"
          style={{ left: `${left}%`, width: `${Math.max(width, 0)}%`, background: seg.color }}
          title={`${seg.label}: ${formatValue(seg.value)}`}
        />
      ))}
      <div
        className="component-stack-bar__total"
        style={{ left: `${totalX}%` }}
        title={`Total: ${formatValue(total)}${se != null ? ` ± ${se.toFixed(2)}` : ''}`}
      />
    </div>
  )
}
