import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { PageLayout, SkeletonLoader, StatCard, Badge, IdentityHeader, ComponentStackBar, PlayerAvatar } from '../components/common'
import type { StackSegment } from '../components/common'
import Tabs from '../components/common/Tabs'
import { ChartPanel } from '../components/common'
import TeamIdentityTab from '../components/teams/TeamIdentityTab'
import TeamFormTab from '../components/teams/TeamFormTab'
import TeamRadar from '../components/teams/TeamRadar'
import { LineSwapWidget } from '../components/common'
import { getTeamDetail, getTeamTrends, getTeamRoster, getTeamStreak } from '../api/teams'
import { getPowerRankings } from '../api/rankings'
import { getTeamGames } from '../api/games'
import { TeamDetail, TeamTrends, TeamRoster, RosterPlayer, Game, StreakCard, PowerRatingRow } from '../api/types'
import { RATINGS_COMPONENTS } from '../config/metrics'
import { getTeamLogoUrl, getTeamName, getTeamColor, formatDateForAPI, formatTOI, setTeamPrimaryColor, clearTeamPrimaryColor } from '../utils/teams'
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

  return (
    <PageLayout>
      <div className="team-profile">
        {/* Identity Header */}
        <IdentityHeader
          backLink={{ label: '← Back to Teams', to: '/teams' }}
          leftContent={
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
              <img
                src={getTeamLogoUrl(teamDetail.team_abbrev)}
                alt={teamFullName}
                style={{ width: '64px', height: '64px', objectFit: 'contain' }}
              />
              <div>
                <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 600, margin: 0, color: 'var(--color-text-primary)' }}>
                  {teamFullName}
                </h1>
                <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-2)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-base)', color: 'var(--color-text-secondary)' }}>
                    {teamDetail.wins}-{teamDetail.losses}-{teamDetail.otl}
                  </span>
                  <span style={{ fontSize: 'var(--text-base)', color: 'var(--color-text-secondary)' }}>
                    {teamDetail.points} PTS
                  </span>
                </div>
              </div>
            </div>
          }
          teamColors={{ home: teamColor }}
        />

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

        {/* Tab Navigation */}
        <div style={{ padding: 'var(--space-6) 0', borderBottom: '1px solid var(--color-border)' }}>
          <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 var(--space-6)' }}>
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
        </div>

        {/* Tab Content */}
        {currentTab === 'overview' && (
          <OverviewTab teamDetail={teamDetail} teamColor={teamColor} streakCard={streakCard} />
        )}

        {/* Power-rating component breakdown — the full four-part split lives here (Phase 3.1) */}
        {currentTab === 'overview' && teamId && (
          <div style={{ maxWidth: 760, margin: '0 auto', padding: '0 var(--space-6, 24px) var(--space-4, 16px)' }}>
            <TeamPowerCard teamId={parseInt(teamId)} />
          </div>
        )}

        {/* Notable run -> a single compact insight line (the full Streak Doctor lives on
            Performance / Trends, not here). */}
        {currentTab === 'overview' && streakCard?.is_notable && (
          <div style={{ maxWidth: 760, margin: '0 auto', padding: '0 var(--space-6, 24px) var(--space-4, 16px)' }}>
            <Link to={`/teams/${teamId}?tab=performance`} className="team-profile__streak-line">
              <Badge variant={streakCard.run_word === 'surge' ? 'hot' : streakCard.run_word === 'slump' ? 'cold' : 'small-sample'}
                label={streakCard.run_word ? streakCard.run_word.toUpperCase() : 'FORM'} />
              <span>{streakCard.verdict}</span>
              <span className="team-profile__streak-line-cta">See Performance / Trends →</span>
            </Link>
          </div>
        )}

        {currentTab === 'identity' && teamId && (
          <TeamIdentityTab teamId={parseInt(teamId)} />
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
          <div className="team-profile__section">
            <h2 className="team-profile__section-title">Line Lab</h2>
            <LineSwapWidget teamId={parseInt(teamId)} />
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
    </PageLayout>
  )
}

/**
 * Power-rating breakdown for one team (Phase 3.1). The four-component ComponentStackBar with
 * labels lives HERE (off the Rankings list, which shows a single magnitude bar). Reuses the
 * existing /rankings/power endpoint and finds this team's row — no new backend surface.
 */
function TeamPowerCard({ teamId }: { teamId: number }) {
  const [rows, setRows] = useState<PowerRatingRow[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active = true
    getPowerRankings()
      .then((d) => { if (active) setRows(d) })
      .catch(() => { if (active) setFailed(true) })
    return () => { active = false }
  }, [teamId])

  if (failed || !rows) return null
  const idx = rows.findIndex((r) => r.team_id === teamId)
  if (idx === -1) return null // e.g. a national team with no NHL rating
  const r = rows[idx]

  const segments: StackSegment[] = RATINGS_COMPONENTS.map((c) => ({
    key: c.key, label: c.label, value: r[c.contrib] as number, color: c.color,
  }))
  let pos = 0, neg = 0
  for (const c of RATINGS_COMPONENTS) { const v = r[c.contrib] as number; if (v >= 0) pos += v; else neg += v }
  const m = Math.max(0.2, pos, Math.abs(neg), Math.abs(r.total_rating) + (r.rating_se ?? 0))
  const fmt = (v: number) => (v >= 0 ? '+' : '') + v.toFixed(2)

  return (
    <div className="team-profile__section">
      <h2 className="team-profile__section-title">Power Rating</h2>
      <div style={{
        border: '1px solid var(--color-border)', borderRadius: 'var(--radius-xl)',
        background: 'var(--color-bg-surface)', boxShadow: 'var(--shadow-sm)',
        padding: 'var(--space-5)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)',
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-2)' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: 'var(--text-2xl)', color: 'var(--color-text-primary)' }}>{fmt(r.total_rating)}</span>
            <span style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-muted)' }}>net goals / game</span>
            {r.rating_se != null && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>± {r.rating_se.toFixed(2)}</span>}
          </div>
          <Link to="/rankings" style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-secondary)' }}>
            #{idx + 1} of {rows.length} · full rankings →
          </Link>
        </div>

        <ComponentStackBar segments={segments} total={r.total_rating} domain={[-m, m]} se={r.rating_se} height={26} />

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2) var(--space-4)' }}>
          {RATINGS_COMPONENTS.map((c) => (
            <span key={c.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: c.color, display: 'inline-block' }} />
              {c.label}
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-muted)' }}>{fmt(r[c.contrib] as number)}</span>
            </span>
          ))}
        </div>
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', lineHeight: 1.5, margin: 0 }}>
          Net goals per game versus a league-average opponent, split into the four sources that produce it.
          Bar centred at league average; the tick is the total, the line its uncertainty.
        </p>
      </div>
    </div>
  )
}

