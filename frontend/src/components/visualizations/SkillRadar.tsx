/**
 * Skills radar (Part B5): a variable-length percentile-within-position radar, SVG only.
 *
 * Takes any-length spoke list (absent spokes are simply not passed — never zero, never greyed).
 * Each axis plots the spoke's percentile (0-100) as radius. Honesty tags (skill/usage/style/proxy)
 * are colour-coded with a legend; noisy spokes (sd present) get a faint radial uncertainty whisker.
 *
 * DEFAULT (full) mode: full spoke labels, per-vertex dots + percentile numbers, the tag legend.
 * COMPACT mode (archetype gallery small-multiples): the polygon is the dominant visual — short
 * spoke labels, arc-group labels outside the ring, a solid translucent fill with a thick outline,
 * and NO per-vertex dots/numbers/legend. The FULL name + exact percentile stay on hover.
 */
import { useState } from 'react'
import { RadarSpoke } from '../../api/types'
import { ordinal } from '../../utils/format'
import './SkillRadar.css'

// Trait groups recolor to the restrained categorical palette (§6 R5): skill→cat-1, usage→cat-4,
// style→cat-2, proxy→cat-6 (stone). Tokens, so they follow the theme.
const TAG_COLOR: Record<string, string> = {
  skill: 'var(--color-data-1)', usage: 'var(--color-data-4)', style: 'var(--color-data-2)', proxy: 'var(--color-data-6)',
}
const TAG_LABEL: Record<string, string> = {
  skill: 'Skill', usage: 'Usage', style: 'Style', proxy: 'Proxy',
}

interface Props {
  spokes: RadarSpoke[]
  baseline?: string | null
  size?: number
  /** Compact small-multiple rendering (gallery cards): short labels, arc groups, no dots/legend. */
  compact?: boolean
  /** spoke key -> short label (compact mode). */
  shortLabels?: Record<string, string>
  /** Arc-group labels by the spoke (ring order) each group starts at. Rendered in compact and full. */
  arcGroups?: { label: string; startKey: string }[]
  /** Emphasize the 50th-percentile ring as the league-median reference (full mode). */
  medianRing?: boolean
  /** Dim non-skill spokes (usage/style/proxy) so the measured-skill signal reads as primary. */
  dimNonSkill?: boolean
  /** Shape-only mode (Player Overview): guide rings + dashed median ring, polygon, honesty-colored
   *  nodes, FOUR arc-group labels only (no per-spoke labels). Names/values live in hover tooltips. */
  shapeOnly?: boolean
  /** Suppress the internal legend (the consumer renders it elsewhere, e.g. a title row). */
  hideLegend?: boolean
}

// Honesty legend in fixed order (skill / usage / style) for the shape-only radar.
const SHAPE_LEGEND = ['skill', 'usage', 'style'] as const

