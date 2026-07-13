/**
 * Today (Home v3) — the front door at `/`. Offseason layout per instructions/19-home-v3-approved.md:
 * a 00c context strip (no Sheet title), then the single grid (main column + 324px rail), then the
 * full-width Studio band; the footer is the shared canvas footer from PageLayout.
 *
 * The single grid is the page's structural law: `minmax(0,1fr) 324px` is the only column split on the
 * page — every vertical seam is this grid's seam. Do not introduce a second column structure.
 *
 * Data: ships the OFFSEASON branch only. The Lead is phase-aware (config/leadTemplates). The Ledger
 * and Still-available modules read the /moves and /free-agents feeds — both stubbed empty until the
 * nightly DAG/model writes them, so they render honest empty states by default. Grades are never
 * computed client-side. Review-only: DEV + `?fixtures` renders the whole page from local fixtures.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { PageLayout, ContextStrip, Panel } from '../components/common'
import { usePageTitle } from '../hooks/usePageTitle'
import { getTeamColor } from '../utils/teams'
import { getGameDates } from '../api/games'
import { getOffseasonBoard } from '../api/offseason'
import { getPowerRankings, getDeservedStandings } from '../api/rankings'
import { getMoves } from '../api/moves'
import { getFreeAgents } from '../api/freeAgents'
import { selectLead } from '../config/leadTemplates'
import { resolveFeatured } from '../config/featured'
import { isFixtureMode } from '../utils/fixtures'
import { FIXTURE_MOVES, FIXTURE_FREE_AGENTS, FIXTURE_OFFSEASON_BOARD, FIXTURE_POWER } from '../config/homeFixtures'
import type { RosterForecastRow, PowerRatingRow, DeservedStandingRow, MoveRow, MovesPage, FreeAgentRow } from '../api/types'
import './Today.css'

const isoDate = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const DAY_MS = 86_400_000
const money = (aav: number) => `$${(aav / 1e6).toFixed(1)}M`

/** Phase line for the context strip: "Free agency · Day {n} · {d} days to opening night".
 *  Day count is from July 1 of the current year; days-to-opening is the first scheduled game date. */
function usePhaseLine(): string {
  const [line, setLine] = useState('Free agency')
  useEffect(() => {
    const now = new Date()
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
    const jul1 = new Date(now.getFullYear(), 6, 1).getTime()
    const dayN = Math.max(1, Math.floor((startOfToday - jul1) / DAY_MS) + 1)
    getGameDates(isoDate(now)).then((dates) => {
      const opening = dates.map((d) => d.date).filter((d) => d >= isoDate(now)).sort()[0]
      const days = opening ? Math.round((new Date(`${opening}T00:00:00`).getTime() - startOfToday) / DAY_MS) : null
      setLine(`Free agency · Day ${dayN}${days != null ? ` · ${days} days to opening night` : ''}`)
    }).catch(() => setLine(`Free agency · Day ${dayN}`))
  }, [])
  return line
}
// TODO(season): build + approve the season branch of this page; it currently ships offseason only.

// ── The Lead (phase-aware) ────────────────────────────────────────────────────
function TheLead() {
  const [power, setPower] = useState<PowerRatingRow[]>([])
  const [deserved, setDeserved] = useState<DeservedStandingRow[]>([])
  const [board, setBoard] = useState<RosterForecastRow[]>([])
  const [moves, setMoves] = useState<MoveRow[]>([])
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let active = true
    if (isFixtureMode()) {
      setPower(FIXTURE_POWER); setBoard(FIXTURE_OFFSEASON_BOARD); setMoves(FIXTURE_MOVES); setReady(true)
      return
    }
    Promise.all([
      getPowerRankings().catch(() => []),
      getDeservedStandings().catch(() => []),
      getOffseasonBoard().catch(() => []),
      getMoves({ limit: 20 }).then((p) => p.items).catch(() => [] as MoveRow[]),
    ]).then(([p, d, o, m]) => { if (active) { setPower(p); setDeserved(d); setBoard(o); setMoves(m); setReady(true) } })
    return () => { active = false }
  }, [])
  if (!ready) return <section className="home-lead"><div className="home-skel" style={{ height: 128 }} /></section>
  const lead = selectLead({ phase: 'offseason', slate: [], lastNight: [], power, deserved, offseason: board, moves })
  if (!lead) return null
  return (
    <section className="home-lead">
      <p className="home-eyebrow">The lead</p>
      <h2 className="home-lead__headline">{lead.headline}</h2>
      <p className="home-lead__dek">{lead.dek}</p>
      <Link className="home-link" to={lead.link.to}>{lead.link.label}</Link>
    </section>
  )
}

