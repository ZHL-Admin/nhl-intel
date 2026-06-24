import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { PageLayout, SkeletonLoader, StatCard, Badge, IdentityHeader, PlayerAvatar, StreakDoctorCard, StandingsLadder, InsightCard } from '../components/common'
import type { StandingsLadderTeam } from '../components/common'
import { Flame, Shield, Gauge, Crosshair, Zap, ShieldCheck, Sparkles, Hand, Lightbulb } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import Tabs from '../components/common/Tabs'
import { ChartPanel } from '../components/common'
import TeamIdentityTab from '../components/teams/TeamIdentityTab'
import TeamFormTab from '../components/teams/TeamFormTab'
import TeamRadar from '../components/teams/TeamRadar'
import LineBoard from '../components/teams/LineBoard'
import { LineSwapWidget } from '../components/common'
import { getTeamDetail, getTeamTrends, getTeamRoster, getTeamStreak, getStandings, getTeamInsights } from '../api/teams'
import { getPowerRankings } from '../api/rankings'
import { getTeamGames } from '../api/games'
import { TeamDetail, TeamTrends, TeamRoster, RosterPlayer, Game, StreakCard, PowerRatingRow, StandingsRow, TeamInsight } from '../api/types'
import { RATINGS_COMPONENTS } from '../config/metrics'
import { getTeamLogoUrl, getTeamName, getTeamColor, formatDateForAPI, formatTOI, setTeamPrimaryColor, clearTeamPrimaryColor } from '../utils/teams'
import { ordinal } from '../utils/format'
import { TEAM_SNAPSHOT_GROUPS, snapshotStatView } from '../config/metrics'

/** Top three per division clinch; 4th and below chase the conference wild cards. */
const PLAYOFF_CUT = 3

/** Division StandingsLadder view-model from league standings + the current team (header). Returns
 * null when the division slice isn't available, so the header omits the ladder rather than faking it. */
function divisionLadder(standings: StandingsRow[], t: TeamDetail): {
  division: string; teams: StandingsLadderTeam[]; contextLine?: string
} | null {
  if (!t.division) return null
  const peers = standings.filter((s) => s.division === t.division && s.division_rank != null)
  if (peers.length < 2) return null
  const teams: StandingsLadderTeam[] = peers.map((s) => ({
    teamId: s.team_id,
    abbrev: s.team_abbrev,
    logoUrl: getTeamLogoUrl(s.team_abbrev),
    rank: s.division_rank as number,
    points: s.points,
    gamesPlayed: s.games_played,
    isCurrent: s.team_abbrev === t.team_abbrev,
  }))
  const sorted = [...peers].sort((a, b) => (a.division_rank as number) - (b.division_rank as number))
  const me = sorted.find((s) => s.team_abbrev === t.team_abbrev)
  let contextLine: string | undefined
  if (me?.division_rank != null) {
    const rank = me.division_rank
    const pts = (n: number) => `${n} point${n === 1 ? '' : 's'}`
    if (rank <= PLAYOFF_CUT) {
      const firstOut = sorted.find((s) => s.division_rank === PLAYOFF_CUT + 1)
      const margin = firstOut ? me.points - firstOut.points : null
      contextLine = `${ordinal(rank)} in ${t.division}` +
        (margin != null && margin > 0 ? `, ${pts(margin)} up on the top three` : ', holding a top-three spot')
    } else {
      const cutTeam = sorted.find((s) => s.division_rank === PLAYOFF_CUT)
      const back = cutTeam ? cutTeam.points - me.points : null
      contextLine = `${ordinal(rank)} in ${t.division}` +
        (back != null && back > 0 ? `, ${pts(back)} back of the top three` : '')
    }
  }
  return { division: t.division, teams, contextLine }
}
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine, Label } from 'recharts'
import './TeamProfile.css'

