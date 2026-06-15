/**
 * League style map (Phase 3.2): SVG scatter of the 32 team logos at their PCA coordinates,
 * with quadrant axis annotations from the API. Clicking a logo navigates to the team.
 * No new charting deps — a hand-drawn SVG inside ChartPanel.
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChartPanel } from '../common'
import { getStyleMap } from '../../api/teams'
import { StyleMap } from '../../api/types'
import { getTeamLogoUrl } from '../../utils/teams'
import './StyleMapChart.css'

const W = 720
const H = 480
const PAD = 56

export default function StyleMapChart({ height }: { height?: number }) {
  const navigate = useNavigate()
  const [data, setData] = useState<StyleMap | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getStyleMap()
      .then((d) => active && setData(d))
      .catch(() => active && setError('Could not load style map.'))
    return () => { active = false }
  }, [])

  if (error) return <ChartPanel title="League style map"><p className="stylemap__error">{error}</p></ChartPanel>
  if (!data) return <ChartPanel title="League style map"><div className="stylemap__loading" /></ChartPanel>

  const xs = data.teams.map((t) => t.x)
  const ys = data.teams.map((t) => t.y)
  const xMin = Math.min(...xs), xMax = Math.max(...xs)
  const yMin = Math.min(...ys), yMax = Math.max(...ys)
  const sx = (x: number) => PAD + ((x - xMin) / (xMax - xMin || 1)) * (W - 2 * PAD)
  // SVG y grows downward; flip so higher y is up
  const sy = (y: number) => H - PAD - ((y - yMin) / (yMax - yMin || 1)) * (H - 2 * PAD)
  const cx = sx((xMin + xMax) / 2)
  const cy = sy((yMin + yMax) / 2)

  return (
    <ChartPanel title="League style map" subtitle="Teams clustered by playing-style fingerprint (PCA)">
      <div className="stylemap" style={height ? { height } : undefined}>
        <svg viewBox={`0 0 ${W} ${H}`} className="stylemap__svg" preserveAspectRatio="xMidYMid meet">
          {/* axes */}
          <line x1={PAD / 2} y1={cy} x2={W - PAD / 2} y2={cy} className="stylemap__axis" />
          <line x1={cx} y1={PAD / 2} x2={cx} y2={H - PAD / 2} className="stylemap__axis" />
          {/* axis annotations from the API */}
          <text x={W - PAD / 2} y={cy - 6} textAnchor="end" className="stylemap__axis-label">{data.x_pos_desc} ▶</text>
          <text x={PAD / 2} y={cy - 6} textAnchor="start" className="stylemap__axis-label">◀ {data.x_neg_desc}</text>
          <text x={cx + 6} y={PAD / 2} textAnchor="start" className="stylemap__axis-label">▲ {data.y_pos_desc}</text>
          <text x={cx + 6} y={H - PAD / 2 + 4} textAnchor="start" className="stylemap__axis-label">▼ {data.y_neg_desc}</text>
          {/* team logos */}
          {data.teams.map((t) => (
            <image
              key={t.team_id}
              href={t.team_abbrev ? getTeamLogoUrl(t.team_abbrev) : undefined}
              x={sx(t.x) - 14}
              y={sy(t.y) - 14}
              width={28}
              height={28}
              className="stylemap__logo"
              onClick={() => navigate(`/teams/${t.team_id}`)}
            >
              <title>{t.team_abbrev}</title>
            </image>
          ))}
        </svg>
      </div>
    </ChartPanel>
  )
}
