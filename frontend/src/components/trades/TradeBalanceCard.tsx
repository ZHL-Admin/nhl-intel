/**
 * TradeBalanceCard (Handoff 6) — the single-trade verdict leaf. A balance bar that tilts to the side
 * that won, with the band, the verdict sentence, and an expandable per-asset ledger. The unit you land
 * on from the value map, a dossier deal, an exemplar, or search.
 *
 * One value-based verdict: players at realized tenure pWAR, picks at the slot's empirical expectation.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react'
import { getTeamColor, getTeamLogoUrl, getTeamName } from '../../utils/teams'
import { TradeBoardItem, TradeBoardAsset } from '../../api/trades'
import Tilt from './Tilt'
import './trades.css'

const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`
// mirrors config.TRADE_OUTCOMES['REALIZED_HORIZON_YEARS'] — the trade retrospective's tenure horizon,
// distinct from the Draft Value tool's separate 7-year curve window. Keep in sync if the config changes.
const REALIZED_HORIZON_YEARS = 5

function AssetLine({ a }: { a: TradeBoardAsset }) {
  const pick = a.asset_type === 'Draft Pick'
  const future = a.asset_type === 'Other'

  // A salary-retention broker row: this team kept part of the player's cap hit, but his real new club
  // is a DIFFERENT team in the deal (the backend flags it and zeros its WAR). Render it as the cap
  // mechanism it is — never as the team "getting" the player, which reads as a second acquirer.
  if (a.retention) {
    return (
      <div className="tbl-asset tbl-asset--retention">
        <span className="tbl-asset__name tbl-muted">
          retained {a.retained_pct ? `${a.retained_pct}% of ` : ''}
          {a.player_id != null
            ? <Link to={`/players/${a.player_id}`}>{a.label}</Link>
            : a.label}
          {'’s salary'}
        </span>
      </div>
    )
  }

  return (
    <div className="tbl-asset">
      <span className="tbl-asset__name">
        {a.player_id != null
          ? <Link to={`/players/${a.player_id}`}>{a.label}</Link>
          : future ? <span className="tbl-muted">future considerations</span> : a.label}
        {pick && a.unvaluable && <span className="tbl-tag tbl-tag--muted" title="missing round or pre-trade draft year — cannot value this pick">unvaluable</span>}
        {a.conditional && <span className="tbl-tag">conditional</span>}
      </span>
      <span className="tbl-asset__vals">
        <span className="mono">{a.unvaluable ? '—' : a.war_slot.toFixed(1)}</span>
      </span>
    </div>
  )
}

export default function TradeBalanceCard({ trade, focusTeam, defaultOpen = false, fullHref }: {
  trade: TradeBoardItem; focusTeam?: string; defaultOpen?: boolean; fullHref?: string
}) {
  const [open, setOpen] = useState(defaultOpen)

  // order sides so the focus entity (a dossier's team) reads on the left
  const sides = [...trade.sides]
  if (focusTeam) sides.sort((a, b) => (a.team_abbrev === focusTeam ? -1 : b.team_abbrev === focusTeam ? 1 : 0))
  const threeTeam = trade.team_count >= 3

  // 2-team: one bar, positive = right side won
  const left = sides[0], right = sides[1]
  const signed = right ? right.net_war_slot : 0
  const bandHw = trade.band_hw_slot
  const winnerColor = trade.winner_team_id != null
    ? getTeamColor(sides.find((s) => s.team_id === trade.winner_team_id)?.team_abbrev || left.team_abbrev)
    : 'var(--color-text-muted)'

  const winnerAbbrev = sides.find((s) => s.team_id === trade.winner_team_id)?.team_abbrev
  const winnerName = winnerAbbrev ? getTeamName(winnerAbbrev) : ''
  const m = fmt(Math.abs(trade.margin_slot))
  // Incomplete trades ARE graded — on realized value to date — but show a maturity tag instead of a hard
  // verdict: the realized-to-date margin "so far" with a deliberately wide band. No projection of the rest.
  // Settled trades read one of three tiers: decisive (clears the band), edge (sign known, within the band),
  // even (realized value came out level).
  const verdictText = trade.incomplete
    ? `still maturing — year ${trade.window_progress} of ${REALIZED_HORIZON_YEARS}`
      + (winnerAbbrev ? ` · ${winnerName} ${m} so far (±${bandHw.toFixed(1)})` : ` · even so far (±${bandHw.toFixed(1)})`)
    : trade.verdict === 'even'
      ? 'Even — realized value came out level.'
      : trade.verdict === 'edge'
        ? `Slight edge ${winnerName}, ${m} WAR (within the band)`
        : `${winnerName} won this, ${m} WAR`

  return (
    <div className={`tbl-card ${trade.incomplete ? 'tbl-card--incomplete' : ''}`}>
      <div className="tbl-head">
        <div className="tbl-head__teams">
          {sides.map((s, i) => (
            <span key={s.team_abbrev} className="tbl-head__team">
              {i > 0 && <span className="tbl-muted"> · </span>}
              <img src={getTeamLogoUrl(s.team_abbrev)} alt="" className="tbl-logo" loading="lazy" />
              <span className="mono">{s.team_abbrev}</span>
            </span>
          ))}
        </div>
        <span className="tbl-head__date mono">{trade.date}</span>
      </div>

      {focusTeam && sides.some((s) => s.gm_name) && (
        <div className="tbl-gmline">
          {sides.map((s) => (
            <span key={s.team_abbrev} className="tbl-gmline__item">
              {s.team_abbrev} GM: {s.gm_name || 'unknown'}
              {s.gm_transition && <Tooltip label="attribution uncertain near a handover" />}
            </span>
          ))}
        </div>
      )}

      {!threeTeam ? (
        <Tilt signed={signed} bandHw={bandHw} color={winnerColor}
          even={trade.verdict === 'even'} edge={trade.verdict === 'edge' && !trade.incomplete}
          incomplete={trade.incomplete} size="full" />
      ) : (
        <div className="tbl-multibar">
          {sides.map((s) => {
            const net = s.net_war_slot ?? 0
            return (
              <div key={s.team_abbrev} className="tbl-multibar__row">
                <span className="tbl-multibar__lbl mono">{s.team_abbrev}</span>
                <Tilt signed={net} bandHw={0} color={getTeamColor(s.team_abbrev)} even={false} incomplete={trade.incomplete} size="compact" />
                <span className="mono tbl-multibar__v">{fmt(net)}</span>
              </div>
            )
          })}
          <span className="tbl-tag">3-team</span>
        </div>
      )}

      <div className="tbl-verdict">
        <span>{verdictText}</span>
        {fullHref && <span className="tbl-share"> · <Link to={fullHref}>open full page ↗</Link></span>}
      </div>

      <button className="tbl-expand" onClick={() => setOpen((o) => !o)}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />} ledger
      </button>
      {open && (
        <div className="tbl-ledger">
          {sides.map((s) => (
            <div key={s.team_abbrev} className="tbl-ledger__col">
              <div className="tbl-ledger__head"><span>{s.team_abbrev} got</span><span className="tbl-muted">WAR</span></div>
              {s.assets.length ? s.assets.map((a, i) => <AssetLine key={i} a={a} />)
                : <div className="tbl-muted">—</div>}
            </div>
          ))}
          <div className="tbl-ledger__foot tbl-muted">
            {trade.archetype.replace(/_/g, ' ')} · confidence {trade.confidence}
          </div>
        </div>
      )}
    </div>
  )
}

function Tooltip({ label }: { label: string }) {
  return <span className="tbl-flag" title={label}><AlertTriangle size={11} /></span>
}
