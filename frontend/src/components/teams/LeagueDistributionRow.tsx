/**
 * LeagueDistributionRow (06 v2 §0.1) — the team-context comparison row. For team metrics the
 * benchmark is the other 31 teams, not the team's own history.
 *
 * Anatomy: `130px label | flexible strip | 38px value`, height 27. The strip carries a faint
 * baseline hairline, the other teams as 1.5×8px ticks at their real percentile positions (from
 * the league table — never decorative), and this team as a 7px ink dot. The printed value is the
 * league rank ("26th"), rank-colored per §0.2 (1-6 blue, top-of-red-band red, else ink).
 *
 * Ticks are optional: when the per-metric league table isn't served the row degrades to the
 * baseline + this team's dot + rank (honest — no invented ticks).
 */
import { rankColor } from '../../utils/rank'
import { ordinal } from '../../utils/format'
import './LeagueDistributionRow.css'

export interface DistributionTick {
  /** 0..1 position along the strip (this metric's league percentile for that team). */
  percentile: number
  /** Team name shown on hover. */
  team: string
}

export default function LeagueDistributionRow({
  label,
  percentile,
  rank,
  leagueSize = 32,
  ticks,
}: {
  label: string
  /** This team's 0..1 percentile position for the metric (higher = better). */
  percentile: number | null
  /** This team's league rank for the metric (1 = best). */
  rank: number | null
  leagueSize?: number
  ticks?: DistributionTick[]
}) {
  const dotPct = percentile == null ? null : Math.max(0, Math.min(1, percentile)) * 100
  return (
    <div className="ldr">
      <span className="ldr__label">{label}</span>
      <span className="ldr__strip" role="img" aria-label={rank != null ? `${label}: ${ordinal(rank)} of ${leagueSize}` : label}>
        <span className="ldr__baseline" />
        {ticks?.map((t, i) => (
          <span
            key={i}
            className="ldr__tick"
            style={{ left: `${Math.max(0, Math.min(1, t.percentile)) * 100}%` }}
            title={t.team}
          />
        ))}
        {dotPct != null && <span className="ldr__dot" style={{ left: `${dotPct}%` }} />}
      </span>
      <span className="ldr__value" style={{ color: rank != null ? rankColor(rank, leagueSize) : undefined }}>
        {rank != null ? ordinal(rank) : '—'}
      </span>
    </div>
  )
}
