/**
 * The scoreboard (doc 13 §2) — the verdict, one elevated Panel above the pieces. It re-renders
 * live as assets change. Two-team: a balance meter flanked by team blocks. N>=3: stacked team
 * rows with zero-centered signed micro-bars, sorted best-edge-first. Receipts below an internal
 * hairline, valence dots per that team's perspective. Confidence dot-chip + a "How we judge
 * trades" tooltip carry the method; ShareActions renders the copy-link + share-card controls.
 */
import { Info } from 'lucide-react'
import { DotChip, Tooltip, ShareActions } from '../common'
import { TeamTradeResult } from '../../api/types'
import { getTeamAbbrev, getTeamLogoUrl, getTeamName } from '../../utils/teams'
import { fmtDollarsM } from '../../utils/format'
import {
  twoTeamTilt, rolePhrase, rowEdgeLabel, netEdge, netEdgeDollars,
  combinedConfidence, teamReceipts, verdictSentence, Receipt as ReceiptT,
} from './verdictLogic'
import './Scoreboard.css'

const shareStamp = () => new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()

const HOW_WE_JUDGE =
  'The verdict weighs projected talent (WAR over the remaining term) against price vs market ' +
  '(surplus value: worth minus cost, present-valued), on a shared basis. The tilt is derived: ' +
  'each side’s net edge combines its talent delta and its price-vs-market delta at roughly ' +
  '$3.5M per WAR; the meter points to the higher net edge, the same source as the home Ledger’s ' +
  '"Edge {TEAM}". Fit and the cap are read alongside, not folded into the tilt.'

function receiptColor(v: ReceiptT['valence']): string {
  return v === 'pos' ? 'var(--color-data-positive)' : v === 'neg' ? 'var(--color-data-negative)' : 'var(--color-text-muted)'
}

function Receipts({ items }: { items: ReceiptT[] }) {
  return (
    <div className="tb-receipts">
      {items.map((r, i) => (
        <div key={i} className="tb-receipt">
          <span className="tb-receipt__dot" style={{ background: receiptColor(r.valence) }} />
          <span className="tb-receipt__text"><b>{r.lead}</b> — {r.body}</span>
        </div>
      ))}
    </div>
  )
}

function TeamBlock({ t, align }: { t: TeamTradeResult; align: 'left' | 'right' }) {
  const abbrev = getTeamAbbrev(t.team_id)
  return (
    <div className={`tb-team tb-team--${align}`}>
      <img className="tb-team__logo" src={getTeamLogoUrl(abbrev)} alt=""
           onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
      <div className="tb-team__body">
        <span className="tb-team__name">{getTeamName(abbrev)}</span>
        <span className="tb-team__role">{rolePhrase(t)}</span>
      </div>
    </div>
  )
}

/** The balance meter: hairline track, quarter ticks, stronger center tick, one ink dot by the tilt. */
function BalanceMeter({ value, label }: { value: number; label: string }) {
  const pct = 50 + value * 50   // value in [-1, 1] → 0..100%
  return (
    <div className="tb-meter">
      <div className="tb-meter__track">
        <span className="tb-meter__tick" style={{ left: '25%' }} />
        <span className="tb-meter__tick tb-meter__tick--center" style={{ left: '50%' }} />
        <span className="tb-meter__tick" style={{ left: '75%' }} />
        <span className="tb-meter__dot" style={{ left: `${pct}%` }} />
      </div>
      <span className="tb-meter__label">{label}</span>
    </div>
  )
}

/** A zero-centered signed micro-bar (GAR composition anatomy): blue right of zero, red left. */
function EdgeBar({ value, scale }: { value: number; scale: number }) {
  const frac = scale > 0 ? Math.max(-1, Math.min(1, value / scale)) : 0
  const pctW = Math.abs(frac) * 50
  const color = value >= 0 ? 'var(--color-data-positive)' : 'var(--color-data-negative)'
  return (
    <span className="tb-edgebar">
      <span className="tb-edgebar__center" />
      <span className="tb-edgebar__fill" style={{
        left: value >= 0 ? '50%' : `${50 - pctW}%`, width: `${pctW}%`, background: color,
      }} />
    </span>
  )
}

function ScoreboardHead({ teams }: { teams: TeamTradeResult[] }) {
  const conf = combinedConfidence(teams)
  const confLabel = `${conf.charAt(0).toUpperCase()}${conf.slice(1)} confidence`
  return (
    <div className="tb-scoreboard__head">
      <span className="tb-scoreboard__eyebrow">THE VERDICT · {shareStamp()}</span>
      <div className="tb-scoreboard__meta">
        <DotChip label={confLabel} state={conf === 'high' ? 'filled' : 'projected'}
          color={conf === 'high' ? 'var(--line-blue)' : 'var(--color-text-muted)'} />
        <Tooltip content={HOW_WE_JUDGE}>
          <span className="tb-scoreboard__how"><Info size={12} /> How we judge trades</span>
        </Tooltip>
        <ShareActions kicker={`TRADE VERDICT · ${shareStamp()}`} verdict={verdictSentence(teams)}
          shareName="trade-verdict" />
      </div>
    </div>
  )
}

export default function Scoreboard({ teams }: { teams: TeamTradeResult[] }) {
  if (teams.length < 2) return null

  // N >= 3 — stacked rows sorted by net edge, best first; shared micro-bar scale.
  if (teams.length >= 3) {
    const sorted = [...teams].sort((a, b) => netEdge(b) - netEdge(a))
    const scale = Math.max(1e6, ...sorted.map((t) => Math.abs(netEdgeDollars(t))))
    return (
      <section className="tb-scoreboard">
        <ScoreboardHead teams={teams} />
        <div className="tb-scoreboard__hairline" />
        <div className="tb-rows">
          {sorted.map((t, i) => {
            const edge = netEdgeDollars(t)
            return (
              <div key={t.team_id} className="tb-row">
                <img className="tb-row__logo" src={getTeamLogoUrl(getTeamAbbrev(t.team_id))} alt=""
                     onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
                <div className="tb-row__id">
                  <span className="tb-row__name">{getTeamName(getTeamAbbrev(t.team_id))}</span>
                  <span className="tb-row__role">{rolePhrase(t)}</span>
                </div>
                <div className="tb-row__bar">
                  <EdgeBar value={edge} scale={scale} />
                  <span className="tb-row__edgelabel">{rowEdgeLabel(t, i, sorted.length)} · {fmtDollarsM(edge, true)} eq</span>
                </div>
                <Receipts items={teamReceipts(t, 2)} />
              </div>
            )
          })}
        </div>
      </section>
    )
  }

  // Two teams — the balance meter flanked by mirrored team blocks.
  const [left, right] = teams
  const tilt = twoTeamTilt(left, right)
  return (
    <section className="tb-scoreboard">
      <ScoreboardHead teams={teams} />
      <div className="tb-scoreboard__stage">
        <TeamBlock t={left} align="left" />
        <BalanceMeter value={tilt.value} label={tilt.meterLabel} />
        <TeamBlock t={right} align="right" />
      </div>
      <div className="tb-scoreboard__hairline" />
      <div className="tb-scoreboard__receipts">
        <Receipts items={teamReceipts(left, 3)} />
        <Receipts items={teamReceipts(right, 3)} />
      </div>
    </section>
  )
}
