/**
 * ImpactNarrative — the consolidated Impact & Value read on the player profile. ONE story in ONE
 * headline unit (percentile). Reading order is ADAPTIVE on the entangled flag:
 *   - entangled player  -> lead with the confidence caveat, then the WOWY evidence, then the bars
 *   - other player      -> lead with the impact-vs-value gap, then the bars, then WOWY as support
 * Reuses playerDetail.value (impact/value percentiles + gap + the value_gap `read`) — no recompute.
 * Entanglement changes the primary number: the Impact percentile renders as a visibly WIDE, muted,
 * low-confidence RANGE (UncertaintyBand) rather than a crisp tick. GAR/WAR stays visible as a
 * demoted sub-line under the Value bar. r-values live only in the confidence tooltip. Locked tier
 * vocabulary + band widths (shared with the ranked Players page) live in the spec.
 */
import { useContext, useMemo } from 'react'
import { PlayerValue, ImpactContext, WowyPartner } from '../../api/types'
import UncertaintyBand from '../common/UncertaintyBand'
import Tooltip from '../common/Tooltip'
import { PageCardContext } from '../common/PageCard'
import WowyPartnerPanel from './WowyPartnerPanel'
import './ImpactNarrative.css'

const asPctile = (p?: number | null) => (p == null ? null : Math.round(p * 100))
const ord = (n: number) => {
  const v = n % 100
  if (v >= 11 && v <= 13) return `${n}th`
  switch (n % 10) { case 1: return `${n}st`; case 2: return `${n}nd`; case 3: return `${n}rd`; default: return `${n}th` }
}
const clamp = (n: number) => Math.max(0, Math.min(100, n))

// Locked confidence vocabulary + band half-widths (identical on the ranked Players page).
function confidence(entangled: boolean) {
  return entangled
    ? { tier: 'Low confidence · entangled', band: 22, low: true }
    : { tier: 'Moderate confidence', band: 12, low: false }
}

