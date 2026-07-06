/**
 * Today (P1) — the front door at `/`. A single PageCard holding self-contained modules, each with
 * its own data call, skeleton, and empty rule. v1 uses ONLY existing endpoints (no insight feed —
 * that is v2/D18). Layout: a 12-col grid, main (cols 1-8) + rail (cols 9-12) on desktop; single
 * column on mobile in the order M1..M7. When tonight AND last night are both empty (deep offseason)
 * the offseason M5 is promoted to the top of the main column so the page never opens with a gap.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUp, ArrowDown } from 'lucide-react'
import { PageLayout, PageCard, SkeletonLoader } from '../components/common'
import GameCard from '../components/games/GameCard'
import { usePageTitle } from '../hooks/usePageTitle'
import { inPlayoffWindow, inOffseasonWindow } from '../utils/seasonal'
import { getTeamLogoUrl } from '../utils/teams'
import { getGamesByDate } from '../api/games'
import { getPowerRankings } from '../api/rankings'
import { getDeservedStandings } from '../api/rankings'
import { getPlayoffBracket } from '../api/playoffs'
import { getOffseasonBoard } from '../api/offseason'
import { TRAJECTORY_MEANINGFUL_MOVE } from '../config/metrics'
import { fmt } from '../utils/format'
import { WRITING } from '../config/writing'
import type { Game, PowerRatingRow, DeservedStandingRow, PlayoffOdds, RosterForecastRow } from '../api/types'
import './Today.css'

const isoDate = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** Section header: sentence-case region title + a quiet "See all" link to the parent surface.
 *  `mod` drives the mobile single-column ordering (M1..M7) via a per-module class. */
function Region({ mod, title, seeAll, children }: { mod: string; title: string; seeAll?: { to: string; label?: string }; children: React.ReactNode }) {
  return (
    <section className={`today-mod today-mod--${mod}`}>
      <div className="today-mod__head">
        <h2 className="page-region-title today-mod__title">{title}</h2>
        {seeAll && <Link className="today-mod__seeall" to={seeAll.to}>{seeAll.label ?? 'See all'}</Link>}
      </div>
      {children}
    </section>
  )
}

const TeamRow = ({ abbrev, teamId, children }: { abbrev?: string | null; teamId: number; children: React.ReactNode }) => (
  <Link to={`/teams/${teamId}`} className="today-row">
    {abbrev && <img className="today-row__logo" src={getTeamLogoUrl(abbrev)} alt="" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />}
    <span className="today-row__abbrev">{abbrev ?? teamId}</span>
    <span className="today-row__body">{children}</span>
  </Link>
)

// ── M1/M2: game strips (presentational; the parent owns the single fetch so it can apply the
//    offseason promotion rule without double-calling the endpoint). Each still owns its own render.
function GameStrip({ mod, title, seeAll, games, loading, scoreEmphasis }:
  { mod: string; title: string; seeAll?: { to: string }; games: Game[]; loading: boolean; scoreEmphasis?: boolean }) {
  if (!loading && games.length === 0) return null   // hidden when no games
  return (
    <Region mod={mod} title={title} seeAll={seeAll}>
      {loading
        ? <div className="today-strip"><SkeletonLoader height={72} /><SkeletonLoader height={72} /><SkeletonLoader height={72} /></div>
        : <div className={`today-strip ${scoreEmphasis ? 'today-strip--scores' : ''}`}>
            {games.map((g) => <GameCard key={g.game_id} game={g} size="compact" />)}
          </div>}
    </Region>
  )
}

