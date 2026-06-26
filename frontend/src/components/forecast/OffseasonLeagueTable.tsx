import { Info } from 'lucide-react'
import { Tooltip } from '../common'
import { RosterForecastRow } from '../../api/types'
import { getTeamLogoUrl, getTeamName } from '../../utils/teams'
import { fmtRating, fmtRank, tierForRank, isQuiet } from '../../utils/forecastFormat'

/** Projected rank change vs last season's finish: ▲ = climbing, ▼ = falling, — = no move. */
function RankMove({ delta }: { delta?: number | null }) {
  if (delta == null || delta === 0) return <span className="oltable__move--flat">—</span>
  return delta > 0
    ? <span className="oltable__move--up">▲{delta}</span>
    : <span className="oltable__move--down">▼{Math.abs(delta)}</span>
}

/** League view: full projected standings, all 32 teams. Rows click through to the team view. */
export default function OffseasonLeagueTable({ rows, onSelect }: {
  rows: RosterForecastRow[]; onSelect: (teamId: number) => void
}) {
  const ordered = [...rows].sort((a, b) => (a.projected_rank ?? 99) - (b.projected_rank ?? 99))
  return (
    <div className="oltable">
      <table>
        <thead>
          <tr>
            <th className="oltable__rank">#</th>
            <th>Team</th>
            <th className="oltable__num">
              <span className="oltable__th-tip">
                Projected rating
                <Tooltip content="Projected next-season strength in goals per game versus a league-average team: +0.50 means expected to outscore an average opponent by half a goal a night. 0 = average, negative = below.">
                  <Info size={12} className="oltable__th-info" />
                </Tooltip>
              </span>
            </th>
            <th className="oltable__center oltable__move">
              <span className="oltable__th-tip">
                Move
                <Tooltip content="Change in league rank by rating: where the team ranks on projected next-season rating vs where it ranked last season. ▲ = projected to climb, ▼ = to fall.">
                  <Info size={12} className="oltable__th-info" />
                </Tooltip>
              </span>
            </th>
            <th className="oltable__num">vs last season</th>
            <th className="oltable__center oltable__moves">Moves</th>
            <th className="oltable__center oltable__tier">Tier</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((r) => {
            const tier = tierForRank(r.projected_rank)
            const flat = Math.abs(r.delta) < 0.005
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
                <td className="oltable__num mono oltable__rating">{fmtRating(r.projected_rating)}</td>
                <td className="oltable__center oltable__move mono"><RankMove delta={r.projected_rank_delta} /></td>
                <td className={`oltable__num mono ${flat ? '' : r.delta > 0 ? 'is-up' : 'is-down'}`}>
                  {flat ? '±.00' : fmtRating(r.delta)}
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
