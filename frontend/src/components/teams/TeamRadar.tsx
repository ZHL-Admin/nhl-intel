/**
 * Team performance radar (SPEC Page 3 §2): six percentile axes vs the league, with a league-median
 * (50th-pctile) reference polygon so the eye reads identity at a glance. Driven by the rank fields
 * already on TeamDetail (rank -> percentile). De-defaulted Recharts: subtle polar grid, no clutter,
 * a custom tooltip that shows the actual value alongside the percentile.
 */
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip,
} from 'recharts'
import { TeamDetail } from '../../api/types'
import { ordinal } from '../../utils/format'

const N_TEAMS = 32
/** rank (1 = best) -> percentile (0-100, higher = better). */
function rankPctile(rank?: number | null): number | null {
  if (rank == null) return null
  return Math.round(((N_TEAMS - rank) / (N_TEAMS - 1)) * 100)
}

interface Axis { key: string; label: string; pctile: number | null; value: string }

function buildAxes(t: TeamDetail): Axis[] {
  const xgfShare = t.xgf_per60 + t.xga_per60 > 0 ? t.xgf_per60 / (t.xgf_per60 + t.xga_per60) : null
  const gfP = rankPctile(t.gf_per_gp_rank)
  const gaP = rankPctile(t.ga_per_gp_rank)
  const finishing = gfP != null && gaP != null ? Math.round((gfP + gaP) / 2) : (gfP ?? gaP)
  const gd = (t.total_goals_for - t.total_goals_against) / Math.max(1, t.games_played)
  return [
    { key: 'poss', label: 'Possession', pctile: rankPctile(t.cf_pct_rank), value: `${(t.cf_pct * 100).toFixed(1)}% CF` },
    { key: 'qual', label: 'Chance quality', pctile: rankPctile(t.xgf_pct_rank), value: xgfShare != null ? `${(xgfShare * 100).toFixed(1)}% xGF` : '—' },
    { key: 'gen', label: 'Danger generation', pctile: rankPctile(t.hdcf_per60_rank), value: `${t.hdcf_per60.toFixed(1)} HDCF/60` },
    { key: 'supp', label: 'Danger suppression', pctile: rankPctile(t.hdca_per60_rank), value: `${t.hdca_per60.toFixed(1)} HDCA/60` },
    { key: 'zone', label: 'Zone control', pctile: rankPctile(t.zone_entry_proxy_success_rate_rank), value: t.zone_entry_proxy_success_rate != null ? `${(t.zone_entry_proxy_success_rate * 100).toFixed(1)}% entries` : '—' },
    { key: 'fin', label: 'Finishing', pctile: finishing, value: `${gd >= 0 ? '+' : ''}${gd.toFixed(2)} GD/GP` },
  ]
}

function RadarTip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const a: Axis = payload[0].payload
  return (
    <div className="team-radar__tip">
      <div className="team-radar__tip-label">{a.label}</div>
      <div className="team-radar__tip-pct">{a.pctile == null ? '—' : `${ordinal(a.pctile)} percentile`}</div>
      <div className="team-radar__tip-val">{a.value}</div>
    </div>
  )
}

export default function TeamRadar({ teamDetail, color, height = 300 }: {
  teamDetail: TeamDetail; color: string; height?: number
}) {
  const axes = buildAxes(teamDetail).map((a) => ({ ...a, plot: a.pctile ?? 0, league: 50 }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={axes} margin={{ top: 16, right: 24, bottom: 16, left: 24 }}>
        <PolarGrid stroke="var(--color-border-subtle)" />
        <PolarAngleAxis dataKey="label" tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} />
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
        {/* league-median reference polygon at the 50th percentile */}
        <Radar name="League median" dataKey="league" stroke="var(--color-border-strong)"
          fill="none" strokeDasharray="4 4" isAnimationActive={false} />
        <Radar name="This team" dataKey="plot" stroke={color} fill={color} fillOpacity={0.3}
          isAnimationActive animationDuration={400} />
        <Tooltip content={<RadarTip />} />
      </RadarChart>
    </ResponsiveContainer>
  )
}
