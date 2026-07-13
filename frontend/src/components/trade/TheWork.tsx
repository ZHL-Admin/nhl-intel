/**
 * The work (doc 13 §4) — the appendix. A collapsible section (default expanded, state remembered)
 * holding one shared table: metric + caption (1fr) | a right-aligned value column per team | a
 * context column. Rows: Talent, Price vs market, Fit, Cap. The talent history strip reuses the
 * league-distribution row anatomy, positioned from REAL Trade Outcomes magnitude percentiles.
 */
import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Info } from 'lucide-react'
import { Tooltip } from '../common'
import { TeamTradeResult } from '../../api/types'
import { getTeamAbbrev } from '../../utils/teams'
import { fmtWar, fmtDollarsM, CAP_DOLLAR_TAG, ordinal } from '../../utils/format'
import { getTradeBoard } from '../../api/trades'
import { fitWord, teamFitScore, valOf } from './verdictLogic'
import './TheWork.css'

const STORAGE_KEY = 'tb.work.expanded'

/** The league-distribution strip: real trades as faint ticks, this trade as the ink dot. */
function HistoryStrip({ distribution, magnitude, unit }: {
  distribution: number[]; magnitude: number; unit: 'WAR' | '$'
}) {
  if (!distribution.length) {
    // TODO(data): no served magnitude distribution for this axis — strip omitted, not faked.
    return <span className="tb-work__nostrip">Distribution unavailable</span>
  }
  const max = Math.max(...distribution, magnitude, 1e-9)
  const below = distribution.filter((d) => d < magnitude).length
  const pctile = Math.round((below / distribution.length) * 100)
  const dotPct = Math.min(100, (magnitude / max) * 100)
  const unitWord = unit === 'WAR' ? 'talent swing' : 'value swing'
  return (
    <div className="tb-strip">
      <div className="tb-strip__track">
        {distribution.map((d, i) => (
          <span key={i} className="tb-strip__tick" style={{ left: `${Math.min(100, (d / max) * 100)}%` }} />
        ))}
        <span className="tb-strip__dot" style={{ left: `${dotPct}%` }} />
      </div>
      <span className="tb-strip__caption">A bigger {unitWord} than {ordinal(pctile)} percentile of trades</span>
    </div>
  )
}

function Val({ v, unit }: { v: number | null | undefined; unit: 'WAR' | '$' }) {
  if (v == null) return <span className="tb-work__val tb-work__val--zero">—</span>
  const cls = valOf(v)
  const txt = unit === 'WAR' ? `${fmtWar(v)}` : fmtDollarsM(v, true)
  return <span className={`tb-work__val tb-work__val--${cls} mono`}>{txt}</span>
}

