import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { PageLayout, SkeletonLoader, StatCard, Badge, IdentityHeader, ComponentStackBar } from '../components/common'
import type { StackSegment } from '../components/common'
import Tabs from '../components/common/Tabs'
import TeamIdentityTab from '../components/teams/TeamIdentityTab'
import TeamFormTab from '../components/teams/TeamFormTab'
import { StreakDoctorCard, LineSwapWidget } from '../components/common'
import { getTeamDetail, getTeamTrends, getTeamRoster, getTeamVsOpponent, getTeamStreak } from '../api/teams'
import { getPowerRankings } from '../api/rankings'
import { getTeamGames } from '../api/games'
import { TeamDetail, TeamTrends, TeamRoster, Game, TeamVsOpponent, StreakCard, PowerRatingRow } from '../api/types'
import { RATINGS_COMPONENTS } from '../config/metrics'
import { getTeamLogoUrl, getTeamName, getTeamColor, formatDateForAPI, setTeamPrimaryColor, clearTeamPrimaryColor } from '../utils/teams'
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
  const [selectedOpponent, setSelectedOpponent] = useState<number | null>(null)
  const [opponentStats, setOpponentStats] = useState<TeamVsOpponent | null>(null)
  const [streakCard, setStreakCard] = useState<StreakCard | null>(null)

  const [loading, setLoading] = useState(true)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [trendsError, setTrendsError] = useState<string | null>(null)
  const [rosterError, setRosterError] = useState<string | null>(null)
  const [opponentError, setOpponentError] = useState<string | null>(null)

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

  const handleOpponentSelect = async (opponentId: number) => {
    if (!teamId) return
    setSelectedOpponent(opponentId)
    setOpponentError(null)
    setOpponentStats(null)

    try {
      const stats = await getTeamVsOpponent(parseInt(teamId), opponentId)
      setOpponentStats(stats)
    } catch (err) {
      console.error('Error fetching opponent stats:', err)
      setOpponentError('Failed to load opponent stats.')
    }
  }

  const handleRetryOpponent = () => {
    if (selectedOpponent) {
      handleOpponentSelect(selectedOpponent)
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

    return [...players].sort((a, b) => {
      const aVal = a[sortConfig.key]
      const bVal = b[sortConfig.key]

      if (aVal === bVal) return 0

      const comparison = aVal > bVal ? 1 : -1
      return sortConfig.direction === 'asc' ? comparison : -comparison
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
                { value: 'form', label: 'Form' },
                { value: 'lines', label: 'Lines' },
                { value: 'performance', label: 'Performance' },
                { value: 'roster', label: 'Roster' },
                { value: 'matchups', label: 'Matchups' }
              ]}
              value={currentTab}
              onChange={handleTabChange}
            />
          </div>
        </div>

        {/* Tab Content */}
        {currentTab === 'overview' && (
          <OverviewTab
            teamDetail={teamDetail}
            teamTrends={teamTrends}
            trendsError={trendsError}
            handleRetryTrends={handleRetryTrends}
            selectedOpponent={selectedOpponent}
            opponentStats={opponentStats}
            opponentError={opponentError}
            handleOpponentSelect={handleOpponentSelect}
            handleRetryOpponent={handleRetryOpponent}
            teamColor={teamColor}
          />
        )}

        {/* Power-rating component breakdown — the full four-part split lives here (Phase 3.1) */}
        {currentTab === 'overview' && teamId && (
          <div style={{ maxWidth: 760, margin: '0 auto', padding: '0 var(--space-6, 24px) var(--space-4, 16px)' }}>
            <TeamPowerCard teamId={parseInt(teamId)} />
          </div>
        )}

        {/* Auto-surface a notable run on the Overview tab (Phase 3.3) */}
        {currentTab === 'overview' && streakCard?.is_notable && (
          <div style={{ maxWidth: 760, margin: '0 auto', padding: '0 var(--space-6, 24px) var(--space-4, 16px)' }}>
            <StreakDoctorCard card={streakCard} />
          </div>
        )}

        {currentTab === 'identity' && teamId && (
          <TeamIdentityTab teamId={parseInt(teamId)} />
        )}

        {currentTab === 'form' && teamId && (
          <TeamFormTab teamId={parseInt(teamId)} />
        )}

        {currentTab === 'lines' && teamId && (
          <div className="team-profile__section">
            <h2 className="team-profile__section-title">Line Lab</h2>
            <LineSwapWidget teamId={parseInt(teamId)} />
          </div>
        )}

        {currentTab === 'performance' && (
          <PerformanceTab />
        )}

        {currentTab === 'roster' && (
          <RosterTab
            teamRoster={teamRoster}
            rosterError={rosterError}
            handleRetryRoster={handleRetryRoster}
            sortConfig={sortConfig}
            handleSort={handleSort}
            sortPlayers={sortPlayers}
            navigate={navigate}
          />
        )}

        {currentTab === 'matchups' && (
          <MatchupsTab />
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
function OverviewTab({
  teamDetail,
  teamTrends,
  trendsError,
  handleRetryTrends,
  selectedOpponent,
  opponentStats,
  opponentError,
  handleOpponentSelect,
  handleRetryOpponent,
  teamColor
}: {
  teamDetail: TeamDetail
  teamTrends: TeamTrends | null
  trendsError: string | null
  handleRetryTrends: () => void
  selectedOpponent: number | null
  opponentStats: TeamVsOpponent | null
  opponentError: string | null
  handleOpponentSelect: (opponentId: number) => void
  handleRetryOpponent: () => void
  teamColor: string
}) {
  return (
    <div className="team-profile__content">
      {/* Season Snapshot */}
      <div className="team-profile__section">
        <h2 className="team-profile__section-title">Season Snapshot</h2>
        <div className="team-profile__stat-grid">
          <StatCard
            label="CF%"
            value={(teamDetail.cf_pct * 100).toFixed(1) + '%'}
            rank={teamDetail.cf_pct_rank}
          />
          <StatCard
            label="xGF%"
            value={((teamDetail.xgf_per60 / (teamDetail.xgf_per60 + teamDetail.xga_per60)) * 100).toFixed(1) + '%'}
            rank={teamDetail.xgf_pct_rank}
          />
          <StatCard
            label="HDCF/60"
            value={teamDetail.hdcf_per60.toFixed(2)}
            rank={teamDetail.hdcf_per60_rank}
          />
          <StatCard
            label="HDCA/60"
            value={teamDetail.hdca_per60.toFixed(2)}
            rank={teamDetail.hdca_per60_rank}
          />
          <StatCard
            label="GF/GP"
            value={(teamDetail.total_goals_for / teamDetail.games_played).toFixed(2)}
            rank={teamDetail.gf_per_gp_rank}
          />
          <StatCard
            label="GA/GP"
            value={(teamDetail.total_goals_against / teamDetail.games_played).toFixed(2)}
            rank={teamDetail.ga_per_gp_rank}
          />
          {teamDetail.zone_entry_proxy_success_rate != null && (
            <StatCard
              label="Zone Entry Success (proxy)"
              value={`${(teamDetail.zone_entry_proxy_success_rate * 100).toFixed(1)}%`}
              rank={teamDetail.zone_entry_proxy_success_rate_rank || undefined}
            />
          )}
          {teamDetail.faceoff_win_pct != null && (
            <StatCard
              label="Faceoff Win %"
              value={`${(teamDetail.faceoff_win_pct * 100).toFixed(1)}%`}
            />
          )}
        </div>
      </div>

      {/* Season Trends - Chart 1: CF% and xGF% */}
      <div className="team-profile__section">
        <h2 className="team-profile__section-title">Possession Trends (5-Game Rolling)</h2>
        {trendsError ? (
          <div className="team-profile__section-error">
            <p>{trendsError}</p>
            <button onClick={handleRetryTrends} className="team-profile__retry-button">
              Retry
            </button>
          </div>
        ) : teamTrends && teamTrends.cf_pct_5gp.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart
              data={teamTrends.cf_pct_5gp.map((point, i) => ({
                date: new Date(point.game_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                cf_pct: point.value * 100,
                xgf_pct: teamTrends.xgf_pct_5gp[i]?.value * 100 || 50
              }))}
              margin={{ right: 60 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="date"
                stroke="var(--color-text-muted)"
                style={{ fontSize: 'var(--text-xs)' }}
              />
              <YAxis
                stroke="var(--color-text-muted)"
                style={{ fontSize: 'var(--text-xs)' }}
                domain={[40, 60]}
                tickFormatter={(value) => Math.round(value).toString()}
              />
              <RechartsTooltip
                formatter={(value) => typeof value === 'number' ? `${value.toFixed(1)}%` : ''}
                contentStyle={{
                  backgroundColor: 'var(--color-bg-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-md)'
                }}
              />
              <ReferenceLine y={50} stroke="var(--color-text-muted)" strokeDasharray="3 3" />
              <Line
                type="monotone"
                dataKey="cf_pct"
                stroke={teamColor}
                strokeWidth={2}
                dot={false}
                name="CF%"
              >
                <Label
                  value="CF%"
                  position="insideBottomRight"
                  offset={15}
                  fill={teamColor}
                  style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}
                />
              </Line>
              <Line
                type="monotone"
                dataKey="xgf_pct"
                stroke="var(--color-accent)"
                strokeWidth={2}
                dot={false}
                name="xGF%"
              >
                <Label
                  value="xGF%"
                  position="insideBottomRight"
                  fill="var(--color-accent)"
                  style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}
                />
              </Line>
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="team-profile__no-data">Insufficient data for trends</div>
        )}
      </div>

      {/* Season Trends - Chart 2: HDCF/60 vs HDCA/60 */}
      <div className="team-profile__section">
        <h2 className="team-profile__section-title">High Danger Chances For (5-Game Rolling)</h2>
        {trendsError ? (
          <div className="team-profile__section-error">
            <p>{trendsError}</p>
            <button onClick={handleRetryTrends} className="team-profile__retry-button">
              Retry
            </button>
          </div>
        ) : teamTrends && teamTrends.hdcf_per60_5gp.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart
              data={teamTrends.hdcf_per60_5gp.map((point) => ({
                date: new Date(point.game_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                hdcf: point.value
              }))}
              margin={{ right: 80 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="date"
                stroke="var(--color-text-muted)"
                style={{ fontSize: 'var(--text-xs)' }}
              />
              <YAxis
                stroke="var(--color-text-muted)"
                style={{ fontSize: 'var(--text-xs)' }}
                tickFormatter={(value) => Math.round(value).toString()}
              />
              <RechartsTooltip
                formatter={(value) => typeof value === 'number' ? value.toFixed(2) : ''}
                contentStyle={{
                  backgroundColor: 'var(--color-bg-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-md)'
                }}
              />
              <Line
                type="monotone"
                dataKey="hdcf"
                stroke="var(--color-data-positive)"
                strokeWidth={2}
                dot={false}
                name="HDCF/60"
              >
                <Label
                  value="HDCF/60"
                  position="insideBottomRight"
                  offset={15}
                  fill="var(--color-data-positive)"
                  style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}
                />
              </Line>
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="team-profile__no-data">Insufficient data for trends</div>
        )}
      </div>

      {/* vs Opponent Section */}
      <div className="team-profile__section">
        <h2 className="team-profile__section-title">vs Opponent</h2>
        {!selectedOpponent ? (
          <div className="team-profile__vs-opponent-prompt">
            <p>Select an opponent to view head-to-head stats</p>
            <select
              className="team-profile__vs-opponent-select"
              onChange={(e) => handleOpponentSelect(parseInt(e.target.value))}
              defaultValue=""
            >
              <option value="" disabled>
                Choose opponent...
              </option>
              {/* NHL Teams - hardcoded for now */}
              <option value="1">New Jersey Devils</option>
              <option value="2">New York Islanders</option>
              <option value="3">New York Rangers</option>
              <option value="4">Philadelphia Flyers</option>
              <option value="5">Pittsburgh Penguins</option>
              <option value="6">Boston Bruins</option>
              <option value="7">Buffalo Sabres</option>
              <option value="8">Montreal Canadiens</option>
              <option value="9">Ottawa Senators</option>
              <option value="10">Toronto Maple Leafs</option>
            </select>
          </div>
        ) : opponentError ? (
          <div className="team-profile__section-error">
            <p>{opponentError}</p>
            <button onClick={handleRetryOpponent} className="team-profile__retry-button">
              Retry
            </button>
          </div>
        ) : opponentStats ? (
          <div className="team-profile__vs-opponent-stats">
            {opponentStats.small_sample && (
              <div className="team-profile__small-sample-badge">
                <Badge variant="small-sample" />
                <span className="team-profile__small-sample-text">
                  {opponentStats.games_played} {opponentStats.games_played === 1 ? 'game' : 'games'} played
                </span>
              </div>
            )}
            <div className="team-profile__stat-grid">
              <StatCard
                label="Record"
                value={`${opponentStats.wins}-${opponentStats.losses}-${opponentStats.otl}`}
              />
              <StatCard
                label="CF%"
                value={opponentStats.cf_pct != null ? `${(opponentStats.cf_pct * 100).toFixed(1)}%` : '—'}
                tooltip={opponentStats.cf_pct == null ? 'Not enough games against this opponent to report CF%' : undefined}
              />
              <StatCard
                label="HDCF/60"
                value={opponentStats.hdcf_per60 != null ? opponentStats.hdcf_per60.toFixed(2) : '—'}
                tooltip={opponentStats.hdcf_per60 == null ? 'Not enough games against this opponent to report HDCF/60' : undefined}
              />
              <StatCard
                label="xGF/60"
                value={opponentStats.xgf_per60 != null ? opponentStats.xgf_per60.toFixed(2) : '—'}
                tooltip={opponentStats.xgf_per60 == null ? 'Not enough games against this opponent to report xGF/60' : undefined}
              />
            </div>
            <button
              className="team-profile__vs-opponent-change"
              onClick={() => handleOpponentSelect(0)}
            >
              Change Opponent
            </button>
          </div>
        ) : (
          <div className="team-profile__no-data">Loading opponent stats...</div>
        )}
      </div>
    </div>
  )
}

// Performance Tab Placeholder
function PerformanceTab() {
  return (
    <div className="team-profile__content">
      <div className="team-profile__section">
        <p style={{ textAlign: 'center', color: 'var(--color-text-muted)', padding: 'var(--space-16)' }}>
          Performance tab content coming in PART 6
        </p>
      </div>
    </div>
  )
}

// Roster Tab Component
function RosterTab({
  teamRoster,
  rosterError,
  handleRetryRoster,
  sortConfig,
  handleSort,
  sortPlayers,
  navigate
}: {
  teamRoster: TeamRoster | null
  rosterError: string | null
  handleRetryRoster: () => void
  sortConfig: { key: string; direction: 'asc' | 'desc' }
  handleSort: (key: string) => void
  sortPlayers: (players: any[]) => any[]
  navigate: (path: string) => void
}) {
  return (
    <div className="team-profile__content">
      <div className="team-profile__section">
        <h2 className="team-profile__section-title">Roster</h2>
        {rosterError ? (
          <div className="team-profile__section-error">
            <p>{rosterError}</p>
            <button onClick={handleRetryRoster} className="team-profile__retry-button">
              Retry
            </button>
          </div>
        ) : teamRoster ? (
          <div className="team-profile__roster">
            {/* Forwards */}
            {teamRoster.forwards.length > 0 && (
              <div className="team-profile__roster-section">
                <h3 className="team-profile__roster-heading">Forwards</h3>
                <table className="team-profile__roster-table">
                  <thead>
                    <tr>
                      <th onClick={() => handleSort('player_name')} className="team-profile__roster-sortable">
                        Player {sortConfig.key === 'player_name' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('games_played')} className="team-profile__roster-table-number team-profile__roster-sortable">
                        GP {sortConfig.key === 'games_played' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('toi_per_gp')} className="team-profile__roster-table-number team-profile__roster-sortable">
                        TOI/GP {sortConfig.key === 'toi_per_gp' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('points_per60')} className="team-profile__roster-table-number team-profile__roster-sortable">
                        PTS/60 {sortConfig.key === 'points_per60' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('cf_pct')} className="team-profile__roster-table-number team-profile__roster-sortable hide-mobile">
                        CF% {sortConfig.key === 'cf_pct' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortPlayers(teamRoster.forwards).map((player) => (
                      <tr
                        key={player.player_id}
                        className="team-profile__roster-row"
                        onClick={() => navigate(`/players/${player.player_id}`)}
                      >
                        <td>{player.player_name}</td>
                        <td className="team-profile__roster-table-number mono">{player.games_played}</td>
                        <td className="team-profile__roster-table-number mono">{player.toi_per_gp.toFixed(1)}</td>
                        <td className="team-profile__roster-table-number mono">{player.points_per60.toFixed(2)}</td>
                        <td className="team-profile__roster-table-number mono hide-mobile">
                          {(player.cf_pct * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Defensemen */}
            {teamRoster.defensemen.length > 0 && (
              <div className="team-profile__roster-section">
                <h3 className="team-profile__roster-heading">Defensemen</h3>
                <table className="team-profile__roster-table">
                  <thead>
                    <tr>
                      <th onClick={() => handleSort('player_name')} className="team-profile__roster-sortable">
                        Player {sortConfig.key === 'player_name' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('games_played')} className="team-profile__roster-table-number team-profile__roster-sortable">
                        GP {sortConfig.key === 'games_played' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('toi_per_gp')} className="team-profile__roster-table-number team-profile__roster-sortable">
                        TOI/GP {sortConfig.key === 'toi_per_gp' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('points_per60')} className="team-profile__roster-table-number team-profile__roster-sortable">
                        PTS/60 {sortConfig.key === 'points_per60' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('cf_pct')} className="team-profile__roster-table-number team-profile__roster-sortable hide-mobile">
                        CF% {sortConfig.key === 'cf_pct' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortPlayers(teamRoster.defensemen).map((player) => (
                      <tr
                        key={player.player_id}
                        className="team-profile__roster-row"
                        onClick={() => navigate(`/players/${player.player_id}`)}
                      >
                        <td>{player.player_name}</td>
                        <td className="team-profile__roster-table-number mono">{player.games_played}</td>
                        <td className="team-profile__roster-table-number mono">{player.toi_per_gp.toFixed(1)}</td>
                        <td className="team-profile__roster-table-number mono">{player.points_per60.toFixed(2)}</td>
                        <td className="team-profile__roster-table-number mono hide-mobile">
                          {(player.cf_pct * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Goalies */}
            {teamRoster.goalies.length > 0 && (
              <div className="team-profile__roster-section">
                <h3 className="team-profile__roster-heading">Goalies</h3>
                <table className="team-profile__roster-table">
                  <thead>
                    <tr>
                      <th onClick={() => handleSort('player_name')} className="team-profile__roster-sortable">
                        Player {sortConfig.key === 'player_name' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('games_played')} className="team-profile__roster-table-number team-profile__roster-sortable">
                        GP {sortConfig.key === 'games_played' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                      <th onClick={() => handleSort('toi_per_gp')} className="team-profile__roster-table-number team-profile__roster-sortable">
                        TOI/GP {sortConfig.key === 'toi_per_gp' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortPlayers(teamRoster.goalies).map((player) => (
                      <tr
                        key={player.player_id}
                        className="team-profile__roster-row"
                        onClick={() => navigate(`/players/${player.player_id}`)}
                      >
                        <td>{player.player_name}</td>
                        <td className="team-profile__roster-table-number mono">{player.games_played}</td>
                        <td className="team-profile__roster-table-number mono">{player.toi_per_gp.toFixed(1)}</td>
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

// Matchups Tab Placeholder
function MatchupsTab() {
  return (
    <div className="team-profile__content">
      <div className="team-profile__section">
        <p style={{ textAlign: 'center', color: 'var(--color-text-muted)', padding: 'var(--space-16)' }}>
          Matchups tab content coming in PART 7
        </p>
      </div>
    </div>
  )
}

export default TeamProfile