export default function SkillRadar({ spokes, baseline, size = 420, compact = false, shortLabels, arcGroups, medianRing, dimNonSkill, shapeOnly, hideLegend }: Props) {
  const [hover, setHover] = useState<number | null>(null)
  const usable = spokes.filter(s => s.percentile != null)
  const n = usable.length
  if (n < 3) return <div className="skill-radar__empty">Not enough data for a radar.</div>

  // ---- Shape-only render (Player Overview hero): conveys shape, not per-spoke labels ----
  if (shapeOnly) {
    const CX = 200, CY = 130, R = 110
    const ang = (i: number) => ((-90 + i * (360 / n)) * Math.PI) / 180
    const at = (i: number, r: number): [number, number] => [CX + Math.cos(ang(i)) * r, CY + Math.sin(ang(i)) * r]
    const poly = usable.map((s, i) => at(i, R * (s.percentile! / 100)).join(',')).join(' ')
    const arcs = (arcGroups ?? [])
      .map(g => ({ label: g.label, i: usable.findIndex(s => s.key === g.startKey) }))
      .filter(g => g.i >= 0).sort((a, b) => a.i - b.i)
      .map((g, gi, all) => {
        const end = (gi + 1 < all.length ? all[gi + 1].i : n) - 1
        const mid = (g.i + end) / 2
        const [x, y] = at(mid, R + 8)
        const c = Math.cos(ang(mid))
        const anchor = Math.abs(c) < 0.3 ? 'middle' : c > 0 ? 'start' : 'end'
        return { label: g.label, x, y: y + (Math.sin(ang(mid)) < -0.3 ? -2 : Math.sin(ang(mid)) > 0.3 ? 8 : 4), anchor }
      })
    return (
      <div className="skill-radar skill-radar--shape">
        <svg viewBox="0 0 400 258" width="100%" className="skill-radar__svg" role="img">
          {/* §6 R5: two guide rings only (50th, 90th of R=110); no dashed median ring */}
          {[55, 99].map(r => (
            <circle key={r} cx={CX} cy={CY} r={r} className="skill-radar__ring--guide" />
          ))}
          <polygon points={poly} className="skill-radar__poly--shape" />
          {arcs.map(a => (
            <text key={a.label} x={a.x} y={a.y} textAnchor={a.anchor as any} className="skill-radar__arc">{a.label.toLowerCase()}</text>
          ))}
          {usable.map((s, i) => {
            const [px, py] = at(i, R * (s.percentile! / 100))
            return (
              <g key={`n${i}`} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                <circle cx={px} cy={py} r={hover === i ? 4.2 : 2.8} style={{ fill: TAG_COLOR[s.tag] ?? TAG_COLOR.skill }} className="skill-radar__node" />
              </g>
            )
          })}
        </svg>
        {hover != null && (
          <div className="skill-radar__tip">
            <strong>{usable[hover].label}</strong> · {TAG_LABEL[usable[hover].tag]}<br />
            {ordinal(usable[hover].percentile!)} percentile
          </div>
        )}
        {!hideLegend && (
          <div className="skill-radar__legend">
            {SHAPE_LEGEND.map(t => (
              <span key={t} className="skill-radar__legend-item">
                <span className="skill-radar__legend-dot" style={{ background: TAG_COLOR[t] }} />{TAG_LABEL[t]}
              </span>
            ))}
          </div>
        )}
        {baseline && !hideLegend && <div className="skill-radar__baseline">{baseline}</div>}
      </div>
    )
  }

  const cx = size / 2, cy = size / 2
  const labelMargin = compact ? 24 : 64        // compact short labels need far less room -> bigger polygon
  const R = size / 2 - labelMargin
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2
  const pt = (i: number, r: number) => [cx + Math.cos(angle(i)) * r, cy + Math.sin(angle(i)) * r]
  const ringPcts = [50, 90]   // §6 R5: two rings only (50th, 90th), no inner guide rings
  // pad the viewBox so labels (and compact arc-group labels) live inside it and the SVG scales clean
  const PAD_X = Math.round(size * (compact ? 0.18 : 0.24))
  // full-mode arc-group labels sit outside the ring, so reserve more vertical room when present
  const PAD_Y = Math.round(size * (compact ? 0.16 : (arcGroups ? 0.13 : 0.05)))
  const labelOf = (s: RadarSpoke) => (compact && shortLabels ? (shortLabels[s.key] ?? s.label) : s.label)

  const poly = usable.map((s, i) => pt(i, (s.percentile! / 100) * R).join(',')).join(' ')
  const tags = Array.from(new Set(usable.map(s => s.tag)))

  // arc groups: contiguous runs by ring order, label at the run's angular midpoint (compact + full)
  const arcs = arcGroups
    ? arcGroups
        .map(g => ({ label: g.label, i: usable.findIndex(s => s.key === g.startKey) }))
        .filter(g => g.i >= 0).sort((a, b) => a.i - b.i)
        .map((g, gi, all) => {
          const end = (gi + 1 < all.length ? all[gi + 1].i : n) - 1
          const mid = (g.i + end) / 2
          const [x, y] = pt(mid, R + (compact ? 26 : 40))
          return { label: g.label, x, y }
        })
    : []

  return (
    <div className="skill-radar">
      <svg viewBox={`${-PAD_X} ${-PAD_Y} ${size + 2 * PAD_X} ${size + 2 * PAD_Y}`}
           className="skill-radar__svg" role="img">
        {ringPcts.map(p => (
          <circle key={p} cx={cx} cy={cy} r={(p / 100) * R}
                  className={`skill-radar__ring${medianRing && p === 50 ? ' skill-radar__ring--median' : ''}`} />
        ))}
        {!compact && ringPcts.map(p => (
          <text key={`l${p}`} x={cx + 3} y={cy - (p / 100) * R - 2} className="skill-radar__ring-label">{p}</text>
        ))}
        {usable.map((_s, i) => {
          const [x, y] = pt(i, R)
          return <line key={`ax${i}`} x1={cx} y1={cy} x2={x} y2={y} className="skill-radar__axis" />
        })}
        {!compact && usable.map((s, i) => {
          if (s.sd == null) return null
          const r = (s.percentile! / 100) * R
          const [x1, y1] = pt(i, Math.max(0, r - 22))
          const [x2, y2] = pt(i, Math.min(R, r + 22))
          return <line key={`sd${i}`} x1={x1} y1={y1} x2={x2} y2={y2} className="skill-radar__whisker" />
        })}

        {/* arc-group labels (compact) */}
        {arcs.map(a => (
          <text key={a.label} x={a.x} y={a.y} textAnchor="middle" className="skill-radar__arc">{a.label}</text>
        ))}

        <polygon points={poly} className={`skill-radar__poly${compact ? ' skill-radar__poly--solid' : ''}`} />

        {usable.map((s, i) => {
          const dataR = (s.percentile! / 100) * R
          const [px, py] = pt(i, dataR)
          const [lx, ly] = pt(i, R + (compact ? 11 : 18))
          const anchor = Math.abs(Math.cos(angle(i))) < 0.3 ? 'middle'
            : Math.cos(angle(i)) > 0 ? 'start' : 'end'
          return (
            <g key={`pt${i}`} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
               style={dimNonSkill && s.tag !== 'skill' && hover !== i ? { opacity: 0.42 } : undefined}>
              {/* hover hit area (invisible in compact, where there is no visible dot) */}
              <circle cx={px} cy={py} r={compact ? 9 : (hover === i ? 5 : 3.5)}
                      style={{ fill: compact ? 'transparent' : (TAG_COLOR[s.tag] ?? TAG_COLOR.skill) }}
                      className={compact ? 'skill-radar__hit' : 'skill-radar__dot'} />
              {compact && hover === i && (
                <circle cx={px} cy={py} r={3.5} style={{ fill: TAG_COLOR[s.tag] ?? TAG_COLOR.skill }} className="skill-radar__dot" />
              )}
              <text x={lx} y={ly} textAnchor={anchor as any}
                    className={`skill-radar__spoke-label${compact ? ' skill-radar__spoke-label--compact' : ''}`}
                    style={{ fill: hover === i ? TAG_COLOR[s.tag] : undefined }}>
                {labelOf(s)}
              </text>
            </g>
          )
        })}
      </svg>

      {hover != null && (
        <div className="skill-radar__tip">
          <strong>{usable[hover].label}</strong> · {TAG_LABEL[usable[hover].tag]}<br />
          {ordinal(usable[hover].percentile!)} percentile
          {usable[hover].sd != null && <span> · noisy estimate (±{usable[hover].sd!.toFixed(2)})</span>}
        </div>
      )}

      {!compact && !hideLegend && (
        <div className="skill-radar__legend">
          {tags.map(t => (
            <span key={t} className="skill-radar__legend-item">
              <span className="skill-radar__legend-dot" style={{ background: TAG_COLOR[t] }} />
              {TAG_LABEL[t] ?? t}
            </span>
          ))}
        </div>
      )}
      {baseline && !hideLegend && <div className="skill-radar__baseline">{baseline}</div>}
    </div>
  )
}
