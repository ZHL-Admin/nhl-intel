/**
 * Isolated-impact context — reads beside ImpactValuePanel on the player profile. Shows the
 * single-season isolated (RAPM) impact with an uncertainty band (widened when the player is
 * entangled), its divergence from the three-year weighted baseline, the carry signal, and an
 * entanglement badge. No blended score: every field is shown separately. Reuses the recurring
 * uncertainty motif (UncertaintyBand). Data from mart_player_impact_context via
 * GET /players/{id}/summary.impact_context.
 */
import { useContext } from 'react'
import { ImpactContext } from '../../api/types'
import UncertaintyBand from '../common/UncertaintyBand'
import Tooltip from '../common/Tooltip'
import { PageCardContext } from '../common/PageCard'
import './ImpactContextPanel.css'

const IMPACT_DOMAIN = 1.2   // xGF/60 isolated impact roughly spans ±1.2
const STABILITY_R = 0.43    // single-season offence-impact YoY r (≥200 5v5 min); isolated-impact.md

const signed = (v?: number | null, d = 2) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}`

function headline(delta?: number | null): string {
  if (delta == null) return 'Isolated impact this season'
  if (delta > 0.08) return 'Driving results above his three-year impact'
  if (delta < -0.08) return 'Below his three-year impact baseline'
  return 'In line with his three-year impact'
}

export default function ImpactContextPanel({ ctx, name }: { ctx: ImpactContext; name: string }) {
  const insideCard = useContext(PageCardContext)
  const { total_impact: total, multi_total_impact: multi, single_vs_multi_delta: delta } = ctx
  const entangled = !!ctx.entangled
  const share = ctx.max_partner_toi_share
  const carry = ctx.carry_score
  const last = name.split(' ').slice(-1)[0]

  if (total == null) return null

  // 95% band on the single-season total, widened when entangled (harder to separate)
  const sd = Math.sqrt((ctx.off_sd ?? 0) ** 2 + (ctx.def_sd ?? 0) ** 2)
  const half = 1.96 * sd * (entangled ? 1.6 : 1)

  return (
    <div className={`icx${insideCard ? ' icx--flat' : ''}`}>
      <div className="icx__head">
        <h3 className="icx__title">{headline(delta)}</h3>
        {entangled && (
          <Tooltip content={`${last}'s 5v5 minutes are heavily concentrated with one linemate${
            share != null ? ` (${Math.round(share * 100)}% with his top partner)` : ''
          }. The isolated, teammate-adjusted estimate is harder to separate here, so read the wider band, not the point.`}>
            <span className="icx__badge" role="img" aria-label="entangled minutes">Entangled</span>
          </Tooltip>
        )}
      </div>

      <div className="icx__band">
        <UncertaintyBand
          value={total} lo={total - half} hi={total + half}
          domainMin={-IMPACT_DOMAIN} domainMax={IMPACT_DOMAIN} size="md"
        />
        <div className="icx__scale"><span>−{IMPACT_DOMAIN.toFixed(1)}</span><span>0</span><span>+{IMPACT_DOMAIN.toFixed(1)}</span></div>
      </div>

      <div className="icx__stats">
        <Tooltip content="Single-season isolated (RAPM) impact: this player's effect on 5v5 expected goals per 60, after adjusting for teammates, competition, zone starts, and score. Higher is better.">
          <div className="icx__stat">
            <span className="icx__stat-lbl">This season</span>
            <span className="icx__stat-val">{signed(total)}</span>
          </div>
        </Tooltip>
        <div className="icx__stat">
          <span className="icx__stat-lbl">3-year</span>
          <span className="icx__stat-val">{signed(multi)}</span>
        </div>
        <Tooltip content="How this season's isolated impact diverges from the three-year weighted window. A large positive gap is a breakout signal; single-season RAPM is noisier than the window, so read them together.">
          <div className={`icx__stat ${delta != null && delta > 0 ? 'is-pos' : delta != null && delta < 0 ? 'is-neg' : ''}`}>
            <span className="icx__stat-lbl">vs 3-year</span>
            <span className="icx__stat-val">{signed(delta)}</span>
          </div>
        </Tooltip>
        {carry != null && (
          <Tooltip content={`Carry: how much better ${last}'s linemates do with him than without, TOI-weighted across partners. Positive means he lifts the players around him.`}>
            <div className={`icx__stat ${carry > 0 ? 'is-pos' : carry < 0 ? 'is-neg' : ''}`}>
              <span className="icx__stat-lbl">Carry</span>
              <span className="icx__stat-val">{signed(carry)}</span>
            </div>
          </Tooltip>
        )}
      </div>

      <p className="icx__foot">
        Single-season isolated impact is a moderate-repeatability signal (year-to-year r ≈ {STABILITY_R.toFixed(2)});
        read it alongside the three-year window{entangled ? ' — and wider still here, since his minutes are entangled' : ''}.
      </p>
    </div>
  )
}