function TeamProfile() {
  const { teamId } = useParams<{ teamId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const currentTab = searchParams.get('tab') || 'overview'

  const [teamDetail, setTeamDetail] = useState<TeamDetail | null>(null)
  const [teamTrends, setTeamTrends] = useState<TeamTrends | null>(null)
  const [teamRoster, setTeamRoster] = useState<TeamRoster | null>(null)
  const [upcomingGame, setUpcomingGame] = useState<Game | null>(null)
  const [recentGames, setRecentGames] = useState<Game[]>([])
  const [streakCard, setStreakCard] = useState<StreakCard | null>(null)
  // Power rating fetched ONCE here so the lead verdict and the Power Rating card show one net-goals/gm number.
  const [power, setPower] = useState<{ row: PowerRatingRow; rank: number; n: number } | null>(null)
  // League standings (sliced to the division for the header StandingsLadder) + generated quick insights.
  const [standings, setStandings] = useState<StandingsRow[]>([])
  const [insights, setInsights] = useState<TeamInsight[]>([])

  const [loading, setLoading] = useState(true)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [trendsError, setTrendsError] = useState<string | null>(null)
  const [rosterError, setRosterError] = useState<string | null>(null)

  const [sortConfig, setSortConfig] = useState<{
    key: string
    direction: 'asc' | 'desc'
  }>({ key: 'points_per60', direction: 'desc' })

  useEffect(() => {
    if (!teamId) return

    const fetchData = async () => {
      setLoading(true)
      setDetailError(null)
      setTrendsError(null)
      setRosterError(null)

      try {
        const detail = await getTeamDetail(parseInt(teamId))
        setTeamDetail(detail)
        // Set team primary color for contextual theming
        const teamColor = getTeamColor(detail.team_abbrev)
        setTeamPrimaryColor(teamColor)
      } catch (err) {
        console.error('Error fetching team detail:', err)
        setDetailError('Failed to load team details.')
      }

      // Fetch trends and roster independently
      try {
        const trends = await getTeamTrends(parseInt(teamId))
        setTeamTrends(trends)
      } catch (err) {
        console.error('Error fetching team trends:', err)
        setTrendsError('Failed to load team trends.')
      }

      try {
        const roster = await getTeamRoster(parseInt(teamId))
        setTeamRoster(roster)
      } catch (err) {
        console.error('Error fetching team roster:', err)
        setRosterError('Failed to load team roster.')
      }

      // Fetch upcoming games (next 7 days)
      try {
        const today = new Date()
        const nextWeek = new Date()
        nextWeek.setDate(today.getDate() + 7)

        const games = await getTeamGames(
          parseInt(teamId),
          formatDateForAPI(today),
          formatDateForAPI(nextWeek)
        )

        // Find the next preview game
        const nextGame = games.find(g => g.is_preview)
        if (nextGame) {
          setUpcomingGame(nextGame)
        }
      } catch (err) {
        console.error('Error fetching upcoming games:', err)
        // Not critical, don't set error state
      }

      // Last 10 completed games (for the Performance / Trends results timeline)
      try {
        const today = new Date()
        const past = new Date()
        past.setDate(today.getDate() - 60)
        const games = await getTeamGames(parseInt(teamId), formatDateForAPI(past), formatDateForAPI(today))
        const finals = games
          .filter(g => !g.is_preview && g.home_score != null && g.away_score != null)
          .sort((a, b) => b.game_date.localeCompare(a.game_date))
          .slice(0, 10)
        setRecentGames(finals)
      } catch (err) {
        console.error('Error fetching recent games:', err)
      }

      setLoading(false)
    }

    fetchData()

    // Cleanup: reset team primary color when leaving page
    return () => {
      clearTeamPrimaryColor()
    }
  }, [teamId])

  // Streak Doctor card (window 10) for the auto-render-when-notable banner (Phase 3.3).
  useEffect(() => {
    if (!teamId) return
    let active = true
    setStreakCard(null)
    getTeamStreak(parseInt(teamId), 10)
      .then((c) => active && setStreakCard(c))
      .catch(() => { /* no card (e.g. <10 games) — banner just hides */ })
    return () => { active = false }
  }, [teamId])

  // Power rating + league rank (shared by the lead verdict and the Power Rating card).
  useEffect(() => {
    if (!teamId) return
    let active = true
    setPower(null)
    getPowerRankings()
      .then((rows) => {
        if (!active) return
        const idx = rows.findIndex((r) => r.team_id === parseInt(teamId))
        if (idx >= 0) setPower({ row: rows[idx], rank: idx + 1, n: rows.length })
      })
      .catch(() => { /* no rating -> verdict + card degrade gracefully */ })
    return () => { active = false }
  }, [teamId])

  // League standings (header StandingsLadder) — degrade to no ladder if unavailable.
  useEffect(() => {
    let active = true
    setStandings([])
    getStandings()
      .then((rows) => active && setStandings(rows))
      .catch(() => { /* no standings -> header omits the ladder */ })
    return () => { active = false }
  }, [teamId])

  // Generated quick insights (engine copy) — omitted gracefully if unavailable.
  useEffect(() => {
    if (!teamId) return
    let active = true
    setInsights([])
    getTeamInsights(parseInt(teamId))
      .then((rows) => active && setInsights(rows))
      .catch(() => { /* no insights -> Quick insights section hides */ })
    return () => { active = false }
  }, [teamId])

  const handleRetryDetail = () => {
    if (teamId) {
      window.location.reload()
    }
  }

  const handleRetryTrends = async () => {
    if (!teamId) return
    setTrendsError(null)
    try {
      const trends = await getTeamTrends(parseInt(teamId))
      setTeamTrends(trends)
    } catch (err) {
      setTrendsError('Failed to load team trends.')
    }
  }

  const handleRetryRoster = async () => {
    if (!teamId) return
    setRosterError(null)
    try {
      const roster = await getTeamRoster(parseInt(teamId))
      setTeamRoster(roster)
    } catch (err) {
      setRosterError('Failed to load team roster.')
    }
  }

  const handleSort = (key: string) => {
    let direction: 'asc' | 'desc' = 'desc'
    if (sortConfig.key === key && sortConfig.direction === 'desc') {
      direction = 'asc'
    }
    setSortConfig({ key, direction })
  }

  const sortPlayers = (players: any[]) => {
    if (!sortConfig.key) return players
    const dir = sortConfig.direction === 'asc' ? 1 : -1
    return [...players].sort((a, b) => {
      const aVal = a[sortConfig.key]
      const bVal = b[sortConfig.key]
      // null/undefined always sort to the bottom regardless of direction
      const aNull = aVal == null, bNull = bVal == null
      if (aNull && bNull) return 0
      if (aNull) return 1
      if (bNull) return -1
      if (aVal === bVal) return 0
      return (aVal > bVal ? 1 : -1) * dir
    })
  }

  const handleTabChange = (tab: string) => {
    setSearchParams({ tab })
  }

  // Loading state
  if (loading) {
    return (
      <PageLayout>
        <div className="team-profile">
          {/* Header skeleton */}
          <div className="team-profile__header-skeleton">
            <SkeletonLoader height={120} />
          </div>

          {/* Stat cards skeleton */}
          <div className="team-profile__section">
            <h2 className="team-profile__section-title">Season Snapshot</h2>
            <div className="team-profile__stat-grid">
              {[...Array(8)].map((_, i) => (
                <SkeletonLoader key={i} height={100} />
              ))}
            </div>
          </div>

          {/* Charts skeleton */}
          <div className="team-profile__section">
            <SkeletonLoader height={300} />
          </div>
          <div className="team-profile__section">
            <SkeletonLoader height={300} />
          </div>

          {/* Roster skeleton */}
          <div className="team-profile__section">
            <SkeletonLoader height={400} />
          </div>
        </div>
      </PageLayout>
    )
  }

  // Error state for critical data
  if (detailError || !teamDetail) {
    return (
      <PageLayout>
        <div className="team-profile__error">
          <p className="team-profile__error-message">
            {detailError || 'Team not found'}
          </p>
          <button onClick={handleRetryDetail} className="team-profile__retry-button">
            Retry
          </button>
        </div>
      </PageLayout>
    )
  }

  const teamColor = getTeamColor(teamDetail.team_abbrev)
  const teamFullName = getTeamName(teamDetail.team_abbrev)
  const ladder = divisionLadder(standings, teamDetail)
  const netRating = power?.row.total_rating ?? null

  return (
    <PageLayout>
      <div className="team-profile">
        {/* Identity Header (compact, packed) */}
        {/* Header + standings as two side-by-side cards (per comp), not nested. */}
        <div className="team-hd-row">
          <IdentityHeader
            leftContent={
              <div className="team-hd">
                <img src={getTeamLogoUrl(teamDetail.team_abbrev)} alt={teamFullName} className="team-hd__logo" />
                <div className="team-hd__id">
                  <h1 className="team-hd__name">{teamFullName}</h1>
                  <div className="team-hd__context">
                    {[teamDetail.division, teamDetail.conference,
                      teamDetail.division_rank != null ? `${ordinal(teamDetail.division_rank)} in division` : null]
                      .filter(Boolean).join(' · ')}
                  </div>
                  <hr className="team-hd__divider" />
                  <div className="team-hd__hero">
                    <span className="team-hd__record mono">{teamDetail.wins}-{teamDetail.losses}-{teamDetail.otl}</span>
                    <span className="team-hd__pts">{teamDetail.points} PTS</span>
                    {power && (
                      <span className={`team-hd__power team-hd__power--r${power.rank <= 5 ? '1' : power.rank <= 11 ? '2' : power.rank <= 21 ? '3' : '4'}`}>
                        Power Ranking: #{power.rank} of {power.n}
                      </span>
                    )}
                  </div>
                  <p className="team-hd__verdict">{teamVerdict(teamDetail, streakCard, netRating)}</p>
                </div>
              </div>
            }
            teamColors={{ home: teamColor }}
          />
          {ladder && (
            <StandingsLadder
              division={ladder.division}
              teams={ladder.teams}
              playoffCutAfterRank={PLAYOFF_CUT}
              showHeader={false}
              size="md"
            />
          )}
        </div>

        {/* Upcoming Game Strip (conditional) */}
        {upcomingGame && (
          <div
            className="team-profile__upcoming-game"
            onClick={() => navigate(`/games/${upcomingGame.game_id}`)}
          >
            <div className="team-profile__upcoming-game-label">
              Next Game
            </div>
            <div className="team-profile__upcoming-game-info">
              <div className="team-profile__upcoming-game-opponent">
                {upcomingGame.home_team_id === teamDetail.team_id ? 'vs' : '@'}{' '}
                <span className="team-profile__upcoming-game-opponent-name">
                  {upcomingGame.home_team_id === teamDetail.team_id
                    ? getTeamName(upcomingGame.away_team_abbrev)
                    : getTeamName(upcomingGame.home_team_abbrev)}
                </span>
              </div>
              <div className="team-profile__upcoming-game-date">
                {new Date(upcomingGame.game_date).toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'short',
                  day: 'numeric'
                })}
              </div>
            </div>
            <div className="team-profile__upcoming-game-arrow">→</div>
          </div>
        )}
        
        {/* Tabs + tab content together in one card */}
        <div className="team-tabs-card">
          <div className="team-tabs-card__nav">
            <Tabs
              options={[
                { value: 'overview', label: 'Overview' },
                { value: 'identity', label: 'Identity' },
                { value: 'performance', label: 'Performance / Trends' },
                { value: 'lines', label: 'Lines' },
                { value: 'roster', label: 'Roster' },
                // Matchups hidden until its vs-opponent content is built (no empty tab).
              ]}
              value={currentTab}
              onChange={handleTabChange}
            />
          </div>

          {/* Tab Content */}
          {currentTab === 'overview' && teamId && (
            <OverviewTab teamDetail={teamDetail} teamColor={teamColor} streakCard={streakCard}
              power={power} insights={insights} teamId={parseInt(teamId)} />
          )}

          {currentTab === 'identity' && teamId && (
            <TeamIdentityTab teamId={parseInt(teamId)} teamDetail={teamDetail} teamColor={teamColor} />
          )}

          {/* Performance / Trends — form verdict (Streak Doctor, its own Last 5/10/20 toggle) then
              the season-long rolling trend charts + last-10 results. */}
          {currentTab === 'performance' && teamId && (
            <>
              <TeamFormTab teamId={parseInt(teamId)} />
              <PerformanceTrendsTab
                teamTrends={teamTrends}
                trendsError={trendsError}
                handleRetryTrends={handleRetryTrends}
                teamColor={teamColor}
                recentGames={recentGames}
                teamId={parseInt(teamId)}
                navigate={navigate}
              />
            </>
          )}

          {currentTab === 'lines' && teamId && (
            <div className="team-profile__content">
              <div className="team-profile__section">
                <h2 className="team-profile__section-title">Lines</h2>
                <LineBoard teamId={parseInt(teamId)} />
              </div>
              <div className="team-profile__section">
                <h2 className="team-profile__section-title">Experiment with a swap</h2>
                <p className="team-profile__section-sub">Swap any player into a current line to see the projected grade and xGF% change.</p>
                <LineSwapWidget teamId={parseInt(teamId)} />
              </div>
            </div>
          )}

          {currentTab === 'roster' && (
            <RosterTab
              teamRoster={teamRoster}
              teamAbbrev={teamDetail?.team_abbrev}
              rosterError={rosterError}
              handleRetryRoster={handleRetryRoster}
              sortConfig={sortConfig}
              handleSort={handleSort}
              sortPlayers={sortPlayers}
              navigate={navigate}
            />
          )}
        </div>
      </div>
    </PageLayout>
  )
}