// ── M3: Movers — biggest 15-day risers and fallers past the shared meaningful-move threshold.
function Movers() {
  const [rows, setRows] = useState<PowerRatingRow[] | null>(null)
  useEffect(() => { getPowerRankings().then(setRows).catch(() => setRows([])) }, [])
  if (rows === null) return <Region mod="m3" title="Moving"><SkeletonLoader height={120} /></Region>
  const moved = rows.filter((r) => r.trajectory_15d != null && Math.abs(r.trajectory_15d) > TRAJECTORY_MEANINGFUL_MOVE)
  if (moved.length === 0) return null   // hidden if nobody clears the threshold
  const risers = [...moved].filter((r) => (r.trajectory_15d ?? 0) > 0).sort((a, b) => (b.trajectory_15d ?? 0) - (a.trajectory_15d ?? 0)).slice(0, 3)
  const fallers = [...moved].filter((r) => (r.trajectory_15d ?? 0) < 0).sort((a, b) => (a.trajectory_15d ?? 0) - (b.trajectory_15d ?? 0)).slice(0, 3)
  const line = (r: PowerRatingRow) => {
    const up = (r.trajectory_15d ?? 0) > 0
    return (
      <TeamRow key={r.team_id} abbrev={r.team_abbrev} teamId={r.team_id}>
        <span className="today-row__val mono">{fmt.rating(r.total_rating)}</span>
        <span className={`today-row__delta ${up ? 'is-up' : 'is-down'}`}>
          {up ? <ArrowUp size={12} /> : <ArrowDown size={12} />}{Math.abs(r.trajectory_15d ?? 0).toFixed(2)}
        </span>
      </TeamRow>
    )
  }
  return (
    <Region mod="m3" title="Moving" seeAll={{ to: '/teams?view=power' }}>
      <div className="today-cols">
        <div><div className="today-col__head">Rising</div>{risers.map(line)}</div>
        <div><div className="today-col__head">Falling</div>{fallers.map(line)}</div>
      </div>
    </Region>
  )
}

// ── M4: Luck watch — two luckiest and two unluckiest by luck_delta (existing valence convention).
function LuckWatch() {
  const [rows, setRows] = useState<DeservedStandingRow[] | null>(null)
  useEffect(() => { getDeservedStandings().then(setRows).catch(() => setRows([])) }, [])
  if (rows === null) return <Region mod="m4" title="Luck watch"><SkeletonLoader height={120} /></Region>
  if (rows.length === 0) return null   // no rows off-season
  const sorted = [...rows].sort((a, b) => b.luck_delta - a.luck_delta)
  const pick = [...sorted.slice(0, 2), ...sorted.slice(-2)]
  const line = (r: DeservedStandingRow) => (
    <TeamRow key={r.team_id} abbrev={r.team_abbrev} teamId={r.team_id}>
      <span className="today-row__val mono">{Math.round(r.actual_points)} vs {Math.round(r.deserved_points)}</span>
      <span className="today-row__delta" style={{ color: r.luck_delta > 0 ? 'var(--color-success)' : 'var(--color-danger)' }}>
        {fmt.delta(r.luck_delta)}
      </span>
    </TeamRow>
  )
  return (
    <Region mod="m4" title="Luck watch" seeAll={{ to: '/teams?view=deserved' }}>
      <div className="today-list">{pick.map(line)}</div>
    </Region>
  )
}

// ── M5: Seasonal stakes — playoff title odds (D20 window) or offseason WAR gainers (Jul–Sep).
function SeasonalStakes({ variant }: { variant: 'playoff' | 'offseason' }) {
  const [odds, setOdds] = useState<PlayoffOdds[] | null>(null)
  const [board, setBoard] = useState<RosterForecastRow[] | null>(null)
  useEffect(() => {
    if (variant === 'playoff') getPlayoffBracket().then((b) => setOdds(b.odds)).catch(() => setOdds([]))
    else getOffseasonBoard().then(setBoard).catch(() => setBoard([]))
  }, [variant])

  if (variant === 'playoff') {
    if (odds === null) return <Region mod="m5" title="The race"><SkeletonLoader height={120} /></Region>
    if (odds.length === 0) return null
    const top = [...odds].sort((a, b) => b.win_cup - a.win_cup).slice(0, 4)
    return (
      <Region mod="m5" title="The race" seeAll={{ to: '/playoffs' }}>
        <div className="today-list">
          {top.map((o) => (
            <TeamRow key={o.abbrev} abbrev={o.abbrev} teamId={o.team_id ?? 0}>
              <span className="today-row__val mono">{fmt.prob(o.win_cup)}</span>
              <span className="today-row__muted">to win it all</span>
            </TeamRow>
          ))}
        </div>
      </Region>
    )
  }

  if (board === null) return <Region mod="m5" title="Offseason board"><SkeletonLoader height={120} /></Region>
  if (board.length === 0) return null
  const gainers = [...board].sort((a, b) => b.net_delta_war - a.net_delta_war).slice(0, 3)
  return (
    <Region mod="m5" title="Offseason board" seeAll={{ to: '/studio/offseason' }}>
      <div className="today-list">
        {gainers.map((r) => (
          <TeamRow key={r.team_id} abbrev={r.team_abbrev} teamId={r.team_id}>
            <span className="today-row__val mono" style={{ color: r.net_delta_war >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }}>
              {fmt.war(r.net_delta_war)} WAR
            </span>
            <span className="today-row__muted">projected</span>
          </TeamRow>
        ))}
      </div>
    </Region>
  )
}