// ── The Ledger ────────────────────────────────────────────────────────────────
function LedgerRow({ m }: { m: MoveRow }) {
  const navigate = useNavigate()
  const p = m.players[0]
  // Signings/extensions open the (prefilled) Contract Grader; trades open the trade dossier.
  const to = m.type === 'trade' ? `/studio/trades/history/trade/${m.id}` : `/studio/contracts?player=${p?.player_id ?? ''}`
  // "To" is where the headline player went (destination = teams[0]); the edge winner is the verdict.
  const toTeam = m.teams[0]
  const dateLabel = new Date(`${m.date}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()
  const terms = m.type === 'trade'
    ? `Trade · ${m.teams.filter((t) => t !== toTeam)[0] ?? m.teams.join('–')}`
    : m.terms ? `${m.terms.years} yr · ${money(m.terms.aav)}` : ''
  return (
    <div
      className="ledger__row"
      role="link"
      tabIndex={0}
      onClick={() => navigate(to)}
      onKeyDown={(e) => { if (e.key === 'Enter') navigate(to) }}
    >
      <span className="ledger__date mono">{dateLabel}</span>
      <span className="ledger__player">
        <Link className="ledger__name" to={`/players/${p?.player_id ?? ''}`} onClick={(e) => e.stopPropagation()}>{p?.name ?? '—'}</Link>
        {p?.pos && <span className="ledger__pos">{p.pos}</span>}
      </span>
      <span className="ledger__to">
        <span className="home-dot" style={{ background: getTeamColor(toTeam ?? '') }} />
        <span className="ledger__abbrev">{toTeam}</span>
      </span>
      <span className={`ledger__terms ${m.type === 'trade' ? 'is-trade' : 'num'}`}>{terms}</span>
      <span className="ledger__verdict">
        {m.type === 'trade'
          ? (m.verdict?.edge ? <span className="ledger__edge">Edge {m.verdict.edge}</span> : null)
          : (m.verdict?.grade ? <span className="ledger__grade">{m.verdict.grade}</span> : null)}
      </span>
    </div>
  )
}

function TheLedger() {
  const [page, setPage] = useState<MovesPage | null>(null)
  useEffect(() => {
    if (isFixtureMode()) { setPage({ items: FIXTURE_MOVES, total: FIXTURE_MOVES.length }); return }
    getMoves({ limit: 8 }).then(setPage).catch(() => setPage({ items: [], total: 0 }))
  }, [])
  const rows = page?.items.slice(0, 8) ?? []
  return (
    <section className="home-ledger">
      <div className="home-mod-head">
        <p className="home-eyebrow">Recent moves</p>
      </div>
      {page === null ? (
        <div className="home-skel" style={{ height: 180 }} />
      ) : rows.length === 0 ? (
        <p className="home-empty">Quiet week. The ledger fills as moves land.</p>
      ) : (
        <div className="ledger">
          <div className="ledger__head">
            <span>Date</span><span>Player</span><span>To</span><span>Terms</span><span className="ledger__verdict-h">Verdict</span>
          </div>
          {rows.map((m) => <LedgerRow key={m.id} m={m} />)}
          <div className="ledger__foot">
            <Link className="home-link" to="/studio/offseason">All moves this offseason <ArrowUpRight size={13} /></Link>
          </div>
        </div>
      )}
    </section>
  )
}

// ── Rail · Offseason board (movers) ───────────────────────────────────────────
const MOVER_DOMAIN = 4.0 // shared ±WAR domain across all rows

function MoversPanel() {
  const [board, setBoard] = useState<RosterForecastRow[] | null>(null)
  useEffect(() => {
    if (isFixtureMode()) { setBoard(FIXTURE_OFFSEASON_BOARD); return }
    getOffseasonBoard().then(setBoard).catch(() => setBoard([]))
  }, [])
  const rows = (() => {
    if (!board) return null
    // Top 3 and bottom 3 teams by net WAR change from the offseason board.
    const moved = board.filter((r) => !r.negligible && r.net_delta_war != null)
    const risers = [...moved].filter((r) => r.net_delta_war > 0).sort((a, b) => b.net_delta_war - a.net_delta_war).slice(0, 3)
    // 3 worst, displayed least-bad → worst (third-worst on top, the worst at the bottom).
    const fallers = [...moved].filter((r) => r.net_delta_war < 0).sort((a, b) => a.net_delta_war - b.net_delta_war).slice(0, 3).reverse()
    return [...risers, ...fallers]
  })()
  return (
    <Panel title="Offseason board" action={<Link className="home-link home-link--quiet" to="/studio/offseason">Full board</Link>}>
      {rows === null ? (
        <div className="home-skel" style={{ height: 150 }} />
      ) : rows.length === 0 ? (
        <p className="home-empty">No meaningful movement yet.</p>
      ) : (
        <div className="home-movers">
          {rows.map((r) => {
            const v = Math.max(-MOVER_DOMAIN, Math.min(MOVER_DOMAIN, r.net_delta_war))
            const up = v > 0
            const pct = (Math.abs(v) / MOVER_DOMAIN) * 50 // half-track
            return (
              <Link key={r.team_id} to={`/teams/${r.team_id}`} className="home-mover">
                <span className="home-mover__label">
                  <span className="home-dot" style={{ background: getTeamColor(r.team_abbrev ?? '') }} />
                  <span className="home-mover__abbrev">{r.team_abbrev}</span>
                </span>
                <span className="home-mover__track" aria-hidden>
                  <span className="home-mover__zero" />
                  <span
                    className={`home-mover__fill ${up ? 'is-up' : 'is-down'}`}
                    style={up ? { left: '50%', width: `${pct}%` } : { right: '50%', width: `${pct}%` }}
                  />
                </span>
                <span className={`home-mover__val num ${up ? 'is-up' : 'is-down'}`}>{v > 0 ? '+' : ''}{v.toFixed(1)}</span>
              </Link>
            )
          })}
          {/* TODO(data): the doc calls for a dashed extension per row for the unresolved-forecast
              portion (open roster spots) + a "Dashed = unresolved spots" legend. No field on
              RosterForecastRow isolates the unresolved WAR, so bars render solid only for now. */}
        </div>
      )}
    </Panel>
  )
}

// ── Rail · Still available ────────────────────────────────────────────────────
function StillAvailablePanel() {
  const [rows, setRows] = useState<FreeAgentRow[] | null>(null)
  useEffect(() => {
    if (isFixtureMode()) { setRows(FIXTURE_FREE_AGENTS); return }
    getFreeAgents({ limit: 5 }).then(setRows).catch(() => setRows([]))
  }, [])
  const top = rows ? rows.slice(0, 5) : null
  return (
    <Panel title="Still available" action={<Link className="home-link home-link--quiet" to="/players">All free agents</Link>}>
      {top === null ? (
        <div className="home-skel" style={{ height: 120 }} />
      ) : top.length === 0 ? (
        <p className="home-empty">The free-agent board opens when the pool feed lands.</p>
      ) : (
        <div className="home-fa">
          {top.map((r) => (
            <Link key={r.player_id} to={`/players/${r.player_id}`} className="home-fa__row">
              <span className="home-fa__name">
                {r.name}
                <span className="home-fa__meta">{[r.status, r.pos, r.age].filter((x) => x != null && x !== '').join(' · ')}</span>
              </span>
              {r.projected_award?.aav != null ? (
                <span className="home-fa__val num">proj {money(r.projected_award.aav)}</span>
              ) : r.projected_war != null ? (
                <span className="home-fa__val num">
                  {(r.projected_war >= 0 ? '+' : '') + r.projected_war.toFixed(1)} WAR
                  {r.war_sd != null}
                </span>
              ) : null}
            </Link>
          ))}
        </div>
      )}
    </Panel>
  )
}

// ── Rail · Featured ───────────────────────────────────────────────────────────
function FeaturedPanel() {
  const f = resolveFeatured()
  return (
    <Panel>
      <p className="home-eyebrow">{f.eyebrow}</p>
      <h3 className="home-featured__title">{f.title}</h3>
      <p className="home-featured__dek">{f.dek}</p>
      <Link className="home-link" to={f.to}>{f.linkLabel} <ArrowUpRight size={13} /></Link>
    </Panel>
  )
}

// ── Studio band ───────────────────────────────────────────────────────────────
// Offseason pin set (a config array so the season state can rotate it): Contracts, Trades, Lineups.
const STUDIO_PINS = [
  { to: '/studio/contracts', name: 'Contracts', dek: 'Grade any deal against the aging curve and the market.', contract: 'player + terms → grade' },
  { to: '/studio/trades', name: 'Trades', dek: 'Build a deal, find a fit, weigh the tilt.', contract: 'assets ⇄ assets → verdict' },
  { to: '/studio/lineups', name: 'Lineups', dek: 'Project lines before they take a shift.', contract: 'roster → projected WAR' },
]
function StudioBand() {
  return (
    <section className="home-studio">
      <div className="home-mod-head">
        <p className="home-eyebrow">From the Studio</p>
        <Link className="home-link home-link--quiet" to="/studio">All tools</Link>
      </div>
      <div className="home-studio__grid">
        {STUDIO_PINS.map((p) => (
          <Link key={p.to} to={p.to} className="home-studio__cell">
            <span className="home-studio__name">{p.name}</span>
            <span className="home-studio__dek">{p.dek}</span>
            <span className="home-studio__contract mono">{p.contract}</span>
          </Link>
        ))}
      </div>
    </section>
  )
}

export default function Today() {
  usePageTitle('Today')
  const now = new Date()
  const longDate = now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
  const line = usePhaseLine()

  return (
    <PageLayout>
      <ContextStrip primary={longDate} secondary={line} />
      <div className="home__grid">
        <div className="home__main">
          <TheLead />
          <div className="home__divider" />
          <TheLedger />
        </div>
        <aside className="home__rail">
          <MoversPanel />
          <StillAvailablePanel />
          <FeaturedPanel />
        </aside>
      </div>
      <StudioBand />
    </PageLayout>
  )
}
