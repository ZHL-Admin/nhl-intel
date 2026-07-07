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
import { ComponentStackBar, ShareActions } from '../common'
import { TeamTradeResult } from '../../api/types'
import { getTeamAbbrev, getTeamLogoUrl, getTeamName } from '../../utils/teams'
import { fmtWar, fmtWarBand, fmtDollarsM, fmtCapShare, deltaClass, CAP_DOLLAR_TAG } from '../../utils/format'
import './TradeVerdict.css'

export interface Domains { talent: [number, number]; surplus: [number, number] }

/** Verdict-kicker date stamp, e.g. "JUL 6" (browser-local; the share card echoes it). */
const shareStamp = () => new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()
/** One deterministic share sentence from each side's categorical lean, e.g.
 * "Canadiens win the trade; Bruins retool — shed cost for futures." */
function tradeShareVerdict(teams: TeamTradeResult[]): string {
  return teams.map((t) => `${getTeamName(getTeamAbbrev(t.team_id))} ${teamLean(t).label.toLowerCase()}`).join('; ')
}

function barColor(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 1e-9) return 'var(--color-data-neutral)'
  return v > 0 ? 'var(--color-data-positive)' : 'var(--color-data-negative)'
}

/** True when this side trades any pick/prospect — cap-share is muddy there, so de-emphasize it. */
function isFuturesHeavy(t: TeamTradeResult): boolean {
  return [...t.incoming, ...t.outgoing].some((p) => p.asset_type !== 'player')
}

/** The cross-team parts for one team — built from typed fields so the axis rule (lead talent +
 * dollars; cap-share only for player-for-player sides) is applied consistently with the per-team
 * decomposition, rather than from the engine's pre-baked gains string (which always names cap-share). */
function summaryParts(t: TeamTradeResult): string[] {
  const parts: string[] = []
  if (t.talent_delta_war != null) parts.push(`${fmtWar(t.talent_delta_war)} WAR talent`)
  if (t.surplus_delta_dollars != null) {
    const cs = isFuturesHeavy(t) || t.surplus_delta_capshare == null ? '' : ` · ${fmtCapShare(t.surplus_delta_capshare)}`
    parts.push(`${fmtDollarsM(t.surplus_delta_dollars, true)} surplus${cs}`)
  }
  if (t.fit_delta != null) parts.push(`fit ${t.fit_delta >= 0 ? '+' : '−'}${Math.abs(t.fit_delta).toFixed(1)}`)
  if (t.cap?.cap_hit_change != null) parts.push(`cap ${fmtDollarsM(t.cap.cap_hit_change, true)}${t.cap.over_cap ? ' · over' : ''}`)
  return parts
}

export function TradeSummaryBand({ teams }: { teams: TeamTradeResult[] }) {
  if (!teams.length) return null
  return (
    <div className="trade-verdict__summary">
      <div className="trade-verdict__summary-head">
        <h2 className="trade-verdict__summary-title">The Numbers</h2>
        <div className="trade-verdict__summary-share">
          <span className="trade-verdict__kicker mono">TRADE VERDICT · {shareStamp()}</span>
          <ShareActions kicker={`TRADE VERDICT · ${shareStamp()}`} verdict={tradeShareVerdict(teams)}
            shareName="trade-verdict" />
        </div>
      </div>
      <div className="trade-verdict__summary-grid">
        {teams.map((t) => (
          <div key={t.team_id} className="trade-verdict__summary-team">
            <img className="trade-verdict__summary-logo" src={getTeamLogoUrl(getTeamAbbrev(t.team_id))} alt=""
                 onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
            <div className="trade-verdict__summary-body">
              <span className="trade-verdict__summary-name">{getTeamName(getTeamAbbrev(t.team_id))}</span>
              <div className="trade-verdict__summary-parts">
                {summaryParts(t).map((g, i) => <span key={i} className="trade-verdict__part">{g}</span>)}
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

/** A categorical lean per team — the ANSWER (does this side gain?), backed by the decomposition
 * below and the engine's reasoning sentence. Derived transparently from the talent + surplus signs;
 * it is a qualitative read, not a single numeric score. */
function teamLean(t: TeamTradeResult): { label: string; tone: 'pos' | 'neg' | 'zero' } {
  const war = t.talent_delta_war ?? 0
  const sur = t.surplus_delta_dollars ?? 0
  const warUp = war >= 0.5, warDn = war <= -0.5
  const surUp = sur >= 2_000_000, surDn = sur <= -2_000_000
  if (warUp && !surDn) return { label: 'Wins the trade', tone: 'pos' }
  if (warUp && surDn) return { label: 'Win-now — pays a premium', tone: 'zero' }
  if (warDn && surUp) return { label: 'Retools — sheds cost for futures', tone: 'zero' }
  if (warDn && surDn) return { label: 'Loses the trade', tone: 'neg' }
  if (surUp) return { label: 'Gains value', tone: 'pos' }
  if (surDn) return { label: 'Loses value', tone: 'neg' }
  return { label: 'Roughly even', tone: 'zero' }
}

export function TeamDecomposition({ result, domains }: { result: TeamTradeResult; domains: Domains }) {
  const t = result
  const futures = isFuturesHeavy(t)
  const lean = teamLean(t)
  const talentSe = t.talent_delta_war_low != null && t.talent_delta_war_high != null
    ? (t.talent_delta_war_high - t.talent_delta_war_low) / 2 : null
  const surplusSe = t.surplus_delta_dollars_low != null && t.surplus_delta_dollars_high != null
    ? (t.surplus_delta_dollars_high - t.surplus_delta_dollars_low) / 2 : null
  const cap = t.cap

  return (
    <div className="trade-verdict__team">
      <div className="trade-verdict__team-head">
        <span className={`trade-verdict__lean trade-verdict__lean--${lean.tone}`}>{lean.label}</span>
      </div>

      {t.summary && <p className="trade-verdict__why">{t.summary}</p>}

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