// ── M6: From the studio — static shortcut cards. Blurbs are the exact §5.4 strings.
const STUDIO_CARDS = [
  { to: '/studio/trades', label: 'Trades', blurb: 'Build a deal, find a fit, or study history’s verdicts.' },
  { to: '/studio/lineups', label: 'Lineups', blurb: 'Project lines before they take a shift.' },
  { to: '/studio/contracts', label: 'Contracts', blurb: 'Grade any deal against the aging curve and the market.' },
]
function FromTheStudio() {
  return (
    <Region mod="m6" title="From the studio" seeAll={{ to: '/studio' }}>
      <div className="today-shortcuts">
        {STUDIO_CARDS.map((c) => (
          <Link key={c.to} to={c.to} className="today-shortcut">
            <span className="today-shortcut__label">{c.label}</span>
            <span className="today-shortcut__blurb">{c.blurb}</span>
          </Link>
        ))}
      </div>
    </Region>
  )
}

// ── M7: Writing — latest one or two posts from the manifest. Hidden while empty (owner-supplied
//    markdown not yet added). The `/learn/writing` route lands in P4; until then titles are plain.
function Writing() {
  const posts = WRITING.slice(0, 2)
  if (posts.length === 0) return null
  return (
    <Region mod="m7" title="Writing" seeAll={{ to: '/learn/writing' }}>
      <div className="today-list">
        {posts.map((p) => (
          <div key={p.slug} className="today-post">
            <span className="today-post__title">{p.title}</span>
            <span className="today-row__muted">{new Date(`${p.date}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
          </div>
        ))}
      </div>
    </Region>
  )
}

export default function Today() {
  usePageTitle('Today')
  const now = new Date()
  const longDate = now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1)

  const [slate, setSlate] = useState<Game[] | null>(null)
  const [lastNight, setLastNight] = useState<Game[] | null>(null)
  useEffect(() => {
    getGamesByDate(isoDate(now)).then(setSlate).catch(() => setSlate([]))
    getGamesByDate(isoDate(yesterday)).then(setLastNight).catch(() => setLastNight([]))
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const seasonalVariant: 'playoff' | 'offseason' | null =
    inPlayoffWindow() ? 'playoff' : inOffseasonWindow() ? 'offseason' : null
  const gamesLoaded = slate !== null && lastNight !== null
  const bothEmpty = gamesLoaded && (slate?.length ?? 0) === 0 && (lastNight?.length ?? 0) === 0
  const promoteOffseason = bothEmpty && seasonalVariant === 'offseason'

  return (
    <PageLayout>
      <PageCard title="Today" subtitle={longDate} bodyClassName="today">
        <div className="today__main">
          {promoteOffseason && <SeasonalStakes variant="offseason" />}
          <GameStrip mod="m1" title="Tonight" seeAll={{ to: '/games' }} games={slate ?? []} loading={slate === null} />
          <GameStrip mod="m2" title="Last night" seeAll={{ to: '/games' }} games={lastNight ?? []} loading={lastNight === null} scoreEmphasis />
          <Movers />
        </div>
        <div className="today__rail">
          <LuckWatch />
          {seasonalVariant && !promoteOffseason && <SeasonalStakes variant={seasonalVariant} />}
          <Writing />
          <FromTheStudio />
        </div>
      </PageCard>
    </PageLayout>
  )
}
