import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { PageLayout, PageCard, SkeletonLoader, PlayerAvatar, RailProvider, Rail, Note, Ref, Tile } from '../components/common'
import { gameButtonProps } from '../components/common/GameLink'
import Tabs from '../components/common/Tabs'
import { LineSwapWidget } from '../components/common'
import LineBoard from '../components/teams/LineBoard'
import DepthChart from '../components/teams/DepthChart'
import LeagueDistributionRow from '../components/teams/LeagueDistributionRow'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine, ResponsiveContainer,
  Tooltip as RechartsTooltip,
} from 'recharts'
import { getTeamDetail, getTeamTrends, getTeamRoster, getTeamStreak, getStandings, getTeamIdentity } from '../api/teams'
import { getPowerRankings, getValueRankings } from '../api/rankings'
import { getTeamGames } from '../api/games'
import type {
  TeamDetail, TeamTrends, TeamRoster, Game, StreakCard, PowerRatingRow, StandingsRow,
  TeamIdentity, ValueRankingRow, RosterPlayer,
} from '../api/types'
import { RATINGS_COMPONENTS, FINGERPRINT_GROUPS } from '../config/metrics'
import { usePageTitle } from '../hooks/usePageTitle'
import { getTeamLogoUrl, getTeamName, getTeamColor, formatDateForAPI, formatTOI, setTeamPrimaryColor, clearTeamPrimaryColor } from '../utils/teams'
import { ordinal } from '../utils/format'
import { rankColor } from '../utils/rank'
import './TeamProfile.css'

/** Top three per division clinch; 4th and below chase the conference wild cards. */
const PLAYOFF_CUT = 3

/* Legacy tab query values 301 to the four v2 tabs (Identity → Overview, Lines → Roster, etc.). */
const TAB_ALIASES: Record<string, string> = {
  identity: 'overview',
  'performance / trends': 'performance',
  trends: 'performance',
  lines: 'roster',
  'depth chart': 'roster',
  depth: 'roster',
}
const TABS = ['overview', 'performance', 'roster', 'games'] as const

