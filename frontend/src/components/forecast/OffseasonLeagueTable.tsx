import { Info } from 'lucide-react'
import { Tooltip } from '../common'
import { RosterForecastRow } from '../../api/types'
import { getTeamLogoUrl, getTeamName } from '../../utils/teams'
import {
  fmtRating, fmtRank, tierForRank, isQuiet,
  fmtPoints, fmtPointsBand, fmtPointsDelta,
} from '../../utils/forecastFormat'

/** Projected rank change vs last season's finish: ▲ = climbing, ▼ = falling, — = no move. */
function RankMove({ delta }: { delta?: number | null }) {
  if (delta == null || delta === 0) return <span className="oltable__move--flat">—</span>
  return delta > 0
    ? <span className="oltable__move--up">▲{delta}</span>
    : <span className="oltable__move--down">▼{Math.abs(delta)}</span>
}

/** League view: full projected standings, all 32 teams, by projected POINTS. Rating is a secondary
 * column (the underlying mechanism). Rows click through to the team view. */
export default function OffseasonLeagueTable({ rows, onSelect }: {
  rows: RosterForecastRow[]; onSelect: (teamId: number) => void
}) {
  // Default sort: projected points (desc); fall back to projected rank when points are unavailable.
  const ordered = [...rows].sort((a, b) => {
    const pa = a.projected_points, pb = b.projected_points
    if (pa != null && pb != null && pa !== pb) return pb - pa
    return (a.projected_rank ?? 99) - (b.projected_rank ?? 99)
  })
  return (
    <div className="oltable">
      <table>
        <thead>
          <tr>
            <th className="oltable__rank">#</th>
            <th>Team</th>
            <th className="oltable__num">
              <span className="oltable__th-tip">
                Projected points
                <Tooltip content="Projected next-season standings points over 82 games — a calibrated transform of the team rating, shown with its 80% band. The headline of the forecast.">
                  <Info size={12} className="oltable__th-info" />
                </Tooltip>
              </span>
            </th>
            <th className="oltable__num">
              <span className="oltable__th-tip">
                Rating
                <Tooltip content="The underlying team rating in goals per game vs a league-average team: +0.50 means expected to outscore an average opponent by half a goal a night. Points are derived from this.">
                  <Info size={12} className="oltable__th-info" />
                </Tooltip>
              </span>
            </th>
            <th className="oltable__center oltable__move">
              <span className="oltable__th-tip">
                Move
                <Tooltip content="Change in league rank: where the team ranks on the projection vs where it ranked last season. ▲ = projected to climb, ▼ = to fall.">
                  <Info size={12} className="oltable__th-info" />
                </Tooltip>
              </span>
            </th>
            <th className="oltable__num">
              <span className="oltable__th-tip">
                Δ pts
                <Tooltip content="Standings-points shift from this offseason's moves alone, vs last season's roster.">
                  <Info size={12} className="oltable__th-info" />
                </Tooltip>
              </span>
            </th>
            <th className="oltable__center oltable__moves">Moves</th>
            <th className="oltable__center oltable__tier">Tier</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((r) => {
            const tier = tierForRank(r.projected_rank)
            const pdFlat = r.points_delta == null ? true : Math.abs(Math.round(r.points_delta)) === 0
            const quiet = isQuiet({ n_moves: r.n_moves, delta: r.delta, negligible: r.negligible })
            return (
              <tr key={r.team_id} onClick={() => onSelect(r.team_id)} tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(r.team_id) } }}>
                <td className="oltable__rank mono">{fmtRank(r.projected_rank)}</td>
                <td>
                  <span className="oltable__team">
                    <img src={getTeamLogoUrl(r.team_abbrev ?? '')} alt="" aria-hidden className="oltable__logo" />
                    <span className="oltable__abbr">{r.team_abbrev}</span>
                    <span className="oltable__name">{getTeamName(r.team_abbrev ?? '')}</span>
                    {quiet && <span className="oltable__quiet">quiet</span>}
                  </span>
                </td>
                <td className="oltable__num mono oltable__points">
                  <span className="oltable__points-val">{fmtPoints(r.projected_points)}</span>
                  <span className="oltable__points-band">{fmtPointsBand(r.points_low, r.points_high)}</span>
                </td>
                <td className="oltable__num mono oltable__rating-sec">{fmtRating(r.projected_rating)}</td>
                <td className="oltable__center oltable__move mono"><RankMove delta={r.projected_rank_delta} /></td>
                <td className={`oltable__num mono ${pdFlat ? '' : (r.points_delta ?? 0) > 0 ? 'is-up' : 'is-down'}`}>
                  {pdFlat ? '±0' : fmtPointsDelta(r.points_delta)}
                </td>
                <td className="oltable__center mono oltable__moves">{r.n_moves}</td>
                <td className="oltable__center oltable__tier">
                  <span className={`oltable__pill oltable__pill--${tier.toLowerCase()}`}>{tier}</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
