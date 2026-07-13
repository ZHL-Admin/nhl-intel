import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Tooltip, SkeletonLoader } from '../common'
import MoveLedger from './MoveLedger'
import { RosterForecastRow, OffseasonTeamDetail } from '../../api/types'
import {
  fmtPoints, fmtPointsBand, fmtPointsDelta, fmtRating, fmtRank, changeWords,
} from '../../utils/forecastFormat'

const COMPONENT_LABELS: Record<string, string> = {
  play_5v5: 'Even-strength play',
  finishing: 'Finishing',
  goaltending: 'Goaltending',
  special_teams: 'Special teams',
}

/** §2.1 figure cell — label, value, one-line caption. Value color follows an optional sign class. */
function Figure({ label, value, caption, tone, tip, onClick }: {
  label: string; value: string; caption?: string; tone?: string; tip?: string; onClick?: () => void
}) {
  const labelNode = tip
    ? <Tooltip content={tip}><span className="dfig__label">{label}</span></Tooltip>
    : <span className="dfig__label">{label}</span>
  const body = (
    <>
      {labelNode}
      <span className={`dfig__value mono${tone ? ` ${tone}` : ''}`}>{value}</span>
      {caption && <span className="dfig__caption">{caption}</span>}
    </>
  )
  if (onClick) return <button type="button" className="dfig dfig--tap" onClick={onClick}>{body}</button>
  return <div className="dfig">{body}</div>
}

/** §2 — one team's summer, expanded on a wash inside the league row. Distinct white section cards:
 * the summary (figures + receipts + the Moves-logged ledger), the decisions, the holes + best fits. */
