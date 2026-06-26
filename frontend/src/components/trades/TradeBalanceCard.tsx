/**
 * TradeBalanceCard (Handoff 6) — the single-trade verdict leaf. A balance bar that tilts to the side
 * that won, with the band, the verdict sentence, and an expandable per-asset ledger. The unit you land
 * on from the value map, a dossier deal, an exemplar, or search.
 *
 * Slot is the headline lens on every bar; the actual lens only swaps in when both sides are resolved.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react'
import { getTeamColor, getTeamLogoUrl, getTeamName } from '../../utils/teams'
import { TradeBoardItem, TradeBoardSide, TradeBoardAsset } from '../../api/trades'
import Tilt from './Tilt'
import './trades.css'

const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`

function sideNet(s: TradeBoardSide, lens: 'slot' | 'actual'): number | null {
  return lens === 'actual' ? s.net_war_actual : s.net_war_slot
}

function AssetLine({ a }: { a: TradeBoardAsset }) {
  const pick = a.asset_type === 'Draft Pick'
  const future = a.asset_type === 'Other'
  return (
    <div className="tbl-asset">
      <span className="tbl-asset__name">
        {a.player_id != null
          ? <Link to={`/players/${a.player_id}`}>{a.label}</Link>
          : future ? <span className="tbl-muted">future considerations</span> : a.label}
        {pick && a.became_player_id != null && (
          <span className="tbl-asset__became"> → <Link to={`/players/${a.became_player_id}`}>{a.became_player_name}</Link></span>
        )}
        {pick && a.became_player_id == null && <span className="tbl-tag tbl-tag--muted">unresolved</span>}
        {a.conditional && <span className="tbl-tag">conditional</span>}
      </span>
      <span className="tbl-asset__vals">
        <span className="mono">{a.war_slot.toFixed(1)}</span>
        <span className="mono tbl-muted">{a.war_actual == null ? '—' : a.war_actual.toFixed(1)}</span>
      </span>
    </div>
  )
}

export default function TradeBalanceCard({ trade, lens = 'slot', focusTeam, defaultOpen = false }: {
  trade: TradeBoardItem; lens?: 'slot' | 'actual'; focusTeam?: string; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)

  // order sides so the focus entity (a dossier's team) reads on the left
  const sides = [...trade.sides]
  if (focusTeam) sides.sort((a, b) => (a.team_abbrev === focusTeam ? -1 : b.team_abbrev === focusTeam ? 1 : 0))
  const threeTeam = trade.team_count >= 3

  const actualResolvable = trade.margin_actual != null
  const useActual = lens === 'actual' && actualResolvable

  // 2-team: one bar, positive = right side won
  const left = sides[0], right = sides[1]
  const signed = right ? ((useActual ? (right.net_war_actual ?? 0) : right.net_war_slot)) : 0
  const bandHw = useActual ? (trade.band_hw_actual ?? 0) : trade.band_hw_slot
  const winnerColor = trade.winner_team_id != null
    ? getTeamColor(sides.find((s) => s.team_id === trade.winner_team_id)?.team_abbrev || left.team_abbrev)
    : 'var(--color-text-muted)'

  const winnerAbbrev = sides.find((s) => s.team_id === trade.winner_team_id)?.team_abbrev
  const verdictText = trade.incomplete
    ? `still maturing — through year ${trade.realized_year} of 5`
    : trade.verdict === 'too_close'
      ? `too close to call (within ±${bandHw.toFixed(1)} WAR)`
      : `${trade.verdict === 'lean' ? 'leans' : ''} ${winnerAbbrev ? getTeamName(winnerAbbrev) : ''} ${trade.verdict === 'decisive' ? 'won this,' : ''} ${fmt(Math.abs(trade.margin_slot))} WAR`.trim()

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
          tooClose={trade.verdict === 'too_close'} incomplete={trade.incomplete} size="full" />
      ) : (
        <div className="tbl-multibar">
          {sides.map((s) => {
            const net = sideNet(s, useActual ? 'actual' : 'slot') ?? 0
            return (
              <div key={s.team_abbrev} className="tbl-multibar__row">
                <span className="tbl-multibar__lbl mono">{s.team_abbrev}</span>
                <Tilt signed={net} bandHw={0} color={getTeamColor(s.team_abbrev)} tooClose={false} incomplete={trade.incomplete} size="compact" />
                <span className="mono tbl-multibar__v">{fmt(net)}</span>
              </div>
            )
          })}
          <span className="tbl-tag">3-team</span>
        </div>
      )}

      <div className="tbl-verdict">
        {lens === 'actual' && !actualResolvable
          ? <span className="tbl-muted">actual not resolvable for this trade</span>
          : <span>{verdictText}</span>}
      </div>

      <button className="tbl-expand" onClick={() => setOpen((o) => !o)}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />} ledger
      </button>
      {open && (
        <div className="tbl-ledger">
          {sides.map((s) => (
            <div key={s.team_abbrev} className="tbl-ledger__col">
              <div className="tbl-ledger__head">{s.team_abbrev} got <span className="tbl-muted">(slot · actual)</span></div>
              {s.assets.length ? s.assets.map((a, i) => <AssetLine key={i} a={a} />)
                : <div className="tbl-muted">—</div>}
            </div>
          ))}
          <div className="tbl-ledger__foot tbl-muted">
            {trade.archetype.replace(/_/g, ' ')} · {actualResolvable ? 'both resolved' : 'actual unresolved'} · confidence {trade.confidence}
          </div>
        </div>
      )}
    </div>
  )
}

function Tooltip({ label }: { label: string }) {
  return <span className="tbl-flag" title={label}><AlertTriangle size={11} /></span>
}
