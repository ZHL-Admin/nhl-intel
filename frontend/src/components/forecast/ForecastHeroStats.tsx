import { Tooltip, UncertaintyBand } from '../common'
import { RosterForecastRow } from '../../api/types'
import {
  fmtRating, fmtBand, fmtRank, changeWords,
  fmtPoints, fmtPointsBand, fmtPointsDelta,
} from '../../utils/forecastFormat'

const RATING_DOMAIN: [number, number] = [-0.4, 1.4]
const POINTS_DOMAIN: [number, number] = [65, 125]   // realistic NHL standings-points span

/** Hero cells: projected POINTS lead (with band), then the points move-impact, rank, and moves.
 * Projected rating is demoted to the underlying mechanism beneath the points. */
export default function ForecastHeroStats({ f }: { f: RosterForecastRow }) {
  const hasPoints = f.projected_points != null && f.points_low != null && f.points_high != null
  // sign/flat off the points move-impact when present, else the rating delta (same sign, b > 0)
  const flat = f.points_delta != null ? Math.abs(f.points_delta) < 0.5 : Math.abs(f.delta) < 0.03
  const changeClass = flat ? 'is-flat' : f.delta > 0 ? 'is-up' : 'is-down'
  return (
    <div className="fhero">
      <div className="fhero__cell fhero__cell--wide">
        <Tooltip content="Projected next-season standings points over 82 games — a calibrated transform of the team rating, carried with its band. 0 = none, 164 = ceiling.">
          <span className="fhero__label">{hasPoints ? 'Projected points' : 'Projected rating'}</span>
        </Tooltip>
        {hasPoints ? (
          <>
            <span className="fhero__value fhero__value--xl mono">{fmtPoints(f.projected_points)}</span>
            <UncertaintyBand value={f.projected_points!} lo={f.points_low!} hi={f.points_high!}
              domainMin={POINTS_DOMAIN[0]} domainMax={POINTS_DOMAIN[1]} size="md" />
            <span className="fhero__sub mono">80% range {fmtPointsBand(f.points_low, f.points_high)}</span>
            <span className="fhero__sub fhero__sub--quiet mono">rating {fmtRating(f.projected_rating)} goals/game</span>
          </>
        ) : (
          <>
            <span className="fhero__value fhero__value--xl mono">{fmtRating(f.projected_rating)}</span>
            <UncertaintyBand value={f.projected_rating} lo={f.band_low} hi={f.band_high}
              domainMin={RATING_DOMAIN[0]} domainMax={RATING_DOMAIN[1]} size="md" />
            <span className="fhero__sub mono">80% range {fmtBand(f.band_low, f.band_high, 2)}</span>
          </>
        )}
      </div>

      <div className="fhero__cell">
        <Tooltip content="Standings-points shift from this offseason's moves alone, vs last season's roster.">
          <span className="fhero__label">Change from moves</span>
        </Tooltip>
        <span className={`fhero__value mono fhero__change ${changeClass}`}>
          {f.points_delta != null ? `${fmtPointsDelta(f.points_delta)} pts` : fmtRating(f.delta)}
        </span>
        <span className="fhero__sub">{changeWords(f.delta)}</span>
      </div>

      <div className="fhero__cell">
        <Tooltip content="Projected league rank by projected points (1 = best).">
          <span className="fhero__label">League rank</span>
        </Tooltip>
        <span className="fhero__value mono">{fmtRank(f.projected_rank)}</span>
        <span className="fhero__sub">of 32 teams</span>
      </div>

      <div className="fhero__cell">
        <Tooltip content="Lineup-relevant arrivals and departures logged this offseason (depth churn excluded).">
          <span className="fhero__label">Moves logged</span>
        </Tooltip>
        <span className="fhero__value mono">{f.n_moves}</span>
        <span className="fhero__sub">{f.n_moves === 0 ? 'none yet' : 'in / out'}</span>
      </div>
    </div>
  )
}