/**
 * Power-rating breakdown for one team (Phase 3.1). The four-component ComponentStackBar with
 * labels lives HERE (off the Rankings list, which shows a single magnitude bar). Reuses the
 * existing /rankings/power endpoint and finds this team's row — no new backend surface.
 */
/** Power Rating card (right rail): number + ±SE + the four-component ComponentStackBar. Takes the
 * lifted power row so it shows the SAME net-goals/game number the lead verdict references. */
/** One contribution as a diverging row: label · mini bar from league average · signed value.
 * Color encodes SIGN only (valence): right/green above average, left/red below — never the
 * component category. The baseline is league average (zero), consistent with the rest of the site. */
function ContribRow({ label, value, max }: { label: string; value: number; max: number }) {
  const frac = Math.min(1, Math.abs(value) / max) * 50 // % of the half-track from centre
  const pos = value >= 0
  const color = pos ? 'var(--color-success)' : 'var(--color-danger)'
  return (
    <div className="tov-contrib">
      <span className="tov-contrib__label">{label}</span>
      <span className="tov-contrib__bar">
        <span className="tov-contrib__zero" />
        <span
          className="tov-contrib__fill"
          style={pos
            ? { left: '50%', width: `${frac}%`, background: color }
            : { left: `${50 - frac}%`, width: `${frac}%`, background: color }}
        />
      </span>
      <span className="tov-contrib__val mono" style={{ color }}>{(pos ? '+' : '') + value.toFixed(2)}</span>
    </div>
  )
}