/** Player value-rule color for a WAR readout: blue at/above replacement, red below. */
const warColor = (w: number) => (w >= 0 ? 'var(--color-data-positive)' : 'var(--color-data-negative)')
const fmtWar = (w: number) => `${w >= 0 ? '+' : ''}${w.toFixed(1)}`
const fmtSigned = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}`

function TeamProfile() {
  const { teamId } = useParams<{ teamId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const rawTab = searchParams.get('tab') || 'overview'
  const currentTab = (TAB_ALIASES[rawTab.toLowerCase()] ?? rawTab).toLowerCase()
  const normalizedTab = (TABS as readonly string[]).includes(currentTab) ? currentTab : 'overview'
  // Lens lands Roster on the Lines view when the legacy ?tab=lines URL is used.
  const initialRosterLens = rawTab.toLowerCase() === 'lines' ? 'lines' : 'depth'

  const [teamDetail, setTeamDetail] = useState<TeamDetail | null>(null)
  const [teamTrends, setTeamTrends] = useState<TeamTrends | null>(null)
  const [teamRoster, setTeamRoster] = useState<TeamRoster | null>(null)
  const [upcomingGame, setUpcomingGame] = useState<Game | null>(null)
  const [recentGames, setRecentGames] = useState<Game[]>([])
  const [streakCard, setStreakCard] = useState<StreakCard | null>(null)
  const [power, setPower] = useState<{ row: PowerRatingRow; rank: number; n: number } | null>(null)
  const [standings, setStandings] = useState<StandingsRow[]>([])
  const [identity, setIdentity] = useState<TeamIdentity | null>(null)
  const [skaterValues, setSkaterValues] = useState<ValueRankingRow[]>([])
  const [goalieValues, setGoalieValues] = useState<ValueRankingRow[]>([])

  usePageTitle(teamDetail ? getTeamName(teamDetail.team_abbrev) : undefined)

  const [loading, setLoading] = useState(true)
  const [detailError, setDetailError] = useState<string | null>(null)

  useEffect(() => {
    if (!teamId) return
    const id = parseInt(teamId)
    const fetchData = async () => {
      setLoading(true)
      setDetailError(null)
      try {
        const detail = await getTeamDetail(id)
        setTeamDetail(detail)
        setTeamPrimaryColor(getTeamColor(detail.team_abbrev))
      } catch (err) {
        console.error('Error fetching team detail:', err)
        setDetailError('Failed to load team details.')
      }
      getTeamTrends(id).then(setTeamTrends).catch(() => {})
      getTeamRoster(id).then(setTeamRoster).catch(() => {})
      getTeamIdentity(id).then(setIdentity).catch(() => { /* How they play hides */ })

      try {
        const today = new Date(); const nextWeek = new Date(); nextWeek.setDate(today.getDate() + 7)
        const games = await getTeamGames(id, formatDateForAPI(today), formatDateForAPI(nextWeek))
        const nextGame = games.find((g) => g.is_preview)
        if (nextGame) setUpcomingGame(nextGame)
      } catch { /* not critical */ }

      try {
        const today = new Date(); const past = new Date(); past.setDate(today.getDate() - 120)
        const games = await getTeamGames(id, formatDateForAPI(past), formatDateForAPI(today))
        setRecentGames(games
          .filter((g) => !g.is_preview && g.home_score != null && g.away_score != null)
          .sort((a, b) => b.game_date.localeCompare(a.game_date)))
      } catch { /* results empty */ }

      setLoading(false)
    }
    fetchData()
    return () => { clearTeamPrimaryColor() }
  }, [teamId])

  useEffect(() => {
    if (!teamId) return
    let active = true
    setStreakCard(null)
    getTeamStreak(parseInt(teamId), 10).then((c) => active && setStreakCard(c)).catch(() => {})
    return () => { active = false }
  }, [teamId])

  useEffect(() => {
    if (!teamId) return
    let active = true
    setPower(null)
    getPowerRankings().then((rows) => {
      if (!active) return
      const idx = rows.findIndex((r) => r.team_id === parseInt(teamId))
      if (idx >= 0) setPower({ row: rows[idx], rank: idx + 1, n: rows.length })
    }).catch(() => {})
    return () => { active = false }
  }, [teamId])

  useEffect(() => {
    let active = true
    setStandings([])
    getStandings().then((rows) => active && setStandings(rows)).catch(() => {})
    return () => { active = false }
  }, [teamId])

  // Value rankings (WAR) drive Who drives it, Roster WAR, and the goalie table. League lists,
  // filtered to this team by abbrev.
  useEffect(() => {
    let active = true
    setSkaterValues([]); setGoalieValues([])
    getValueRankings('skaters', 'ALL', undefined, 300).then((r) => active && setSkaterValues(r)).catch(() => {})
    getValueRankings('goalies', 'ALL', undefined, 120).then((r) => active && setGoalieValues(r)).catch(() => {})
    return () => { active = false }
  }, [teamId])

  const handleTabChange = (tab: string) => setSearchParams({ tab })

  if (loading) {
    return (
      <PageLayout>
        <PageCard title="Team">
          <SkeletonLoader height={120} />
          <div style={{ height: 'var(--space-8)' }} />
          <SkeletonLoader height={300} />
        </PageCard>
      </PageLayout>
    )
  }

  if (detailError || !teamDetail) {
    return (
      <PageLayout>
        <PageCard title="Team">
          <div className="team-profile__error">
            <p className="team-profile__error-message">{detailError || 'Team not found'}</p>
            <button onClick={() => window.location.reload()} className="btn btn--secondary">Retry</button>
          </div>
        </PageCard>
      </PageLayout>
    )
  }

  const teamColor = getTeamColor(teamDetail.team_abbrev)
  const teamFullName = getTeamName(teamDetail.team_abbrev)
  const leagueSize = power?.n ?? (standings.length || 32)
  const seasonLabel = String(power?.row.season ?? teamDetail.season)
  const teamSkaters = skaterValues.filter((r) => r.team_abbrev === teamDetail.team_abbrev)
  const teamGoalies = goalieValues.filter((r) => r.team_abbrev === teamDetail.team_abbrev)

  return (
    <PageLayout>
      <PageCard
        header={<TeamMasthead t={teamDetail} teamColor={teamColor} teamFullName={teamFullName}
          power={power} standings={standings} seasonLabel={seasonLabel} />}
        controls={
          <Tabs
            options={[
              { value: 'overview', label: 'Overview' },
              { value: 'performance', label: 'Performance' },
              { value: 'roster', label: 'Roster' },
              { value: 'games', label: 'Games' },
            ]}
            value={normalizedTab}
            onChange={handleTabChange}
          />
        }
      >
        <RailProvider>
          <div className="dossier">
            <div className="dossier__main">
              {normalizedTab === 'overview' && teamId && (
                <OverviewTab t={teamDetail} teamColor={teamColor} streakCard={streakCard} power={power}
                  standings={standings} trends={teamTrends} identity={identity} teamSkaters={teamSkaters}
                  teamGoalies={teamGoalies} roster={teamRoster} leagueSize={leagueSize}
                  upcomingGame={upcomingGame} seasonLabel={seasonLabel} teamId={parseInt(teamId)} navigate={navigate} />
              )}
              {normalizedTab === 'performance' && teamId && (
                <PerformanceTab teamColor={teamColor} power={power} trends={teamTrends}
                  teamGoalies={teamGoalies} roster={teamRoster} leagueSize={leagueSize} />
              )}
              {normalizedTab === 'roster' && teamId && (
                <RosterTab teamId={parseInt(teamId)} teamAbbrev={teamDetail.team_abbrev}
                  teamSkaters={teamSkaters} teamGoalies={teamGoalies} initialLens={initialRosterLens} />
              )}
              {normalizedTab === 'games' && teamId && (
                <GamesTab t={teamDetail} upcomingGame={upcomingGame} recentGames={recentGames}
                  teamId={parseInt(teamId)} navigate={navigate} />
              )}
            </div>
            <Rail>
              <Note n={1}>The power rating is the team's strength in net goals per game vs. a league-average opponent, adjusted for score state and schedule.</Note>
              <Note n={2}>Each distribution row places all 32 teams as ticks at their league percentile for that metric; the ink dot is this team and the printed value is its league rank.</Note>
              <Note n={3}>WAR (wins above replacement) rolls a player's on-ice value into one cross-position number vs. a freely available replacement.</Note>
              <Note n={4} italic>Line chemistry projects a unit's expected xGF% from how its members have driven play together and apart — swapping a player re-projects the line.</Note>
            </Rail>
          </div>
        </RailProvider>
      </PageCard>
    </PageLayout>
  )
}

/* ============================================================================ Header (§1) */
function TeamMasthead({ t, teamColor, teamFullName, power, standings, seasonLabel }: {
  t: TeamDetail; teamColor: string; teamFullName: string
  power: { row: PowerRatingRow; rank: number; n: number } | null
  standings: StandingsRow[]; seasonLabel: string
}) {
  const meta = [t.division, t.conference, `${t.wins}-${t.losses}-${t.otl}`, `${t.points} PTS`,
    t.division_rank != null ? `${ordinal(t.division_rank)} in division` : null].filter(Boolean).join(' · ')

  // After-season stakes: games back of the division cut, from live standings.
  let stakes = power ? `${ordinal(power.rank)} of ${power.n}` : null
  const me = standings.find((s) => s.team_abbrev === t.team_abbrev)
  if (me && t.division) {
    const cutTeam = standings.find((s) => s.division === t.division && s.division_rank === PLAYOFF_CUT)
    if (cutTeam && (me.division_rank ?? 99) > PLAYOFF_CUT) {
      const back = cutTeam.points - me.points
      if (back > 0 && stakes) stakes += ` · ${back} back of the cut`
    }
  }

  return (
    <div className="tm-hd">
      <div className="tm-hd__left">
        <img src={getTeamLogoUrl(t.team_abbrev)} alt={teamFullName} className="tm-hd__logo" />
        <div className="tm-hd__id">
          <h1 className="tm-hd__name">{teamFullName}</h1>
          <div className="tm-hd__meta">
            <span className="tm-hd__dot" style={{ background: teamColor }} />
            {meta}
          </div>
          {/* TODO(data): cap space / committed / picks not served by team endpoints — cap line hidden.
              Wire from an offseason team-cap endpoint (space, committed, pick count) when available. */}
        </div>
      </div>
      {power && (
        <div className="tm-hd__right">
          <p className="tm-hd__eyebrow">Power rating · {seasonLabel}</p>
          <div className="tm-hd__rating">{fmtSigned(power.row.total_rating)}</div>
          {stakes && <p className="tm-hd__stakes">{stakes}
            {/* TODO(data): in-season "Playoff odds N%" — no make-playoffs field on the odds endpoint. */}
          </p>}
          {power.row.rating_se != null && <ConfidenceBand se={power.row.rating_se} />}
        </div>
      )}
    </div>
  )
}

/** 84px micro confidence band: ±1 sd of the rating around its point (fixed ±0.5 gpg visual scale). */
function ConfidenceBand({ se }: { se: number }) {
  const scale = 0.5
  const half = Math.min(50, (se / scale) * 50)
  return (
    <span className="tm-hd__conf" title={`± ${se.toFixed(2)} net goals/gm (1 sd)`}>
      <span className="tm-hd__conf-band" style={{ left: `${50 - half}%`, width: `${half * 2}%` }} />
      <span className="tm-hd__conf-mark" />
    </span>
  )
}

/* ============================================================================ Small helpers */
function Figure({ label, value, rank, leagueSize }: { label: string; value: string; rank: number | null; leagueSize: number }) {
  return (
    <div className="tp-fig">
      <div className="tp-fig__val">{value}</div>
      <div className="tp-fig__label">{label}</div>
      {rank != null && <div className="tp-fig__rank" style={{ color: rankColor(rank, leagueSize) }}>{ordinal(rank)}</div>}
    </div>
  )
}

/** Rolling form chart — reused by Overview (compact) and Performance (full). Proxy series: rolling
 *  xGF% (0..1) with a 50% reference; blue above / red below. */
function FormChart({ trends, height, teamColor }: { trends: TeamTrends | null; height: number; teamColor: string }) {
  const data = trends?.xgf_pct_10gp?.map((pt) => ({
    date: new Date(pt.game_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    v: pt.value * 100,
  })) ?? []
  if (data.length === 0) return <p className="tp-empty">Not enough games to chart form yet.</p>
  const tip = { background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', fontSize: 11 }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
        <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" />
        <XAxis dataKey="date" stroke="var(--color-border)" tick={{ fontSize: 11, fill: 'var(--color-text-muted)' }} minTickGap={28} />
        <YAxis domain={[35, 65]} ticks={[35, 50, 65]} stroke="var(--color-border)" tick={{ fontSize: 11, fill: 'var(--color-text-muted)' }} />
        <RechartsTooltip contentStyle={tip} formatter={(v: any) => [`${Number(v).toFixed(1)}%`, 'Rolling xGF%']} />
        <ReferenceLine y={50} stroke="var(--color-border-strong)" />
        <Line type="monotone" dataKey="v" stroke={teamColor} strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

/* ============================================================================ Overview tab (§3) */
function OverviewTab({ t, teamColor, streakCard, power, standings, trends, identity, teamSkaters, teamGoalies, roster, leagueSize, upcomingGame, seasonLabel, teamId, navigate }: {
  t: TeamDetail; teamColor: string; streakCard: StreakCard | null
  power: { row: PowerRatingRow; rank: number; n: number } | null
  standings: StandingsRow[]; trends: TeamTrends | null; identity: TeamIdentity | null
  teamSkaters: ValueRankingRow[]; teamGoalies: ValueRankingRow[]; roster: TeamRoster | null
  leagueSize: number; upcomingGame: Game | null; seasonLabel: string; teamId: number; navigate: (p: string) => void
}) {
  const netRating = power?.row.total_rating ?? null
  const pointsRank = useMemo(() => {
    if (!standings.length) return null
    const sorted = [...standings].sort((a, b) => b.points - a.points)
    const i = sorted.findIndex((s) => s.team_abbrev === t.team_abbrev)
    return i >= 0 ? i + 1 : null
  }, [standings, t.team_abbrev])

  const gp = Math.max(1, t.games_played)
  const xgfPct = t.xgf_per60 + t.xga_per60 > 0 ? (t.xgf_per60 / (t.xgf_per60 + t.xga_per60)) * 100 : null
  const figures: { label: string; value: string; rank: number | null }[] = [
    { label: 'PTS', value: String(t.points), rank: pointsRank },
    { label: 'GF/GP', value: (t.total_goals_for / gp).toFixed(2), rank: t.gf_per_gp_rank },
    { label: 'GA/GP', value: (t.total_goals_against / gp).toFixed(2), rank: t.ga_per_gp_rank },
    { label: 'xGF%', value: xgfPct != null ? `${xgfPct.toFixed(1)}%` : '—', rank: t.xgf_pct_rank },
    { label: 'HDCA/60', value: t.hdca_per60.toFixed(1), rank: t.hdca_per60_rank },
    // TODO(data): PP% not served on TeamDetail; CF% substituted to keep six figures. Swap when served.
    { label: 'CF%', value: `${(t.cf_pct * 100).toFixed(1)}%`, rank: t.cf_pct_rank },
  ]

  return (
    <div className="tp-stack">
      {/* 3.1 Verdict */}
      <blockquote className="tp-verdict">{teamVerdict(t, streakCard, netRating)}</blockquote>

      {/* 3.2 This season */}
      <section className="tp-section">
        <div className="tp-section__head">
          <p className="page-region-title">This season · {seasonLabel}</p>
          <Link to={`/teams/${teamId}?tab=performance`} className="tp-link">Why the rating → Performance</Link>
        </div>
        {upcomingGame && <NextUp game={upcomingGame} t={t} navigate={navigate} />}
        <div className="tp-figs">
          {figures.map((f) => <Figure key={f.label} {...f} leagueSize={leagueSize} />)}
        </div>
        <div className="tp-season-body">
          <div className="tp-form">
            <FormChart trends={trends} height={220} teamColor={teamColor} />
            <p className="tp-caption">
              Rolling 10-game xGF% · 50% reference · blue above / red below · full season.
              {/* TODO(data): spec calls for rolling 10-game POWER-RATING percentile among teams; no
                  such series is served. Using rolling xGF% as a process proxy. */}
            </p>
            {streakCard?.is_notable && streakCard.run_word && (
              <p className="tp-insight">
                <span className="tp-insight__dot" style={{ background: streakCard.total_deviation < 0 ? 'var(--line-red)' : 'var(--line-blue)' }} />
                Recent form: a {streakCard.run_word}. {streakCard.verdict}
              </p>
            )}
          </div>
          <DivisionMini standings={standings} t={t} />
        </div>
      </section>

      {/* 3.3 How they play */}
      <HowTheyPlay identity={identity} t={t} leagueSize={leagueSize} />

      {/* 3.4 Who drives it */}
      <WhoDrivesIt teamSkaters={teamSkaters} teamGoalies={teamGoalies} roster={roster} teamAbbrev={t.team_abbrev} teamId={teamId} />

      {/* 3.5 The era */}
      <section className="tp-section">
        <div className="tp-section__head"><p className="page-region-title">The era</p></div>
        <p className="tp-empty">
          Ten-season power-rating history isn't served yet, so the franchise-arc chart is held back.
          {/* TODO(data): per-season power rating (10y) + configurable band thresholds
              (CONTENDER/PLAYOFF/BUBBLE/REBUILD) for the era chart. */}
        </p>
      </section>
    </div>
  )
}

function NextUp({ game, t, navigate }: { game: Game; t: TeamDetail; navigate: (p: string) => void }) {
  const isHome = game.home_team_id === t.team_id
  const oppAbbrev = isHome ? game.away_team_abbrev : game.home_team_abbrev
  return (
    <button type="button" className="tp-nextup" {...gameButtonProps(() => navigate(`/games/${game.game_id}`))}>
      <span className="tp-nextup__label">Next up</span>
      <img className="tp-nextup__logo" src={getTeamLogoUrl(oppAbbrev)} alt="" />
      <span className="tp-nextup__opp">{isHome ? 'vs' : '@'} {getTeamName(oppAbbrev)}</span>
      <span className="tp-nextup__when">
        {new Date(game.game_date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
      </span>
      <span className="tp-nextup__arrow">→</span>
    </button>
  )
}

/** The division mini table (§3.2 right): rank | logo | name | PTS | GP, cut line, team highlighted. */
function DivisionMini({ standings, t }: { standings: StandingsRow[]; t: TeamDetail }) {
  if (!t.division) return null
  const peers = standings
    .filter((s) => s.division === t.division && s.division_rank != null)
    .sort((a, b) => (a.division_rank ?? 99) - (b.division_rank ?? 99))
    .slice(0, 8)
  if (peers.length < 2) return null
  return (
    <div className="tp-divmini">
      <div className="tp-section__head">
        <p className="page-region-title">The division</p>
        <Link to="/teams?view=standings" className="tp-link">Full standings →</Link>
      </div>
      <div className="tp-divmini__rows">
        {peers.map((s) => (
          <div key={s.team_abbrev}>
            <Link
              to={`/teams/${s.team_id}`}
              className={`tp-divmini__row${s.team_abbrev === t.team_abbrev ? ' is-current' : ''}`}
            >
              <span className="tp-divmini__rank mono">{s.division_rank}</span>
              <img className="tp-divmini__logo" src={getTeamLogoUrl(s.team_abbrev)} alt="" />
              <span className="tp-divmini__name">{s.team_abbrev}</span>
              <span className="tp-divmini__pts mono">{s.points}</span>
              <span className="tp-divmini__gp mono">{s.games_played}</span>
            </Link>
            {s.division_rank === PLAYOFF_CUT && (
              <div className="tp-divmini__cut"><span className="tp-divmini__cut-label mono">CUT</span></div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

/** How they play (§3.3): league-distribution rows from the identity fingerprint, grouped. */
function HowTheyPlay({ identity, t, leagueSize }: { identity: TeamIdentity | null; t: TeamDetail; leagueSize: number }) {
  const [windowIdx, setWindowIdx] = useState(0)
  if (!identity || identity.windows.length === 0) {
    return (
      <section className="tp-section">
        <div className="tp-section__head"><p className="page-region-title">How they play</p></div>
        <p className="tp-empty">Style fingerprint isn't available for this team yet.</p>
      </section>
    )
  }
  const win = identity.windows[Math.min(windowIdx, identity.windows.length - 1)]
  const size = identity.league_size || leagueSize
  const byKey = new Map(win.metrics.map((m) => [m.key, m]))
  const rowFor = (key: string, inverse?: boolean) => {
    const m = byKey.get(key)
    if (!m || m.percentile == null) return null
    // goodness percentile: for "allowed" metrics a lower raw value is better.
    const good = inverse ? 1 - m.percentile : m.percentile
    const rank = Math.round((1 - good) * (size - 1)) + 1
    // Dot sits at the raw percentile (the tick field would too); rank/coloring use goodness.
    return { percentile: m.percentile, rank }
  }

  return (
    <section className="tp-section">
      <div className="tp-section__head">
        <p className="page-region-title">How they play</p>
        {identity.windows.length > 1 && (
          <div className="tp-pills">
            {identity.windows.map((w, i) => (
              <button key={w.window} type="button"
                className={`tp-pill${i === windowIdx ? ' is-active' : ''}`}
                onClick={() => setWindowIdx(i)}>{w.window}</button>
            ))}
          </div>
        )}
      </div>
      <p className="tp-legend">Ticks = all 32 teams · dot = {t.team_abbrev} · value = league rank
        {/* TODO(data): per-metric league table for all teams isn't served here, so tick positions are
            omitted; the dot and rank come from this team's served percentile. */}
      </p>
      <div className="tp-play-grid">
        {FINGERPRINT_GROUPS.map((group) => {
          const rows = group.metrics.map((m) => ({ m, r: rowFor(m.key, m.inverse) })).filter((x) => x.r)
          if (rows.length === 0) return null
          return (
            <div className="tp-play-group" key={group.title}>
              <p className="tp-play-group__title">{group.title}</p>
              {rows.map(({ m, r }) => (
                <LeagueDistributionRow key={m.key} label={m.label}
                  percentile={r!.percentile} rank={r!.rank} leagueSize={size} />
              ))}
            </div>
          )
        })}
      </div>
      <p className="tp-caption">Rank among {size} teams · {win.window}</p>
    </section>
  )
}

/** Who drives it (§3.4): top five skaters by WAR + the primary goalie, as linked tiles. */
function WhoDrivesIt({ teamSkaters, teamGoalies, roster, teamAbbrev, teamId }: {
  teamSkaters: ValueRankingRow[]; teamGoalies: ValueRankingRow[]; roster: TeamRoster | null
  teamAbbrev: string; teamId: number
}) {
  const rosterById = useMemo(() => {
    const map = new Map<number, RosterPlayer>()
    for (const p of [...(roster?.forwards ?? []), ...(roster?.defensemen ?? []), ...(roster?.goalies ?? [])]) map.set(p.player_id, p)
    return map
  }, [roster])

  const topSkaters = [...teamSkaters].sort((a, b) => b.war - a.war).slice(0, 5)
  // Primary goalie: most starts (roster GP as proxy) among team goalies, else highest WAR.
  const primaryGoalie = [...teamGoalies].sort((a, b) => {
    const ga = rosterById.get(a.player_id)?.games_played ?? 0
    const gb = rosterById.get(b.player_id)?.games_played ?? 0
    return gb - ga || b.war - a.war
  })[0]
  const cards = [...topSkaters, ...(primaryGoalie ? [primaryGoalie] : [])]
  if (cards.length === 0) {
    return (
      <section className="tp-section">
        <div className="tp-section__head"><p className="page-region-title">Who drives it</p></div>
        <p className="tp-empty">Player value data isn't available for this team yet.</p>
      </section>
    )
  }

  return (
    <section className="tp-section">
      <div className="tp-section__head">
        <p className="page-region-title">Who drives it</p>
        <Link to={`/teams/${teamId}?tab=roster`} className="tp-link">Full roster →</Link>
      </div>
      <div className="tp-drivers">
        {cards.map((p) => {
          const rp = rosterById.get(p.player_id)
          const isGoalie = (p.entity_kind ?? p.component_kind) === 'goalie'
          // Stat line: GP + on-ice xGF% from the roster payload (G-A-P totals aren't served).
          const stat = rp
            ? isGoalie
              ? `${rp.games_played} GP`
              : `${rp.games_played} GP · ${rp.on_ice_xgf_pct != null ? `${(rp.on_ice_xgf_pct * 100).toFixed(1)}% xGF` : formatTOI(rp.toi_per_gp)}`
            : `${p.position ?? ''}`.trim()
          return (
            <Tile key={p.player_id} to={`/players/${p.player_id}`} className="tp-driver">
              <PlayerAvatar id={p.player_id} team={teamAbbrev} name={p.player_name ?? ''} size={36} />
              <div className="tp-driver__body">
                <div className="tp-driver__name">{p.player_name}</div>
                <div className="tp-driver__pos">{p.position ?? (isGoalie ? 'G' : '')}
                  {/* TODO(data): age + G-A-P season stat line not served on the value/roster payloads. */}
                </div>
                <div className="tp-driver__stat">{stat}</div>
              </div>
              <div className="tp-driver__war" style={{ color: warColor(p.war) }}>{fmtWar(p.war)}<span>WAR</span></div>
            </Tile>
          )
        })}
      </div>
    </section>
  )
}

/* ============================================================================ Performance tab (§4) */
function PerformanceTab({ teamColor, power, trends, teamGoalies, roster, leagueSize }: {
  teamColor: string; power: { row: PowerRatingRow; rank: number; n: number } | null
  trends: TeamTrends | null; teamGoalies: ValueRankingRow[]; roster: TeamRoster | null; leagueSize: number
}) {
  const rosterById = useMemo(() => {
    const map = new Map<number, RosterPlayer>()
    for (const p of (roster?.goalies ?? [])) map.set(p.player_id, p)
    return map
  }, [roster])

  return (
    <div className="tp-stack">
      {/* 4.1 Where the rating comes from */}
      <section className="tp-section">
        <div className="tp-section__head">
          <p className="page-region-title">Where the rating comes from</p>
          <Link to="/teams?view=power" className="tp-link">Full rankings →</Link>
        </div>
        {power ? (
          <div className="tp-comp">
            {RATINGS_COMPONENTS.map((c) => {
              const v = power.row[c.contrib] as number
              return <ContribRow key={c.label} label={c.label} value={v}
                max={Math.max(0.2, ...RATINGS_COMPONENTS.map((k) => Math.abs(power.row[k.contrib] as number)))} />
            })}
            <div className="tp-comp__total">
              <span>Total</span>
              <span className="mono" style={{ color: rankColor(power.rank, power.n) }}>
                {fmtSigned(power.row.total_rating)} net goals per game · {ordinal(power.rank)} of {power.n}
              </span>
            </div>
          </div>
        ) : <p className="tp-empty">Rating composition isn't available.</p>}
      </section>

      {/* 4.2 Results vs the underlying game */}
      <section className="tp-section">
        <div className="tp-section__head"><p className="page-region-title">Results versus the underlying game</p></div>
        <p className="tp-empty">Cumulative goals-vs-expected (GF/xGF, GA/xGA) series aren't served yet.
          {/* TODO(data): cumulative GF, xGF, GA, xGA over the season for the paired gap charts. */}
        </p>
      </section>

      {/* 4.3 Form, full size */}
      <section className="tp-section">
        <div className="tp-section__head"><p className="page-region-title">Form</p></div>
        <FormChart trends={trends} height={320} teamColor={teamColor} />
        <p className="tp-caption">Rolling 10-game xGF% · full season.
          {/* TODO(data): points should click through to game recaps once per-point game ids are served. */}
        </p>
      </section>

      {/* 4.4 Situational profile */}
      <section className="tp-section">
        <div className="tp-section__head"><p className="page-region-title">Situational profile</p></div>
        <p className="tp-empty">Season situational rates (5v5 / PP / PK by xGF/60, xGA/60, GF/60, GA/60) with ranks aren't served yet.
          {/* TODO(data): season-level situational rate table with league ranks (getTeamSituational is per-game). */}
        </p>
      </section>

      {/* 4.5 Goaltending */}
      <section className="tp-section">
        <div className="tp-section__head"><p className="page-region-title">Goaltending</p></div>
        <LeagueDistributionRow label="Team GSAx" percentile={null} rank={null} leagueSize={leagueSize} />
        <p className="tp-caption">Team GSAx league position isn't served.
          {/* TODO(data): team-level GSAx value + league percentile/rank. */}
        </p>
        {teamGoalies.length > 0 ? (
          <table className="gamesheet tp-goalies">
            <thead><tr><th>Goalie</th><th className="num">GS</th><th className="num">GSAx</th><th className="num">WAR</th></tr></thead>
            <tbody>
              {teamGoalies.map((g) => (
                <tr key={g.player_id} onClick={() => (window.location.href = `/players/${g.player_id}`)} style={{ cursor: 'pointer' }}>
                  <td>{g.player_name}</td>
                  <td className="num mono">{rosterById.get(g.player_id)?.games_played ?? '—'}</td>
                  <td className="num mono">—{/* TODO(data): GSAx per goalie not on value payload. */}</td>
                  <td className="num mono" style={{ color: warColor(g.war) }}>{fmtWar(g.war)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="tp-empty">No goalie value data.</p>}
      </section>
    </div>
  )
}

/** One rating-composition row: label · diverging bar from zero · signed value (blue +, red −). */
function ContribRow({ label, value, max }: { label: string; value: number; max: number }) {
  const frac = Math.min(1, Math.abs(value) / max) * 50
  const pos = value >= 0
  const color = pos ? 'var(--color-data-positive)' : 'var(--color-data-negative)'
  return (
    <div className="tp-contrib">
      <span className="tp-contrib__label">{label}</span>
      <span className="tp-contrib__bar">
        <span className="tp-contrib__zero" />
        <span className="tp-contrib__fill" style={pos
          ? { left: '50%', width: `${frac}%`, background: color }
          : { left: `${50 - frac}%`, width: `${frac}%`, background: color }} />
      </span>
      <span className="tp-contrib__val mono" style={{ color }}>{fmtSigned(value)}</span>
    </div>
  )
}

/* ============================================================================ Roster tab (§5) */
function RosterTab({ teamId, teamAbbrev, teamSkaters, teamGoalies, initialLens }: {
  teamId: number; teamAbbrev: string; teamSkaters: ValueRankingRow[]; teamGoalies: ValueRankingRow[]; initialLens: 'depth' | 'lines'
}) {
  const [lens, setLens] = useState<'depth' | 'lines'>(initialLens)
  const warById = useMemo(() => {
    const m = new Map<number, number>()
    for (const r of [...teamSkaters, ...teamGoalies]) m.set(r.player_id, r.war)
    return m
  }, [teamSkaters, teamGoalies])

  return (
    <div className="tp-stack">
      <div className="tp-lens">
        <button type="button" className={`tp-lens__opt${lens === 'depth' ? ' is-active' : ''}`} onClick={() => setLens('depth')}>Depth chart</button>
        <button type="button" className={`tp-lens__opt${lens === 'lines' ? ' is-active' : ''}`} onClick={() => setLens('lines')}>Lines</button>
      </div>

      {lens === 'depth' ? (
        <>
          <DepthChart teamId={teamId} teamAbbrev={teamAbbrev} />
          {/* Per-slot WAR overlay: WAR is available from value rankings; AAV / cap are not. */}
          {warById.size > 0 && (
            <p className="tp-caption">WAR shown on player profiles.
              {/* TODO(data): per-cell "AAV · WAR" and the cap footer (committed / space) need a
                  contract endpoint; not served by the roster payload. */}
            </p>
          )}
        </>
      ) : (
        <>
          <section className="tp-section">
            <div className="tp-section__head"><p className="page-region-title">Lines <Ref n={4} /></p></div>
            <LineBoard teamId={teamId} />
          </section>
          <section className="tp-section">
            <div className="tp-section__head"><p className="page-region-title">Experiment with these lines →</p></div>
            <LineSwapWidget teamId={teamId} />
          </section>
        </>
      )}
    </div>
  )
}

/* ============================================================================ Games tab (§6) */
function GamesTab({ t, upcomingGame, recentGames, teamId, navigate }: {
  t: TeamDetail; upcomingGame: Game | null; recentGames: Game[]; teamId: number; navigate: (p: string) => void
}) {
  const [limit, setLimit] = useState(25)
  const fmtDate = (d: string) => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return (
    <div className="tp-stack">
      {upcomingGame && (
        <section className="tp-section">
          <div className="tp-section__head"><p className="page-region-title">Upcoming</p></div>
          <NextUp game={upcomingGame} t={t} navigate={navigate} />
        </section>
      )}
      <section className="tp-section">
        <div className="tp-section__head">
          <p className="page-region-title">Results</p>
          <span className="tp-note">{recentGames.length ? `${recentGames.length} games` : ''}</span>
        </div>
        {recentGames.length ? (
          <div className="tp-results">
            {recentGames.slice(0, limit).map((g) => {
              const isHome = g.home_team_id === teamId
              const us = isHome ? g.home_score : g.away_score
              const them = isHome ? g.away_score : g.home_score
              const opp = isHome ? g.away_team_abbrev : g.home_team_abbrev
              const win = (us ?? 0) > (them ?? 0)
              return (
                <button key={g.game_id} className="tp-result" {...gameButtonProps(() => navigate(`/games/${g.game_id}`))}>
                  <span className={`tp-result__wl${win ? ' is-win' : ''}`}>{win ? 'W' : 'L'}</span>
                  <span className="tp-result__date mono">{fmtDate(g.game_date)}</span>
                  <span className="tp-result__match">{isHome ? 'vs' : '@'} {opp} <span className="mono">{us}–{them}</span></span>
                  <span className="tp-result__arrow">→</span>
                </button>
              )
            })}
            {recentGames.length > limit && (
              <button className="tp-showmore" onClick={() => setLimit((n) => n + 25)}>Show more</button>
            )}
          </div>
        ) : <p className="tp-empty">No completed games in range.</p>}
        {/* TODO(data): month divider eyebrows + per-game worm (winner-colored) need per-game series. */}
      </section>
    </div>
  )
}

/* ============================================================================ Verdict text */
function teamVerdict(t: TeamDetail, streak: StreakCard | null, netRating: number | null): string {
  const tier = (r?: number | null) => r == null ? 'a middling' : r <= 8 ? 'an elite' : r <= 16 ? 'a strong' : r <= 24 ? 'a middling' : 'a bottom-tier'
  const gen = t.hdcf_per60_rank, supp = t.hdca_per60_rank
  let danger: string
  if (gen != null && supp != null && gen <= 12 && supp <= 12) danger = 'wins the high-danger battle at both ends'
  else if (gen != null && gen <= 12) danger = 'creates high-danger chances well but gives up too many'
  else if (supp != null && supp <= 12) danger = 'leans on suppressing danger more than creating it'
  else danger = 'is weak in the high-danger battle'
  let tail = '.'
  if (netRating != null) {
    const result = netRating >= 0.4 ? 'and outscores opponents comfortably' : netRating >= 0 ? 'and roughly breaks even on goals'
      : netRating >= -0.4 ? 'and is narrowly outscored' : 'and gets outscored'
    tail = `, ${result} (${fmtSigned(netRating)} net goals/gm).`
  }
  let s = `${getTeamName(t.team_abbrev)} is ${tier(t.cf_pct_rank)} possession team that ${danger}${tail}`
  if (streak?.is_notable && streak.run_word) s += ` Recent form: a ${streak.run_word}.`
  return s
}

export default TeamProfile