// Overview Tab Component
/** Deterministic Overview verdict (Layer 1) from real rank fields + any notable run. Template-only
 * (no generated prose); the Phase 6 insight engine will replace this. */
function teamVerdict(t: TeamDetail, streak: StreakCard | null): string {
  const tier = (r?: number | null) => r == null ? 'a middling' : r <= 8 ? 'an elite' : r <= 16 ? 'a strong' : r <= 24 ? 'a middling' : 'a bottom-tier'
  const gd = (t.total_goals_for - t.total_goals_against) / Math.max(1, t.games_played)
  const gen = t.hdcf_per60_rank, supp = t.hdca_per60_rank
  let danger: string
  if (gen != null && supp != null && gen <= 12 && supp <= 12) danger = 'win the high-danger battle at both ends'
  else if (gen != null && gen <= 12) danger = 'create high-danger chances well but give up too many'
  else if (supp != null && supp <= 12) danger = 'lean on suppressing danger more than creating it'
  else danger = 'are middling in the high-danger battle'
  const result = gd >= 0.4 ? 'and outscore opponents comfortably' : gd >= 0 ? 'and roughly break even on goals'
    : gd >= -0.4 ? 'and are narrowly outscored' : 'and get outscored'
  let s = `${t.team_abbrev} are ${tier(t.cf_pct_rank)} possession team that ${danger}, ${result} (${gd >= 0 ? '+' : ''}${gd.toFixed(2)}/gm).`
  if (streak?.is_notable && streak.run_word) s += ` Recent form: a ${streak.run_word}.`
  return s
}

function OverviewTab({ teamDetail, teamColor, streakCard }: {
  teamDetail: TeamDetail; teamColor: string; streakCard: StreakCard | null
}) {
  const xgfShare = teamDetail.xgf_per60 + teamDetail.xga_per60 > 0
    ? teamDetail.xgf_per60 / (teamDetail.xgf_per60 + teamDetail.xga_per60) : null
  return (
    <div className="team-profile__content">
      <p className="team-profile__verdict">{teamVerdict(teamDetail, streakCard)}</p>

      <div className="team-profile__section">
        <h2 className="team-profile__section-title">Performance Profile</h2>
        <p className="team-profile__section-sub">Percentile rank across six dimensions vs the league — the dashed polygon is the league median.</p>
        <ChartPanel title="How this team is built">
          <TeamRadar teamDetail={teamDetail} color={teamColor} />
        </ChartPanel>
      </div>

      <div className="team-profile__section">
        <h2 className="team-profile__section-title">Season Snapshot</h2>
        <div className="team-profile__stat-grid">
          <StatCard label="CF%" value={(teamDetail.cf_pct * 100).toFixed(1) + '%'} rank={teamDetail.cf_pct_rank} tooltip="Corsi For % — share of unblocked + blocked shot attempts at 5v5." />
          <StatCard label="xGF%" value={xgfShare != null ? (xgfShare * 100).toFixed(1) + '%' : '—'} rank={teamDetail.xgf_pct_rank} tooltip="Expected-goals share at 5v5." />
          <StatCard label="HDCF/60" value={teamDetail.hdcf_per60.toFixed(1)} rank={teamDetail.hdcf_per60_rank} tooltip="High-danger chances FOR per 60 minutes." />
          <StatCard label="HDCA/60" value={teamDetail.hdca_per60.toFixed(1)} rank={teamDetail.hdca_per60_rank} tooltip="High-danger chances AGAINST per 60 (lower is better)." />
          <StatCard label="GF/GP" value={(teamDetail.total_goals_for / teamDetail.games_played).toFixed(2)} rank={teamDetail.gf_per_gp_rank} />
          <StatCard label="GA/GP" value={(teamDetail.total_goals_against / teamDetail.games_played).toFixed(2)} rank={teamDetail.ga_per_gp_rank} />
          {teamDetail.zone_entry_proxy_success_rate != null && (
            <StatCard label="Zone Entry % (proxy)" value={`${(teamDetail.zone_entry_proxy_success_rate * 100).toFixed(1)}%`} rank={teamDetail.zone_entry_proxy_success_rate_rank || undefined} tooltip="Derived proxy: inferred from consecutive event zone codes, not measured entries." />
          )}
          {teamDetail.faceoff_win_pct != null && (
            <StatCard label="Faceoff Win %" value={`${(teamDetail.faceoff_win_pct * 100).toFixed(1)}%`} tooltip="Share of faceoffs won (all situations)." />
          )}
        </div>
      </div>
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