function PowerRatingCard({ power }: { power: { row: PowerRatingRow; rank: number; n: number } | null }) {
  if (!power) return null
  const { row: r, rank, n } = power
  const contribs = RATINGS_COMPONENTS.map((c) => ({ label: c.label, value: r[c.contrib] as number }))
  const max = Math.max(0.2, ...contribs.map((c) => Math.abs(c.value)), Math.abs(r.total_rating) + (r.rating_se ?? 0))
  const fmt = (v: number) => (v >= 0 ? '+' : '') + v.toFixed(2)
  return (
    <div className="tov-card">
      <div className="tov-card__title">Power rating</div>
      <div className="tov-power__top">
        <span className="tov-power__num">{fmt(r.total_rating)}</span>
        <span className="tov-power__unit">net goals / game</span>
        {r.rating_se != null && <span className="tov-power__se">± {r.rating_se.toFixed(2)}</span>}
        <span className="tov-power__rank mono">#{rank} of {n}</span>
      </div>
      <div className="tov-power__rows">
        {contribs.map((c) => <ContribRow key={c.label} label={c.label} value={c.value} max={max} />)}
      </div>
      <Link to="/rankings" className="tov-card__link">Full rankings →</Link>
    </div>
  )
}

// Overview Tab Component
/** Deterministic Overview verdict (Layer 1). Net goals/game is sourced from the Power Rating total
 * (the same number the Power Rating card shows) so the page never states two different figures. */
