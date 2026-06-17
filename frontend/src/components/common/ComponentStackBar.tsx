/**
 * Diverging stacked bar of signed components on a shared scale (Phase 3.1).
 *
 * Each component contributes a coloured segment; positive segments stack rightward from a
 * centre zero line, negative segments stack leftward. A tick marks the net total, with an
 * optional uncertainty whisker (+/- se). Built generic so Phase 4 reuses it for player
 * composite stacks. The `domain` is passed in so every row in a table shares one scale.
 *
 * Hovering the bar opens a custom breakdown tooltip (portal-rendered so it isn't clipped) — a
 * faster, richer replacement for the native title, and a built-in "what am I looking at" key.
 */
import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
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
  /** Optional faint reference lines at these domain values (a scale for the eye). */
  gridlines?: number[]
  /**
   * 'stacked' (default) draws every component segment; 'total' draws ONE single-tone bar
   * spanning zero→total. The breakdown tooltip is identical in both, so 'total' gives a
   * scannable magnitude bar on a list while the full component split stays on hover.
   */
  variant?: 'stacked' | 'total'
  /** Fill colour for the 'total' variant. */
  totalColor?: string
}

const fmtDefault = (v: number) => (v >= 0 ? '+' : '') + v.toFixed(2)

export default function ComponentStackBar({
  segments,
  total,
  domain,
  se,
  height = 22,
  formatValue = fmtDefault,
  gridlines,
  variant = 'stacked',
  totalColor = 'var(--color-data-1)',
}: ComponentStackBarProps) {
  const [min, max] = domain
  const span = max - min || 1
  const pct = (v: number) => ((v - min) / span) * 100
  const zero = pct(0)

  const barRef = useRef<HTMLDivElement>(null)
  const [tip, setTip] = useState<{ top: number; left: number } | null>(null)
  const showTip = () => {
    const r = barRef.current?.getBoundingClientRect()
    if (r) setTip({ top: r.top - 8, left: r.left + r.width / 2 })
  }

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
    <div
      ref={barRef}
      className="component-stack-bar"
      style={{ height }}
      onMouseEnter={showTip}
      onMouseLeave={() => setTip(null)}
    >
      {gridlines?.filter((v) => v !== 0).map((v) => (
        <div key={`g${v}`} className="component-stack-bar__grid" style={{ left: `${pct(v)}%` }} />
      ))}
      <div className="component-stack-bar__zero" style={{ left: `${zero}%` }} />
      {se != null && seLeft != null && seRight != null && (
        <div
          className="component-stack-bar__whisker"
          style={{ left: `${seLeft}%`, width: `${seRight - seLeft}%` }}
        />
      )}
      {variant === 'total' ? (
        <div
          className="component-stack-bar__seg"
          style={{
            left: `${pct(Math.min(0, total))}%`,
            width: `${Math.max(pct(Math.max(0, total)) - pct(Math.min(0, total)), 0)}%`,
            background: totalColor,
          }}
        />
      ) : (
        bars.map(({ left, width, seg }) => (
          <div
            key={seg.key}
            className="component-stack-bar__seg"
            style={{ left: `${left}%`, width: `${Math.max(width, 0)}%`, background: seg.color }}
          />
        ))
      )}
      <div className="component-stack-bar__total" style={{ left: `${totalX}%` }} />

      {tip && createPortal(
        <div className="csb-tip" style={{ top: tip.top, left: tip.left }}>
          <div className="csb-tip__rows">
            {segments.map((s) => (
              <div key={s.key} className="csb-tip__row">
                <span className="csb-tip__swatch" style={{ background: s.color }} />
                <span className="csb-tip__label">{s.label}</span>
                <span className="csb-tip__val">{formatValue(s.value)}</span>
              </div>
            ))}
          </div>
          <div className="csb-tip__total">
            <span>Total value</span>
            <span className="csb-tip__val">{formatValue(total)}{se != null ? ` ± ${se.toFixed(1)}` : ''}</span>
          </div>
        </div>,
        document.body,
      )}
    </div>
  )
}
