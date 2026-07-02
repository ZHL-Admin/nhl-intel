import { RosterForecastRow } from '../../api/types'
import { getTeamLogoUrl } from '../../utils/teams'
import { fmtRating, fmtPoints, isQuiet } from '../../utils/forecastFormat'

interface LeagueRailProps {
  rows: RosterForecastRow[]
  selectedId: number | null
  onSelect: (teamId: number) => void
  onSeeAll: () => void
}

/** Sticky, height-bounded standings rail (left column of the team grid). Internally scrolls; never
 * drives page height. Replaces the old full-height vertical-sparkline rail. */
export default function LeagueRail({ rows, selectedId, onSelect, onSeeAll }: LeagueRailProps) {
  const ordered = [...rows].sort((a, b) => (a.projected_rank ?? 99) - (b.projected_rank ?? 99))
  return (
    <div className="lrail">
      <div className="lrail__head">
        <span className="lrail__head-title">Projected order</span>
        <button className="lrail__seeall" onClick={onSeeAll}>Full table →</button>
      </div>
      <div className="lrail__card" role="listbox" aria-label="Projected standings">
        {ordered.map((r) => {
          const quiet = isQuiet({ n_moves: r.n_moves, delta: r.delta, negligible: r.negligible })
          // headline points + the points move-impact chip (fall back to rating if a stale row omits points)
          const usePoints = r.points_delta != null
          const flat = usePoints ? Math.abs(Math.round(r.points_delta!)) === 0 : Math.abs(r.delta) < 0.005
          const dir = (usePoints ? r.points_delta! : r.delta) > 0 ? '▲' : '▼'
          const dmag = usePoints ? Math.abs(Math.round(r.points_delta!)).toString() : Math.abs(r.delta).toFixed(2)
          return (
            <button
              key={r.team_id}
              role="option"
              aria-selected={selectedId === r.team_id}
              className={`lrail__row${selectedId === r.team_id ? ' lrail__row--on' : ''}`}
              onClick={() => onSelect(r.team_id)}
            >
              <span className="lrail__rank mono">{r.projected_rank}</span>
              <img className="lrail__logo" src={getTeamLogoUrl(r.team_abbrev ?? '')} alt="" aria-hidden />
              <span className="lrail__abbr">
                {r.team_abbrev}
                {quiet && <span className="lrail__quiet">quiet</span>}
              </span>
              <span className="lrail__rate">
                <span className="lrail__rating mono">
                  {r.projected_points != null ? fmtPoints(r.projected_points) : fmtRating(r.projected_rating)}
                </span>
                <span className={`lrail__delta mono ${flat ? 'is-flat' : (usePoints ? r.points_delta! : r.delta) > 0 ? 'is-up' : 'is-down'}`}>
                  {flat ? (usePoints ? '±0' : '±.00') : `${dir}${dmag}`}
                </span>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