function teamVerdict(t: TeamDetail, streak: StreakCard | null, netRating: number | null): string {
  const tier = (r?: number | null) => r == null ? 'a middling' : r <= 8 ? 'an elite' : r <= 16 ? 'a strong' : r <= 24 ? 'a middling' : 'a bottom-tier'
  const gen = t.hdcf_per60_rank, supp = t.hdca_per60_rank
  let danger: string
  if (gen != null && supp != null && gen <= 12 && supp <= 12) danger = 'win the high-danger battle at both ends'
  else if (gen != null && gen <= 12) danger = 'create high-danger chances well but give up too many'
  else if (supp != null && supp <= 12) danger = 'lean on suppressing danger more than creating it'
  else danger = 'are weak in the high-danger battle'
  let tail = '.'
  if (netRating != null) {
    const result = netRating >= 0.4 ? 'and outscore opponents comfortably' : netRating >= 0 ? 'and roughly break even on goals'
      : netRating >= -0.4 ? 'and are narrowly outscored' : 'and get outscored'
    tail = `, ${result} (${netRating >= 0 ? '+' : ''}${netRating.toFixed(2)} net goals/gm).`
  }
  let s = `${t.team_abbrev} is ${tier(t.cf_pct_rank)} possession team that ${danger}${tail}`
  if (streak?.is_notable && streak.run_word) s += ` Recent form: a ${streak.run_word}.`
  return s
}

/** Strongest / weakest dimension read for the radar card, from the same rank fields the radar plots. */
function radarRead(t: TeamDetail): string | null {
  const dims = ([
    { label: 'possession', rank: t.cf_pct_rank },
    { label: 'chance quality', rank: t.xgf_pct_rank },
    { label: 'danger generation', rank: t.hdcf_per60_rank },
    { label: 'danger suppression', rank: t.hdca_per60_rank },
    { label: 'zone control', rank: t.zone_entry_proxy_success_rate_rank },
  ].filter((d) => d.rank != null) as { label: string; rank: number }[])
  if (dims.length < 2) return null
  const best = dims.reduce((b, d) => (d.rank < b.rank ? d : b), dims[0])
  const worst = dims.reduce((b, d) => (d.rank > b.rank ? d : b), dims[0])
  return `Strongest: ${best.label} (${ordinal(best.rank)}) · Weakest: ${worst.label} (${ordinal(worst.rank)})`
}

/** Lucide icon for an insight's engine-provided icon name (falls back to a generic bulb). */
const INSIGHT_ICONS: Record<string, LucideIcon> = {
  flame: Flame, shield: Shield, gauge: Gauge, crosshair: Crosshair, zap: Zap,
  'shield-check': ShieldCheck, sparkles: Sparkles, hand: Hand,
}

/** Streak component key (cold-strip driver) -> insight category, so Quick insights don't restate it. */
const STREAK_TO_INSIGHT: Record<string, string> = {
  goaltending: 'goaltending', shooting_luck: 'finishing', special_teams: 'special_teams', play_change: 'possession',
}

/** The cold strip's dominant driver key (largest-magnitude component aligned with the run direction). */
function streakDriverKey(card: StreakCard): string | null {
  const sign = Math.sign(card.total_deviation) || 1
  const aligned = card.components.filter((c) => Math.sign(c.value) === sign)
  const pool = aligned.length ? aligned : card.components
  if (!pool.length) return null
  return pool.reduce((b, c) => (Math.abs(c.value) > Math.abs(b.value) ? c : b), pool[0]).key
}