export default function TeamDossier({ row, detail, loading, error, onRetry }: {
  row: RosterForecastRow
  detail: OffseasonTeamDetail | null
  loading: boolean
  error: boolean
  onRetry: () => void
}) {
  const [ledgerOpen, setLedgerOpen] = useState(false)
  const teamId = row.team_id

  if (error) {
    return (
      <div className="dossier">
        <div className="dcard dcard--msg">
          Could not load this team.{' '}
          <button type="button" className="dcard__retry" onClick={onRetry}>Retry</button>
        </div>
      </div>
    )
  }
  if (loading || !detail) {
    return (
      <div className="dossier">
        <div className="dcard"><SkeletonLoader height={120} /></div>
        <div className="dcard"><SkeletonLoader height={90} /></div>
      </div>
    )
  }

  const f = detail.forecast
  const ins = detail.moves.filter((m) => m.move_type === 'arrival').length
  const outs = detail.moves.filter((m) => m.move_type === 'departure').length
  const fromMoves = f.points_delta ?? f.delta
  const moveTone = Math.abs(fromMoves) < 0.5 ? 'is-flat' : fromMoves > 0 ? 'is-up' : 'is-down'

  // Receipts: the generated valence lines summarizing the summer (the old Verdict prose is distributed
  // here). Reasons first; the verdict sentence backfills when the engine returns no reason lines.
  const receipts = (detail.reasons?.length ? detail.reasons : [detail.verdict]).filter(Boolean).slice(0, 3)

  // THE HOLES (degrade): the richest source (depth chart + how-they-play percentiles) is not served, so
  // surface the team's weakest base components as need proxies. TODO(data) below.
  const holes = Object.entries(detail.base_components)
    .filter(([, v]) => v != null && (v as number) < 0)
    .sort((a, b) => (a[1] as number) - (b[1] as number))
    .slice(0, 3)

  return (
    <div className="dossier">
      {/* ---- 2.1 Summary ---- */}
      <section className="dcard">
        <div className="dcard__head">
          <span className="dcard__eyebrow">The summary</span>
          <div className="dcard__links">
            <Link className="dcard__link" to={`/studio/lineups/lines?team=${teamId}`}>
              Open the projected roster in Lineup Lab <ArrowRight size={13} />
            </Link>
            <Link className="dcard__link" to={`/teams/${teamId}`}>Team profile</Link>
          </div>
        </div>

        <div className="dfigrow">
          <Figure label="Projected points"
            value={f.projected_points != null ? fmtPoints(f.projected_points) : fmtRating(f.projected_rating)}
            caption={f.points_low != null ? `80% range ${fmtPointsBand(f.points_low, f.points_high)}` : undefined}
            tip="Projected next-season standings points over 82 games, with its 80% band." />
          <Figure label="From moves"
            value={f.points_delta != null ? `${fmtPointsDelta(f.points_delta)} pts` : fmtRating(f.delta)}
            caption={changeWords(f.delta)} tone={moveTone}
            tip="Standings-points shift from this offseason's moves alone." />
          <Figure label="League rank" value={fmtRank(f.projected_rank)}
            caption={`of 32 · was ${fmtRank(f.base_rank)} last season`}
            tip="Projected league rank by projected points (1 = best)." />
          <Figure label="Moves logged" value={String(f.n_moves)}
            caption={`${ins} in · ${outs} out${f.n_moves ? ' · tap for the ledger' : ''}`}
            onClick={f.n_moves ? () => setLedgerOpen((o) => !o) : undefined}
            tip="Lineup-relevant arrivals and departures logged this offseason." />
          {/* TODO(data): effective space + its "{raw} raw · the RFA awards eat it" caption are not served. */}
          <Figure label="Effective space" value="—"
            caption="cap space after RFA awards"
            tip="Cap space after projected RFA awards and league-minimum fills. Not yet served by the forecast." />
        </div>

        {ledgerOpen && f.n_moves > 0 && (
          <div className="dcard__ledger">
            <MoveLedger moves={detail.moves} styleNote={detail.style_note}
              netWar={f.net_delta_war} netGoals={f.delta} />
          </div>
        )}

        <div className="dcard__hr" />
        <ul className="receipts">
          {receipts.map((line, i) => (
            <li key={i} className="receipt"><span className="receipt__dot" aria-hidden />{line}</li>
          ))}
        </ul>
      </section>

      {/* ---- 2.2 The decisions (degraded — no served RFA/UFA + Contract-Grader award data) ---- */}
      <section className="dcard">
        <div className="dcard__head">
          <span className="dcard__eyebrow">The decisions</span>
          <span className="dcard__attr">Projected deals served by the Contract Grader</span>
        </div>
        <div className="dtabs" role="tablist" aria-label="Decision filter">
          {['All', 'RFAs', 'UFAs'].map((t, i) => (
            <span key={t} className={`dtab${i === 0 ? ' is-active' : ''}`} aria-disabled>{t}</span>
          ))}
        </div>
        {/* TODO(data): the decisions table (RFA/UFA rows, WAR band, contract chip, projected award, and
            "The call") needs a new endpoint — projected next-deal awards, Call thresholds, and the
            two-branch (re-sign / walk) forecast deltas. Empty state until then. */}
        <p className="dcard__empty">This team's open RFA and UFA decisions, each priced against the Contract Grader's projected award, will land here.</p>
      </section>

      {/* ---- 2.3 The holes and best available fits ---- */}
      <section className="dcard">
        <div className="dholes">
          <div className="dholes__col">
            <span className="dcard__eyebrow">The holes</span>
            {holes.length ? (
              <ul className="dneeds">
                {holes.map(([key, v]) => (
                  <li key={key} className="dneed">
                    <span className="dneed__title">{COMPONENT_LABELS[key] ?? key}</span>
                    <span className="dneed__line">
                      Rates below league average this season ({fmtRating(v as number)} goals/game).
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="dcard__empty">No standout weaknesses in the team's component ratings.</p>
            )}
            {/* TODO(data): richer needs from the depth chart + how-they-play percentiles are not served;
                these are proxied from the team's base component ratings. */}
          </div>

          <div className="dholes__col">
            <span className="dcard__eyebrow">Best available fits</span>
            {/* TODO(data): the FA pool scored by Player Fit for this team (batch, cacheable nightly) is
                not served — no fit tiles until that endpoint exists. */}
            <p className="dcard__empty">The free-agent pool scored by Player Fit for this team lands here — four best fits with a grade and a one-line reason.</p>
            <Link className="dcard__link dholes__trade" to={`/studio/trades/build?team=${teamId}`}>
              Build a trade instead <ArrowRight size={13} />
            </Link>
            <span className="dholes__rationale">when the free-agent market can't fill the need.</span>
          </div>
        </div>
      </section>
    </div>
  )
}
