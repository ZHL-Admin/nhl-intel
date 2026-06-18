/**
 * Skills radar (Part B5): a variable-length percentile-within-position radar, SVG only.
 *
 * Takes any-length spoke list (absent spokes are simply not passed — never zero, never greyed).
 * Each axis plots the spoke's percentile (0-100) as radius. Honesty tags (skill/usage/style/proxy)
 * are colour-coded with a legend; noisy spokes (sd present) get a faint radial uncertainty whisker.
 * The baseline caption states the percentile basis. Reused for the goalie radar.
 */
import { useState } from 'react'
import { RadarSpoke } from '../../api/types'
import './SkillRadar.css'

const TAG_COLOR: Record<string, string> = {
  skill: '#3b82f6', usage: '#a855f7', style: '#f59e0b', proxy: '#64748b',
}
const TAG_LABEL: Record<string, string> = {
  skill: 'Skill', usage: 'Usage', style: 'Style', proxy: 'Proxy',
}

interface Props {
  spokes: RadarSpoke[]
  baseline?: string | null
  size?: number
}

export default function SkillRadar({ spokes, baseline, size = 420 }: Props) {
  const [hover, setHover] = useState<number | null>(null)
  const usable = spokes.filter(s => s.percentile != null)
  const n = usable.length
  if (n < 3) return <div className="skill-radar__empty">Not enough data for a radar.</div>

  const cx = size / 2, cy = size / 2
  const R = size / 2 - 64                      // leave room for labels
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2
  const pt = (i: number, r: number) => [cx + Math.cos(angle(i)) * r, cy + Math.sin(angle(i)) * r]
  const ringPcts = [25, 50, 75, 100]
  // The spoke labels sit beyond the rings and extend outward by their text width, so they overhang
  // the size×size box (worst case the long left/right labels). Pad the viewBox horizontally (and a
  // little vertically) so the labels live INSIDE it — the SVG then scales to fit its container with
  // nothing spilling past the bounds.
  const PAD_X = Math.round(size * 0.24)         // room for the longest left/right spoke labels
  const PAD_Y = Math.round(size * 0.05)

  const poly = usable.map((s, i) => pt(i, (s.percentile! / 100) * R).join(',')).join(' ')

  const tags = Array.from(new Set(usable.map(s => s.tag)))

  return (
    <div className="skill-radar">
      <svg viewBox={`${-PAD_X} ${-PAD_Y} ${size + 2 * PAD_X} ${size + 2 * PAD_Y}`}
           className="skill-radar__svg" role="img">
        {/* rings */}
        {ringPcts.map(p => (
          <circle key={p} cx={cx} cy={cy} r={(p / 100) * R} className="skill-radar__ring" />
        ))}
        {ringPcts.map(p => (
          <text key={`l${p}`} x={cx + 3} y={cy - (p / 100) * R - 2} className="skill-radar__ring-label">{p}</text>
        ))}
        {/* axes */}
        {usable.map((_s, i) => {
          const [x, y] = pt(i, R)
          return <line key={`ax${i}`} x1={cx} y1={cy} x2={x} y2={y} className="skill-radar__axis" />
        })}
        {/* uncertainty whisker for noisy (sd) spokes */}
        {usable.map((s, i) => {
          if (s.sd == null) return null
          const r = (s.percentile! / 100) * R
          const [x1, y1] = pt(i, Math.max(0, r - 22))
          const [x2, y2] = pt(i, Math.min(R, r + 22))
          return <line key={`sd${i}`} x1={x1} y1={y1} x2={x2} y2={y2} className="skill-radar__whisker" />
        })}
        {/* polygon */}
        <polygon points={poly} className="skill-radar__poly" />
        {/* points + labels. The outer ring carries ONLY the spoke label; the percentile number is
            placed INBOARD next to its data dot (with a halo for legibility) so the two never collide. */}
        {usable.map((s, i) => {
          const dataR = (s.percentile! / 100) * R
          const [px, py] = pt(i, dataR)
          const [lx, ly] = pt(i, R + 18)
          // number sits just inboard of the dot, clamped so it neither leaves the rings nor stacks on centre
          const [nx, ny] = pt(i, Math.min(R - 6, Math.max(16, dataR - 15)))
          const anchor = Math.abs(Math.cos(angle(i))) < 0.3 ? 'middle'
            : Math.cos(angle(i)) > 0 ? 'start' : 'end'
          return (
            <g key={`pt${i}`} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <circle cx={px} cy={py} r={hover === i ? 5 : 3.5}
                      style={{ fill: TAG_COLOR[s.tag] ?? '#3b82f6' }} className="skill-radar__dot" />
              <text x={lx} y={ly} textAnchor={anchor as any} className="skill-radar__spoke-label"
                    style={{ fill: hover === i ? TAG_COLOR[s.tag] : undefined }}>
                {s.label}
              </text>
              <text x={nx} y={ny + 3} textAnchor="middle" className="skill-radar__spoke-pctl">
                {Math.round(s.percentile!)}
              </text>
            </g>
          )
        })}
      </svg>

      {hover != null && (
        <div className="skill-radar__tip">
          <strong>{usable[hover].label}</strong> · {TAG_LABEL[usable[hover].tag]}<br />
          {Math.round(usable[hover].percentile!)}th percentile
          {usable[hover].sd != null && <span> · noisy estimate (±{usable[hover].sd!.toFixed(2)})</span>}
        </div>
      )}

      <div className="skill-radar__legend">
        {tags.map(t => (
          <span key={t} className="skill-radar__legend-item">
            <span className="skill-radar__legend-dot" style={{ background: TAG_COLOR[t] }} />
            {TAG_LABEL[t] ?? t}
          </span>
        ))}
      </div>
      {baseline && <div className="skill-radar__baseline">{baseline}</div>}
    </div>
  )
}
