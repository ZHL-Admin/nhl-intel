import { UncertaintyBand } from '../common'
import { RosterForecastRow } from '../../api/types'
import { getTeamLogoUrl, getTeamName } from '../../utils/teams'
import { fmtRating, fmtRank, tierForRank, isQuiet } from '../../utils/forecastFormat'

const RANGE_DOMAIN: [number, number] = [-1.2, 1.4]

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
            <th className="oltable__num">Projected rating</th>
            <th className="oltable__range">Range</th>
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
                <td className="oltable__range">
                  <UncertaintyBand value={r.projected_rating} lo={r.band_low} hi={r.band_high}
                    domainMin={RANGE_DOMAIN[0]} domainMax={RANGE_DOMAIN[1]} />
                </td>
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
