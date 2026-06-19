/**
 * Trade verdict rendering — verdict-first, decomposition never a bare grade.
 *
 *  - TradeSummaryBand: the cross-team "who gains what", each team's parts (talent / surplus / fit /
 *    cap), led by talent (WAR) and the dollar figure.
 *  - TeamDecomposition: one team's parts as labeled rows with a de-defaulted magnitude bar
 *    (ComponentStackBar, total variant, band = whisker) on a scale shared across teams.
 *
 * Axis rule: lead with talent (WAR) and the dollar surplus. Cap-share is the contract-efficiency
 * lens — shown for player-for-player sides, de-emphasized on pick/prospect-heavy sides where it is
 * semantically muddy.
 */
import { ComponentStackBar } from '../common'
import { TeamTradeResult, TradeSummaryLine } from '../../api/types'
import { getTeamAbbrev, getTeamLogoUrl, getTeamName } from '../../utils/teams'
import { fmtWar, fmtWarBand, fmtDollarsM, fmtCapShare, deltaClass, CAP_DOLLAR_TAG } from '../../utils/format'
import './TradeVerdict.css'

export interface Domains { talent: [number, number]; surplus: [number, number] }

const CONF_LABEL: Record<string, string> = { high: 'High confidence', medium: 'Medium confidence', low: 'Low confidence' }

function barColor(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 1e-9) return 'var(--color-data-neutral)'
  return v > 0 ? 'var(--color-data-positive)' : 'var(--color-data-negative)'
}

/** True when this side trades any pick/prospect — cap-share is muddy there, so de-emphasize it. */
function isFuturesHeavy(t: TeamTradeResult): boolean {
  return [...t.incoming, ...t.outgoing].some((p) => p.asset_type !== 'player')
}

export function TradeSummaryBand({ summary }: { summary: TradeSummaryLine[] }) {
  if (!summary.length) return null
  return (
    <div className="trade-verdict__summary">
      <h2 className="trade-verdict__summary-title">Who gains what</h2>
      <div className="trade-verdict__summary-grid">
        {summary.map((s) => (
          <div key={s.team_id} className="trade-verdict__summary-team">
            <img className="trade-verdict__summary-logo" src={getTeamLogoUrl(getTeamAbbrev(s.team_id))} alt=""
                 onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
            <div className="trade-verdict__summary-body">
              <span className="trade-verdict__summary-name">{getTeamName(getTeamAbbrev(s.team_id))}</span>
              <div className="trade-verdict__summary-parts">
                {s.gains.map((g, i) => <span key={i} className="trade-verdict__part">{g}</span>)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Axis({ label, valueText, sub, total, se, domain, subdued }: {
  label: string; valueText: string; sub?: string
  total: number | null | undefined; se?: number | null; domain: [number, number]; subdued?: boolean
}) {
  return (
    <div className={`trade-axis${subdued ? ' trade-axis--subdued' : ''}`}>
      <div className="trade-axis__head">
        <span className="trade-axis__label">{label}</span>
        <span className={`trade-axis__value trade-axis__value--${deltaClass(total)}`}>{valueText}</span>
      </div>
      {total != null && (
        <ComponentStackBar segments={[]} total={total} domain={domain} se={se ?? null}
          variant="total" totalColor={barColor(total)} height={16} gridlines={[0]}
          formatValue={(v) => label === 'Talent' ? fmtWar(v) : fmtDollarsM(v, true)} />
      )}
      {sub && <span className="trade-axis__sub">{sub}</span>}
    </div>
  )
}

export function TeamDecomposition({ result, domains }: { result: TeamTradeResult; domains: Domains }) {
  const t = result
  const futures = isFuturesHeavy(t)
  const talentSe = t.talent_delta_war_low != null && t.talent_delta_war_high != null
    ? (t.talent_delta_war_high - t.talent_delta_war_low) / 2 : null
  const surplusSe = t.surplus_delta_dollars_low != null && t.surplus_delta_dollars_high != null
    ? (t.surplus_delta_dollars_high - t.surplus_delta_dollars_low) / 2 : null
  const cap = t.cap

  return (
    <div className="trade-verdict__team">
      <div className="trade-verdict__team-head">
        <span className="trade-verdict__team-label">Verdict</span>
        <span className={`trade-verdict__conf trade-verdict__conf--${t.confidence}`}>
          {CONF_LABEL[t.confidence ?? ''] ?? t.confidence}
        </span>
      </div>

      {t.incoming.length > 0 && (
        <p className="trade-verdict__acquires">
          <span className="trade-verdict__acquires-lbl">Acquires</span>
          {t.incoming.map((p) => p.label).join(', ')}
        </p>
      )}

      <Axis label="Talent" total={t.talent_delta_war} se={talentSe} domain={domains.talent}
        valueText={`${fmtWar(t.talent_delta_war)} WAR`}
        sub={fmtWarBand(t.talent_delta_war_low, t.talent_delta_war_high)
          ? `range ${fmtWarBand(t.talent_delta_war_low, t.talent_delta_war_high)}` : undefined} />

      <Axis label="Cost-efficiency" total={t.surplus_delta_dollars} se={surplusSe} domain={domains.surplus}
        valueText={fmtDollarsM(t.surplus_delta_dollars, true)}
        sub={futures
          ? `surplus, ${CAP_DOLLAR_TAG}`
          : `${CAP_DOLLAR_TAG} · ${fmtCapShare(t.surplus_delta_capshare)} cap efficiency`} />

      {t.fit_delta != null && (
        <div className="trade-axis trade-axis--fit">
          <div className="trade-axis__head">
            <span className="trade-axis__label">Fit (incoming)</span>
            <span className={`trade-axis__value trade-axis__value--${deltaClass(t.fit_delta)}`}>
              {t.fit_delta >= 0 ? '+' : '−'}{Math.abs(t.fit_delta).toFixed(1)}
            </span>
          </div>
          {t.fit_details.length > 0 && (
            <span className="trade-axis__sub">
              {t.fit_details.map((f) => `${f.player_name} ${f.grade ?? ''}`).join(' · ')}
            </span>
          )}
        </div>
      )}

      {cap && (
        <div className="trade-axis trade-axis--cap">
          <div className="trade-axis__head">
            <span className="trade-axis__label">Cap <span className="trade-axis__approx" title={cap.caveat}>approx</span></span>
            <span className={`trade-axis__value trade-axis__value--${cap.over_cap ? 'neg' : 'zero'}`}>
              {cap.over_cap ? 'Over' : 'Under'}{cap.margin != null ? ` ${fmtDollarsM(Math.abs(cap.margin))}` : ''}
            </span>
          </div>
          <span className="trade-axis__sub">
            {fmtDollarsM(cap.committed_before)} → {fmtDollarsM(cap.committed_after)} of {fmtDollarsM(cap.ceiling)}
            {cap.cap_hit_change != null ? ` (${fmtDollarsM(cap.cap_hit_change, true)})` : ''}
          </span>
        </div>
      )}
    </div>
  )
}
