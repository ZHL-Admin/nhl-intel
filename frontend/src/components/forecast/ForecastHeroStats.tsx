import { Tooltip, UncertaintyBand } from '../common'
import { RosterForecastRow } from '../../api/types'
import { fmtRating, fmtBand, fmtRank, changeWords } from '../../utils/forecastFormat'

const RATING_DOMAIN: [number, number] = [-0.4, 1.4]

/** The four hero cells in the identity header: rating (wide, with its band), change, rank, moves. */
export default function ForecastHeroStats({ f }: { f: RosterForecastRow }) {
  const changeClass = Math.abs(f.delta) < 0.03 ? 'is-flat' : f.delta > 0 ? 'is-up' : 'is-down'
  return (
    <div className="fhero">
      <div className="fhero__cell fhero__cell--wide">
        <Tooltip content="Projected next-season team rating in goals per game vs an average team. Built from the moves logged.">
          <span className="fhero__label">Projected rating</span>
        </Tooltip>
        <span className="fhero__value fhero__value--xl mono">{fmtRating(f.projected_rating)}</span>
        <UncertaintyBand value={f.projected_rating} lo={f.band_low} hi={f.band_high}
          domainMin={RATING_DOMAIN[0]} domainMax={RATING_DOMAIN[1]} size="md" />
        <span className="fhero__sub mono">80% range {fmtBand(f.band_low, f.band_high, 2)}</span>
      </div>

      <div className="fhero__cell">
        <Tooltip content="Goals-per-game shift from this offseason's moves alone, vs last season's roster.">
          <span className="fhero__label">Change from moves</span>
        </Tooltip>
        <span className={`fhero__value mono fhero__change ${changeClass}`}>{fmtRating(f.delta)}</span>
        <span className="fhero__sub">{changeWords(f.delta)}</span>
      </div>

      <div className="fhero__cell">
        <Tooltip content="Projected league rank by projected rating (1 = best).">
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