export default function TheWork({ teams }: { teams: TeamTradeResult[] }) {
  const [show, setShow] = useState<boolean>(() => {
    try { return localStorage.getItem(STORAGE_KEY) !== '0' } catch { return true }
  })
  const toggle = () => setShow((s) => { try { localStorage.setItem(STORAGE_KEY, s ? '0' : '1') } catch { /* noop */ } ; return !s })

  const [board, setBoard] = useState<number[]>([])
  useEffect(() => {
    let cancel = false
    getTradeBoard({ limit: 200 })
      .then((items) => { if (!cancel) setBoard(items.map((t) => Math.abs(t.margin_slot)).filter((n) => Number.isFinite(n))) })
      .catch(() => { if (!cancel) setBoard([]) })
    return () => { cancel = true }
  }, [])

  const talentSwing = useMemo(
    () => Math.max(0, ...teams.map((t) => Math.abs(t.talent_delta_war ?? 0))),
    [teams],
  )

  const colStyle = { gridTemplateColumns: `minmax(0,1fr) repeat(${teams.length}, 104px) 250px` }

  return (
    <div className="tb-work">
      <button className="tb-work__toggle" onClick={toggle} aria-expanded={show}>
        <ChevronDown size={15} className={show ? 'tb-work__chev tb-work__chev--open' : 'tb-work__chev'} />
        {show ? 'Hide the work' : 'Show the work'}
      </button>

      {show && (
        <div className="tb-work__table" role="table">
          {/* header */}
          <div className="tb-work__row tb-work__row--head" role="row" style={colStyle}>
            <span className="tb-work__metric" role="columnheader">Metric</span>
            {teams.map((t) => (
              <span key={t.team_id} className="tb-work__team" role="columnheader">{getTeamAbbrev(t.team_id)}</span>
            ))}
            <span className="tb-work__ctx-head" role="columnheader">Context</span>
          </div>

          {/* Talent */}
          <div className="tb-work__row" role="row" style={colStyle}>
            <span className="tb-work__metric">
              <span className="tb-work__metric-name">Talent</span>
              <span className="tb-work__metric-cap">WAR gained or lost, next season</span>
            </span>
            {teams.map((t) => <span key={t.team_id} className="tb-work__cell"><Val v={t.talent_delta_war} unit="WAR" /></span>)}
            <span className="tb-work__ctx">
              <HistoryStrip distribution={board} magnitude={talentSwing} unit="WAR" />
            </span>
          </div>

          {/* Price vs market */}
          <div className="tb-work__row" role="row" style={colStyle}>
            <span className="tb-work__metric">
              <span className="tb-work__metric-name">
                Price vs market
                <Tooltip content="Surplus value exchanged, per year: projected worth minus contract cost, present-valued.">
                  <Info size={11} className="tb-work__info" />
                </Tooltip>
              </span>
              <span className="tb-work__metric-cap">surplus value exchanged, per year</span>
            </span>
            {teams.map((t) => <span key={t.team_id} className="tb-work__cell"><Val v={t.surplus_delta_dollars} unit="$" /></span>)}
            <span className="tb-work__ctx">
              {/* TODO(data): no served dollar-magnitude distribution — the Trade Outcomes board is WAR-slot based. */}
              <span className="tb-work__nostrip">Market-magnitude distribution not served</span>
            </span>
          </div>

          {/* Fit */}
          <div className="tb-work__row" role="row" style={colStyle}>
            <span className="tb-work__metric">
              <span className="tb-work__metric-name">
                Fit
                <Tooltip content="How incoming players slot into lineup need, from the fit model.">
                  <Info size={11} className="tb-work__info" />
                </Tooltip>
              </span>
              <span className="tb-work__metric-cap">how incoming players slot into lineup need</span>
            </span>
            {teams.map((t) => {
              const score = teamFitScore(t)
              const word = fitWord(score)
              return (
                <span key={t.team_id} className="tb-work__cell">
                  <span className="tb-work__fit">
                    <span className="tb-work__fit-word">{word}</span>
                    {score != null && <span className="tb-work__fit-num mono">{score.toFixed(2)}</span>}
                  </span>
                </span>
              )
            })}
            <span className="tb-work__ctx tb-work__ctx--sentence">
              {teams.flatMap((t) => t.fit_details).filter((f) => f.player_name).slice(0, 2)
                .map((f) => `${f.player_name} ${f.grade ? `(${f.grade})` : ''}`.trim()).join('; ') || 'No incoming skater fit to score.'}
            </span>
          </div>

          {/* Cap */}
          <div className="tb-work__row" role="row" style={colStyle}>
            <span className="tb-work__metric">
              <span className="tb-work__metric-name">
                Cap <span className="tb-work__approx mono">APPROX</span>
              </span>
              <span className="tb-work__metric-cap">projected against this season’s ceiling</span>
            </span>
            {teams.map((t) => {
              const cap = t.cap
              if (!cap) return <span key={t.team_id} className="tb-work__cell"><span className="tb-work__val tb-work__val--zero">—</span></span>
              const over = cap.over_cap === true
              const marginTxt = cap.margin != null ? fmtDollarsM(Math.abs(cap.margin)) : '—'
              return (
                <span key={t.team_id} className="tb-work__cell">
                  <span className={`tb-work__val mono ${over ? 'tb-work__val--neg' : 'tb-work__val--ink'}`}>
                    {over ? 'Over' : 'Under'} {marginTxt}
                  </span>
                </span>
              )
            })}
            <span className="tb-work__ctx tb-work__ctx--sentence">
              {teams.map((t) => {
                const c = t.cap
                if (!c) return null
                return (
                  <span key={t.team_id} className="tb-work__caparith mono">
                    {getTeamAbbrev(t.team_id)} {fmtDollarsM(c.committed_before)} → {fmtDollarsM(c.committed_after)} of {fmtDollarsM(c.ceiling)}
                  </span>
                )
              })}
            </span>
          </div>

          <p className="tb-work__foot">
            Dollar figures are{' '}
            <Tooltip content={CAP_DOLLAR_TAG + ' — present value across the remaining term in projected-cap dollars, not today’s dollars.'}>
              <span className="tb-work__foot-term">present value</span>
            </Tooltip>{' '}
            over each deal’s remaining term. The talent strip positions this trade’s swing against real
            trades from the Trade Outcomes dataset by magnitude percentile.
          </p>
        </div>
      )}
    </div>
  )
}