export default function ImpactNarrative(
  { value, ctx, wowy, name }: { value: PlayerValue; ctx: ImpactContext | null; wowy: WowyPartner[]; name: string },
) {
  const insideCard = useContext(PageCardContext)
  const last = name.split(' ').slice(-1)[0]
  const entangled = !!ctx?.entangled
  const conf = confidence(entangled)

  const ip = asPctile(value.impact_percentile)
  const vp = asPctile(value.value_percentile)
  const ranked = ip != null && vp != null
  const gap = ranked ? ip! - vp! : null   // + => impact over value (drives more than he has produced)
  const share = ctx?.max_partner_toi_share

  const topPartner = useMemo(
    () => (wowy.length ? [...wowy].sort((a, b) => b.toi_together_sec - a.toi_together_sec)[0] : null),
    [wowy],
  )

  // --- lead sentence (ADAPTIVE) ---
  const lead = entangled
    ? {
        head: `We can't cleanly separate ${last}'s impact from ${topPartner?.partner_name?.split(' ').slice(-1)[0] ?? 'his top partner'} this season`,
        body: `${share != null ? `${Math.round(share * 100)}% of ${last}'s 5v5 minutes came with one linemate` : `${last}'s minutes are concentrated with one linemate`}, so read the isolated impact below as a wide range, not a verdict. The proof is in the with-and-without splits.`,
      }
    : value.read
      ? { head: value.read.headline, body: value.read.body ?? '' }
      : ranked
        ? {
            head: gap! > 8 ? `${last} drives play more than he has produced`
              : gap! < -8 ? `${last} has produced more than the play-driving explains`
              : `${last}'s impact and production line up`,
            body: `Impact ${ord(ip!)} vs Value ${ord(vp!)} percentile, within position.`,
          }
        : { head: `${last}'s isolated impact`, body: '' }

  const Lead = (
    <div className="imn__lead">
      <h2 className="imn__lead-head">{lead.head}</h2>
      {lead.body && <p className="imn__lead-body">{lead.body}</p>}
    </div>
  )

  const Confidence = (
    <Tooltip content={`Confidence in the single-season isolated (RAPM) number. Single-season impact is never high-confidence — year-to-year stability is r ≈ ${value.rapm_r.toFixed(2)} (production r ≈ ${value.production_r.toFixed(2)}, finishing r ≈ ${value.finishing_r.toFixed(2)}).${entangled ? ' Entangled minutes widen the range further, because the isolated estimate cannot be split from the most-common partner.' : ''}`}>
      <span className={`imn__conf${conf.low ? ' imn__conf--low' : ''}`}>{conf.tier}</span>
    </Tooltip>
  )

  const Bars = ranked ? (
    <div className="imn__bars">
      <div className="imn__bar">
        <div className="imn__bar-head">
          <span className="imn__bar-lbl">Impact <small>drives play</small></span>
          <span className="imn__bar-val">
            {conf.low
              ? <>~{ord(clamp(ip! - conf.band))}–{ord(clamp(ip! + conf.band))}<small>pctile · low-confidence range</small></>
              : <>{ord(ip!)}<small>pctile</small></>}
          </span>
        </div>
        <div className={`imn__band${conf.low ? ' imn__band--low' : ''}`}>
          <UncertaintyBand
            value={ip!} lo={clamp(ip! - conf.band)} hi={clamp(ip! + conf.band)} domainMin={0} domainMax={100} size="md"
            colorVar={conf.low ? 'var(--color-text-secondary)' : 'var(--color-team-primary)'}
          />
        </div>
      </div>

      <div className="imn__bar">
        <div className="imn__bar-head">
          <span className="imn__bar-lbl">Value <small>production</small></span>
          <span className="imn__bar-val">{ord(vp!)}<small>pctile</small></span>
        </div>
        <div className="imn__band">
          <UncertaintyBand
            value={vp!} lo={clamp(vp! - Math.min(22, value.war_sd * 4))} hi={clamp(vp! + Math.min(22, value.war_sd * 4))}
            domainMin={0} domainMax={100} size="md"
          />
        </div>
        <div className="imn__gar">
          {value.gar >= 0 ? '+' : ''}{value.gar.toFixed(1)} GAR · {value.war >= 0 ? '+' : ''}{value.war.toFixed(1)} ± {value.war_sd.toFixed(1)} WAR
        </div>
      </div>

      {gap != null && Math.abs(gap) >= 10 && (
        <p className="imn__gap">
          {gap > 0
            ? `Impact ${ord(ip!)} vs Value ${ord(vp!)}: drives play more than he has produced.`
            : `Value ${ord(vp!)} vs Impact ${ord(ip!)}: has produced more than the play-driving explains.`}
        </p>
      )}
    </div>
  ) : (
    <p className="imn__muted">{last} hasn't the 5v5 minutes to rank within position this season; GAR shown without a percentile read.</p>
  )

  const Wowy = wowy.length ? (
    <div className="imn__evidence">
      {entangled && <p className="imn__evidence-lead">The proof — what actually happens with and without each linemate:</p>}
      <WowyPartnerPanel partners={wowy} name={name} />
    </div>
  ) : null

  const Baseline = ctx?.single_vs_multi_delta != null ? (
    <p className="imn__baseline">
      This season's isolated impact is{' '}
      {ctx.single_vs_multi_delta > 0.08 ? <strong>above</strong> : ctx.single_vs_multi_delta < -0.08 ? <strong>below</strong> : 'in line with'}{' '}
      his three-year baseline
      {ctx.single_vs_multi_delta > 0.08 ? ' — trending up on a short, noisy sample.' : ctx.single_vs_multi_delta < -0.08 ? ' — down from his longer track record.' : '.'}
    </p>
  ) : null

  // ADAPTIVE reading order (see spec)
  const sections = entangled
    ? [Lead, Confidence, Wowy, Bars, Baseline]
    : [Lead, Bars, Confidence, Wowy, Baseline]

  return (
    <div className={`imn${insideCard ? ' imn--flat' : ''}`}>
      {sections.map((sec, i) => (sec ? <div key={i} className="imn__sec">{sec}</div> : null))}
    </div>
  )
}
