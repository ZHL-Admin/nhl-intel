/**
 * SplitBar (§01) — the win-probability readout used across every scored/upcoming row and the
 * featured tile: a 56x4 two-segment team-color bar (away left, home right) plus a "TOR 71%"
 * tabular label naming the favored team. `homeWp` is the home win probability; it accepts a
 * 0-1 fraction (both the pregame preview and the live model feed it) and tolerates 0-100.
 */
import { getTeamColor } from '../../utils/teams'
import './GameRow.css'

export default function SplitBar({ homeWp, homeAbbrev, awayAbbrev }: {
  homeWp: number
  homeAbbrev: string
  awayAbbrev: string
}) {
  const frac = homeWp > 1 ? homeWp / 100 : homeWp
  const homePct = Math.round(Math.min(1, Math.max(0, frac)) * 100)
  const awayPct = 100 - homePct
  const homeFav = homePct >= awayPct
  const favAbbrev = homeFav ? homeAbbrev : awayAbbrev
  const favPct = Math.max(homePct, awayPct)

  return (
    <span className="split-prob">
      <span className="split-bar" aria-hidden="true">
        <span className="split-bar__seg" style={{ width: `${awayPct}%`, background: getTeamColor(awayAbbrev) }} />
        <span className="split-bar__seg" style={{ width: `${homePct}%`, background: getTeamColor(homeAbbrev) }} />
      </span>
      <span className="split-prob__label num">{favAbbrev} {favPct}%</span>
    </span>
  )
}