function OverviewTab({ teamDetail, teamColor, streakCard, power, insights, teamId }: {
  teamDetail: TeamDetail; teamColor: string; streakCard: StreakCard | null
  power: { row: PowerRatingRow; rank: number; n: number } | null
  insights: TeamInsight[]; teamId: number
}) {
  const read = radarRead(teamDetail)
  const showColdStrip = !!streakCard?.is_notable

  // Quick insights: drop the engine card that restates the cold strip's driver, then take three.
  const driver = showColdStrip ? streakDriverKey(streakCard!) : null
  const excludeKey = driver ? STREAK_TO_INSIGHT[driver] : null
  const quickInsights = insights.filter((i) => i.key !== excludeKey).slice(0, 3)

  return (
    <div className="team-profile__content tov">
      {/* EVIDENCE ZONE — two columns; tops aligned, bottoms even (the identity verdict now
          lives in the page header, just under the record line). */}
      <div className="tov-evidence">
        <div className="tov-col">
          <div className="tov-col__head">
            <h2 className="team-profile__section-title">Season snapshot</h2>
            <p className="tov-col__sub">Team performance at a glance</p>
          </div>
          {showColdStrip && (
            <StreakDoctorCard card={streakCard!} variant="strip" href={`/teams/${teamId}?tab=performance`} />
          )}
          <div className="tov-col__container">
          {TEAM_SNAPSHOT_GROUPS.map((group) => (
            <div className="tov-snap-group" key={group.id}>
              <div className="tov-snap-group__label">{group.label}</div>
              <div className="tov-snap-row">
                {group.stats.map((stat) => {
                  const v = snapshotStatView(teamDetail, stat)
                  return <StatCard key={stat.key} label={stat.label} value={v.value} rank={v.rank} tooltip={v.tooltip} />
                })}
              </div>
            </div>
          ))}
          </div>
        </div>

        <div className="tov-rail">
          <h2 className="team-profile__section-title">Rating &amp; profile</h2>
          <PowerRatingCard power={power} />
          <div className="tov-card tov-radar">
            <div className="tov-card__title">How they're built</div>
            <TeamRadar teamDetail={teamDetail} color={teamColor} height={300} />
            {read && <p className="tov-radar__read">{read}</p>}
          </div>
        </div>
      </div>

      {/* QUICK INSIGHTS — generated cards, deduped against the cold strip */}
      {quickInsights.length > 0 && (
        <div className="tov-insights">
          <h2 className="team-profile__section-title">Quick insights</h2>
          <div className="tov-insights__grid">
            {quickInsights.map((ins) => (
              <InsightCard
                key={ins.key}
                tone={ins.tone}
                icon={INSIGHT_ICONS[ins.icon] ?? Lightbulb}
                title={ins.title}
                body={ins.body}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** Performance / Trends: full-season rolling charts (de-defaulted per UX 3.5) + last-10 results. */
function PerformanceTrendsTab({ teamTrends, trendsError, handleRetryTrends, teamColor, recentGames, teamId, navigate }: {
  teamTrends: TeamTrends | null; trendsError: string | null; handleRetryTrends: () => void
  teamColor: string; recentGames: Game[]; teamId: number; navigate: (p: string) => void
}) {
  const fmtDate = (d: string) => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const possData = teamTrends?.cf_pct_5gp.map((pt, i) => ({
    date: fmtDate(pt.game_date), cf_pct: pt.value * 100, xgf_pct: (teamTrends.xgf_pct_5gp[i]?.value ?? 0) * 100,
  })) ?? []
  const dangerData = teamTrends?.hdcf_per60_5gp.map((pt) => ({ date: fmtDate(pt.game_date), hdcf: pt.value })) ?? []
  const tip = { backgroundColor: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', fontSize: 11 }
  return (
    <div className="team-profile__content">
      <div className="team-profile__section">
        <h2 className="team-profile__section-title">Season Trends</h2>
        <p className="team-profile__section-sub">Five-game rolling averages over the full season (not controlled by the form toggle above).</p>
        {trendsError ? (
          <div className="team-profile__section-error"><p>{trendsError}</p><button onClick={handleRetryTrends} className="team-profile__retry-button">Retry</button></div>
        ) : possData.length > 0 ? (
          <>
            <ChartPanel title="Possession and chance share (CF% / xGF%)">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={possData} margin={{ top: 8, right: 56, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" />
                  <XAxis dataKey="date" stroke="var(--color-border)" tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} />
                  <YAxis domain={[40, 60]} stroke="var(--color-border)" tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} tickFormatter={(v) => Math.round(v).toString()} />
                  <RechartsTooltip contentStyle={tip} formatter={(v: any) => `${Number(v).toFixed(1)}%`} />
                  <ReferenceLine y={50} stroke="var(--color-border-strong)" strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="cf_pct" stroke={teamColor} strokeWidth={2} dot={false} isAnimationActive={false}>
                    <Label value="CF%" position="right" fill={teamColor} style={{ fontSize: 11, fontWeight: 600 }} />
                  </Line>
                  <Line type="monotone" dataKey="xgf_pct" stroke="var(--color-accent)" strokeWidth={2} dot={false} isAnimationActive={false}>
                    <Label value="xGF%" position="right" fill="var(--color-accent)" style={{ fontSize: 11, fontWeight: 600 }} />
                  </Line>
                </LineChart>
              </ResponsiveContainer>
            </ChartPanel>
            {dangerData.length > 0 && (
              <ChartPanel title="High-danger chances created (HDCF/60)">
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={dangerData} margin={{ top: 8, right: 64, bottom: 0, left: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" />
                    <XAxis dataKey="date" stroke="var(--color-border)" tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} />
                    <YAxis stroke="var(--color-border)" tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} tickFormatter={(v) => Math.round(v).toString()} />
                    <RechartsTooltip contentStyle={tip} formatter={(v: any) => Number(v).toFixed(1)} />
                    <Line type="monotone" dataKey="hdcf" stroke="var(--color-data-positive)" strokeWidth={2} dot={false} isAnimationActive={false}>
                      <Label value="HDCF/60" position="right" fill="var(--color-data-positive)" style={{ fontSize: 11, fontWeight: 600 }} />
                    </Line>
                  </LineChart>
                </ResponsiveContainer>
              </ChartPanel>
            )}
          </>
        ) : (
          <div className="team-profile__no-data">Insufficient data for trends</div>
        )}
      </div>

      {recentGames.length > 0 && (
        <div className="team-profile__section">
          <h2 className="team-profile__section-title">Last 10 Results</h2>
          <div className="team-profile__results">
            {recentGames.map((g) => {
              const isHome = g.home_team_id === teamId
              const us = isHome ? g.home_score : g.away_score
              const them = isHome ? g.away_score : g.home_score
              const oppAbbrev = isHome ? g.away_team_abbrev : g.home_team_abbrev
              const win = (us ?? 0) > (them ?? 0)
              return (
                <button key={g.game_id} className="team-profile__result-row" onClick={() => navigate(`/games/${g.game_id}`)}>
                  <span className="team-profile__result-date">{fmtDate(g.game_date)}</span>
                  <span className="team-profile__result-opp">{isHome ? 'vs' : '@'} {oppAbbrev}</span>
                  <span className={`team-profile__result-chip ${win ? 'is-win' : 'is-loss'}`}>{win ? 'W' : 'L'}</span>
                  <span className="team-profile__result-score mono">{us}–{them}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// Performance Tab Placeholder
// Roster Tab Component
function RosterTab({
  teamRoster,
  teamAbbrev,
  rosterError,
  handleRetryRoster,
  sortConfig,
  handleSort,
  sortPlayers,
  navigate
}: {
  teamRoster: TeamRoster | null
  teamAbbrev?: string | null
  rosterError: string | null
  handleRetryRoster: () => void
  sortConfig: { key: string; direction: 'asc' | 'desc' }
  handleSort: (key: string) => void
  sortPlayers: (players: any[]) => any[]
  navigate: (path: string) => void
}) {
  const f = teamRoster?.forwards ?? []
  const d = teamRoster?.defensemen ?? []
  const g = teamRoster?.goalies ?? []
  const summary = teamRoster
    ? `${f.length} forwards · ${d.length} defensemen · ${g.length} goalies — 5v5 production, real ice time, and on-ice xGF share.`
    : ''

  return (
    <div className="team-profile__content">
      <div className="team-profile__section">
        <h2 className="team-profile__section-title">Roster</h2>
        {summary && <p className="team-profile__section-sub">{summary}</p>}
        {rosterError ? (
          <div className="team-profile__section-error">
            <p>{rosterError}</p>
            <button onClick={handleRetryRoster} className="team-profile__retry-button">Retry</button>
          </div>
        ) : teamRoster ? (
          <div className="team-profile__roster">
            {f.length > 0 && (
              <RosterTable heading="Forwards" players={sortPlayers(f)} teamAbbrev={teamAbbrev}
                sortConfig={sortConfig} handleSort={handleSort} navigate={navigate} />
            )}
            {d.length > 0 && (
              <RosterTable heading="Defensemen" players={sortPlayers(d)} teamAbbrev={teamAbbrev}
                sortConfig={sortConfig} handleSort={handleSort} navigate={navigate} />
            )}
            {g.length > 0 && (
              <div className="team-profile__roster-section">
                <h3 className="team-profile__roster-heading">Goalies</h3>
                <table className="team-profile__roster-table">
                  <thead><tr><th>Goalie</th><th className="team-profile__roster-table-number">GP</th></tr></thead>
                  <tbody>
                    {g.map((player) => (
                      <tr key={player.player_id} className="team-profile__roster-row"
                        onClick={() => navigate(`/players/${player.player_id}`)}>
                        <td><RosterNameCell player={player} teamAbbrev={teamAbbrev} /></td>
                        <td className="team-profile__roster-table-number mono">{player.games_played}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          <div className="team-profile__no-data">No roster data available</div>
        )}
      </div>
    </div>
  )
}

/** Player name cell: headshot + name + archetype chip (reused across roster tables). */
function RosterNameCell({ player, teamAbbrev }: { player: RosterPlayer; teamAbbrev?: string | null }) {
  return (
    <div className="team-profile__roster-player">
      <PlayerAvatar id={player.player_id} team={teamAbbrev} name={player.player_name} size={28} />
      <div className="team-profile__roster-player-meta">
        <span className="team-profile__roster-player-name">{player.player_name}</span>
        {player.archetype && <span className="team-profile__roster-arch">{player.archetype}</span>}
      </div>
    </div>
  )
}

/** Tier color for an on-ice share around 50% (top third green / bottom third red, per UX rule 7). */
function shareColor(v?: number | null): string | undefined {
  if (v == null) return undefined
  if (v >= 0.52) return 'var(--color-success)'
  if (v <= 0.48) return 'var(--color-danger)'
  return undefined
}
const pct1 = (v?: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
const dec2 = (v?: number | null) => (v == null ? '—' : v.toFixed(2))

/** Sortable skater roster table with real per-player values (UX number formatting). */
function RosterTable({ heading, players, teamAbbrev, sortConfig, handleSort, navigate }: {
  heading: string
  players: RosterPlayer[]
  teamAbbrev?: string | null
  sortConfig: { key: string; direction: 'asc' | 'desc' }
  handleSort: (key: string) => void
  navigate: (path: string) => void
}) {
  const arrow = (key: string) => (sortConfig.key === key ? (sortConfig.direction === 'asc' ? ' ↑' : ' ↓') : '')
  const cols: { key: string; label: string; mobileHide?: boolean }[] = [
    { key: 'games_played', label: 'GP' },
    { key: 'toi_per_gp', label: 'TOI/GP' },
    { key: 'points_per60', label: 'PTS/60' },
    { key: 'goals_per60', label: 'G/60', mobileHide: true },
    { key: 'ixg_per60', label: 'ixG/60', mobileHide: true },
    { key: 'on_ice_xgf_pct', label: 'ON-ICE xGF%' },
    { key: 'ozs_pct', label: 'OZS%', mobileHide: true },
  ]
  return (
    <div className="team-profile__roster-section">
      <h3 className="team-profile__roster-heading">{heading}</h3>
      <table className="team-profile__roster-table">
        <thead>
          <tr>
            <th onClick={() => handleSort('player_name')} className="team-profile__roster-sortable">Player{arrow('player_name')}</th>
            {cols.map((c) => (
              <th key={c.key} onClick={() => handleSort(c.key)}
                className={`team-profile__roster-table-number team-profile__roster-sortable${c.mobileHide ? ' hide-mobile' : ''}`}>
                {c.label}{arrow(c.key)}
              </th>
            ))}
            <th className="team-profile__roster-table-number">FORM</th>
          </tr>
        </thead>
        <tbody>
          {players.map((player) => (
            <tr key={player.player_id} className="team-profile__roster-row"
              onClick={() => navigate(`/players/${player.player_id}`)}>
              <td><RosterNameCell player={player} teamAbbrev={teamAbbrev} /></td>
              <td className="team-profile__roster-table-number mono">{player.games_played}</td>
              <td className="team-profile__roster-table-number mono">{formatTOI(player.toi_per_gp)}</td>
              <td className="team-profile__roster-table-number mono">{dec2(player.points_per60)}</td>
              <td className="team-profile__roster-table-number mono hide-mobile">{dec2(player.goals_per60)}</td>
              <td className="team-profile__roster-table-number mono hide-mobile">{dec2(player.ixg_per60)}</td>
              <td className="team-profile__roster-table-number mono" style={{ color: shareColor(player.on_ice_xgf_pct) }}>{pct1(player.on_ice_xgf_pct)}</td>
              <td className="team-profile__roster-table-number mono hide-mobile">{pct1(player.ozs_pct)}</td>
              <td className="team-profile__roster-table-number">
                {player.hot_cold === 'hot' ? <Badge variant="hot" />
                  : player.hot_cold === 'cold' ? <Badge variant="cold" />
                    : <span className="team-profile__roster-form-neutral">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default TeamProfile
