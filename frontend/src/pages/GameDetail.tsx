import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { PageLayout, SkeletonLoader, IdentityHeader, TabNav, PodiumCards, ComparisonRow, TimelineList, MiniWorm } from '../components/common'
import GameHeader from '../components/games/GameHeader'
import XGWormChart from '../components/visualizations/XGWormChart'
import BoxscoreSummary from '../components/visualizations/BoxscoreSummary'
import TeamComparisonPanel from '../components/visualizations/TeamComparisonPanel'
import ShotMapKDE from '../components/visualizations/ShotMapKDE'
import PeriodBreakdownTable from '../components/visualizations/PeriodBreakdownTable'
import GamePlayerStatsTable from '../components/visualizations/GamePlayerStatsTable'
import RollingContextPanel from '../components/visualizations/RollingContextPanel'
import { getGameDetail, getGamePlayerStats, getGameShots, getGameXGWorm } from '../api/games'
import { GameDetail as GameDetailType, GamePlayerStats, PlayerGameStats, GameShots, XGWormPoint, TeamGameStats } from '../api/types'
import { getTeamLogoUrl, getTeamColor } from '../utils/teams'
import './GameDetail.css'

function GameDetail() {
  const { gameId } = useParams<{ gameId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [gameDetail, setGameDetail] = useState<GameDetailType | null>(null)
  const [playerStats, setPlayerStats] = useState<GamePlayerStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Tab state from URL query params (default to 'overview')
  const activeTab = searchParams.get('tab') || 'overview'

  useEffect(() => {
    document.title = 'NHL Intel - Game Detail'
  }, [])

  useEffect(() => {
    if (!gameId) return

    const fetchData = async () => {
      setLoading(true)
      setError(null)

      try {
        const [detail, players] = await Promise.all([
          getGameDetail(parseInt(gameId)),
          getGamePlayerStats(parseInt(gameId))
        ])

        setGameDetail(detail)
        setPlayerStats(players)
      } catch (err) {
        console.error('Error fetching game data:', err)
        setError('Failed to load game data. Please try again.')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [gameId])

  const handleBack = () => {
    navigate('/games')
  }

  const handleRetry = () => {
    if (gameId) {
      window.location.reload()
    }
  }

  const handleTabChange = (tab: string) => {
    setSearchParams({ tab })
  }

  if (loading) {
    return (
      <PageLayout>
        <div className="game-detail">
          <div className="game-detail__header-skeleton">
            <div style={{ width: '200px', marginBottom: '24px', margin: '0 auto' }}>
              <SkeletonLoader height={40} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '40px' }}>
              <div style={{ width: '300px' }}>
                <SkeletonLoader height={80} />
              </div>
              <div style={{ width: '120px' }}>
                <SkeletonLoader height={60} />
              </div>
              <div style={{ width: '300px' }}>
                <SkeletonLoader height={80} />
              </div>
            </div>
          </div>
          <div className="game-detail__comparison-skeleton">
            <SkeletonLoader height={400} />
          </div>
          <div className="game-detail__roster-skeleton">
            <SkeletonLoader height={500} />
          </div>
        </div>
      </PageLayout>
    )
  }

  if (error || !gameDetail) {
    return (
      <PageLayout>
        <div className="game-detail__error">
          <p className="game-detail__error-message">
            {error || 'Game not found'}
          </p>
          <button className="game-detail__retry-button" onClick={handleRetry}>
            Retry
          </button>
          <button className="game-detail__back-button" onClick={handleBack}>
            Back to Games
          </button>
        </div>
      </PageLayout>
    )
  }

  const { is_preview, home_team, away_team } = gameDetail
  const homeTeamColor = getTeamColor(home_team.team_abbrev)
  const awayTeamColor = getTeamColor(away_team.team_abbrev)

  // Preview games: use old GameHeader (no tabs for Phase 1)
  if (is_preview) {
    return (
      <PageLayout>
        <div className="game-detail">
          <GameHeader gameDetail={gameDetail} />
          <PreviewModeContent gameDetail={gameDetail} playerStats={playerStats} />
        </div>
      </PageLayout>
    )
  }

  // Completed games: use IdentityHeader + TabNav
  const tabs = [
    { value: 'overview', label: 'Overview' },
    { value: 'analytics', label: 'Analytics' },
    { value: 'players', label: 'Players' }
  ]

  return (
    <PageLayout>
      <div className="game-detail">
        {/* Identity Header - following DevComponents approved pattern */}
        <IdentityHeader
          backLink={{
            label: `← Back to Games`,
            to: '/games'
          }}
          leftContent={
            <div>
              <img
                src={getTeamLogoUrl(away_team.team_abbrev)}
                alt={away_team.team_abbrev}
                style={{ width: 48, height: 48 }}
              />
              <div style={{ marginTop: 'var(--space-2)' }}>
                <div style={{ fontSize: 'var(--text-lg)', fontWeight: 600 }}>
                  {away_team.team_abbrev}
                </div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
                  Away
                </div>
              </div>
            </div>
          }
          centerContent={
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 'var(--text-4xl)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                {away_team.score ?? 0} - {home_team.score ?? 0}
              </div>
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
                Final
              </div>
            </div>
          }
          rightContent={
            <div style={{ textAlign: 'right' }}>
              <img
                src={getTeamLogoUrl(home_team.team_abbrev)}
                alt={home_team.team_abbrev}
                style={{ width: 48, height: 48, marginLeft: 'auto' }}
              />
              <div style={{ marginTop: 'var(--space-2)' }}>
                <div style={{ fontSize: 'var(--text-lg)', fontWeight: 600 }}>
                  {home_team.team_abbrev}
                </div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
                  Home
                </div>
              </div>
            </div>
          }
          teamColors={{
            away: awayTeamColor,
            home: homeTeamColor
          }}
        />

        {/* Tab Navigation (sticky at top 56px) */}
        <TabNav
          tabs={tabs}
          activeTab={activeTab}
          onChange={handleTabChange}
        />

        {/* Tab Content */}
        <CompletedGameTabContent
          activeTab={activeTab}
          gameDetail={gameDetail}
          playerStats={playerStats}
          homeTeamColor={homeTeamColor}
          awayTeamColor={awayTeamColor}
        />
      </div>
    </PageLayout>
  )
}

// Tab content switcher for completed games
function CompletedGameTabContent({
  activeTab,
  gameDetail,
  playerStats,
  homeTeamColor,
  awayTeamColor
}: {
  activeTab: string
  gameDetail: GameDetailType
  playerStats: GamePlayerStats | null
  homeTeamColor: string
  awayTeamColor: string
}) {
  switch (activeTab) {
    case 'overview':
      return <OverviewTab gameDetail={gameDetail} playerStats={playerStats} />
    case 'analytics':
      return <AnalyticsTab gameDetail={gameDetail} playerStats={playerStats} homeTeamColor={homeTeamColor} awayTeamColor={awayTeamColor} />
    case 'players':
      return <PlayersTab gameDetail={gameDetail} playerStats={playerStats} homeTeamColor={homeTeamColor} awayTeamColor={awayTeamColor} />
    default:
      return <OverviewTab gameDetail={gameDetail} playerStats={playerStats} />
  }
}

// Overview Tab - Complete implementation with additional data fetching
function OverviewTab({
  gameDetail,
  playerStats
}: {
  gameDetail: GameDetailType
  playerStats: GamePlayerStats | null
}) {
  const { home_team, away_team, venue_name, game_date, game_id } = gameDetail
  const homeColor = getTeamColor(home_team.team_abbrev)
  const awayColor = getTeamColor(away_team.team_abbrev)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // Lazy load shots and xG worm data for Overview tab
  const [shotsData, setShotsData] = useState<GameShots | null>(null)
  const [xgWormData, setXgWormData] = useState<XGWormPoint[]>([])
  const [dataLoading, setDataLoading] = useState(true)

  useEffect(() => {
    const fetchOverviewData = async () => {
      setDataLoading(true)
      try {
        const [shots, worm] = await Promise.all([
          getGameShots(game_id),
          getGameXGWorm(game_id)
        ])
        setShotsData(shots)
        setXgWormData(worm)
      } catch (err) {
        console.error('Error fetching overview data:', err)
      } finally {
        setDataLoading(false)
      }
    }

    fetchOverviewData()
  }, [game_id])

  const handleNavigateToAnalytics = () => {
    searchParams.set('tab', 'analytics')
    navigate({ search: searchParams.toString() })
  }

  return (
    <div style={{ maxWidth: '1280px', margin: '0 auto', padding: 'var(--space-8)' }}>
      {/* Section 1: Top Performers */}
      {playerStats && <TopPerformersSection playerStats={playerStats} homeTeam={home_team} awayTeam={away_team} />}

      {/* Section 2: Scoring Summary */}
      {!dataLoading && shotsData && (
        <ScoringSummarySection shotsData={shotsData} homeTeam={home_team} awayTeam={away_team} />
      )}

      {/* Section 3: Team Stats */}
      <TeamStatsSection homeTeam={home_team} awayTeam={away_team} homeColor={homeColor} awayColor={awayColor} />

      {/* Section 4: Goaltending */}
      {!dataLoading && shotsData && playerStats && (
        <GoaltendingSection shotsData={shotsData} playerStats={playerStats} homeTeam={home_team} awayTeam={away_team} />
      )}

      {/* Section 5: Game Flow Teaser */}
      {!dataLoading && xgWormData.length > 0 && (
        <GameFlowSection xgWormData={xgWormData} homeTeam={home_team} awayTeam={away_team} onNavigate={handleNavigateToAnalytics} />
      )}

      {/* Section 6: Game Details */}
      <GameDetailsSection venue={venue_name} gameDate={game_date} />
    </div>
  )
}

// Scoring Summary Section - goals from shots data
function ScoringSummarySection({
  shotsData,
  homeTeam,
  awayTeam
}: {
  shotsData: GameShots
  homeTeam: TeamGameStats
  awayTeam: TeamGameStats
}) {
  // Extract goals from shots
  const allShots = [...shotsData.home_shots, ...shotsData.away_shots]
  const goals = allShots
    .filter(shot => shot.outcome === 'goal' && shot.period && shot.time_in_period && shot.scorer_name)
    .sort((a, b) => {
      if (a.period !== b.period) return (a.period || 0) - (b.period || 0)
      // Sort by time within period (earlier first)
      return (a.time_in_period || '').localeCompare(b.time_in_period || '')
    })

  if (goals.length === 0) return null

  // Group by period
  const periods = [...new Set(goals.map(g => g.period))]
  const groups = periods.map(period => {
    const periodGoals = goals.filter(g => g.period === period)

    const periodLabel = period === 4 ? 'OT' : period && period > 4 ? `${period - 3}OT` : `Period ${period}`

    const items = periodGoals.map(goal => {
      const teamAbbrev = goal.team_id === homeTeam.team_id ? homeTeam.team_abbrev : awayTeam.team_abbrev
      const teamColor = getTeamColor(teamAbbrev)

      // Build assists string
      let assistsText = ''
      if (goal.assist1_name && goal.assist2_name) {
        assistsText = ` (${goal.assist1_name}, ${goal.assist2_name})`
      } else if (goal.assist1_name) {
        assistsText = ` (${goal.assist1_name})`
      }

      return {
        id: `${goal.period}-${goal.time_in_period}-${goal.scorer_id}`,
        leftContent: (
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <img src={getTeamLogoUrl(teamAbbrev)} alt={teamAbbrev} style={{ width: '16px', height: '16px' }} />
            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)', fontWeight: 500 }}>
              {goal.scorer_name}{assistsText}
            </span>
          </div>
        ),
        rightContent: (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}>
            {goal.time_in_period}
          </span>
        ),
        accentColor: teamColor
      }
    })

    return {
      label: periodLabel,
      items
    }
  })

  return (
    <section style={{ marginBottom: 'var(--space-12)' }}>
      <h2 style={{
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'var(--color-text-muted)',
        marginBottom: 'var(--space-6)'
      }}>
        Scoring Summary
      </h2>
      <TimelineList groups={groups} />
    </section>
  )
}

// Goaltending Section - calculate stats from shots data
function GoaltendingSection({
  shotsData,
  playerStats,
  homeTeam,
  awayTeam
}: {
  shotsData: GameShots
  playerStats: GamePlayerStats
  homeTeam: TeamGameStats
  awayTeam: TeamGameStats
}) {
  // Get goalies from player stats
  const goalies = [...playerStats.home_players, ...playerStats.away_players]
    .filter(p => p.position === 'G')

  if (goalies.length === 0) return null

  // Calculate saves and goals against for each goalie
  const goalieStats = goalies.map(goalie => {
    const isHome = goalie.team_id === homeTeam.team_id
    const teamAbbrev = isHome ? homeTeam.team_abbrev : awayTeam.team_abbrev
    const teamColor = getTeamColor(teamAbbrev)

    // Count shots against this goalie
    const opposingShots = isHome ? shotsData.away_shots : shotsData.home_shots
    const shotsAgainst = opposingShots.filter(shot => shot.goalie_id === goalie.player_id)
    const goalsAgainst = shotsAgainst.filter(shot => shot.outcome === 'goal').length
    const saves = shotsAgainst.filter(shot => shot.outcome === 'shot_on_goal').length
    const shotsOnGoal = saves + goalsAgainst
    const savePercentage = shotsOnGoal > 0 ? ((saves / shotsOnGoal) * 100).toFixed(1) : '0.0'

    return {
      ...goalie,
      teamAbbrev,
      teamColor,
      shotsAgainst: shotsOnGoal,
      goalsAgainst,
      saves,
      savePercentage
    }
  })

  return (
    <section style={{ marginBottom: 'var(--space-12)' }}>
      <h2 style={{
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'var(--color-text-muted)',
        marginBottom: 'var(--space-6)'
      }}>
        Goaltending
      </h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--space-4)' }}>
        {goalieStats.map(goalie => (
          <div
            key={goalie.player_id}
            style={{
              background: 'var(--color-bg-elevated)',
              borderRadius: 'var(--radius-lg)',
              padding: 'var(--space-6)',
              borderTop: `3px solid ${goalie.teamColor}`
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
              <img src={getTeamLogoUrl(goalie.teamAbbrev)} alt={goalie.teamAbbrev} style={{ width: '16px', height: '16px' }} />
              <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text-primary)' }}>
                {goalie.player_name}
              </h3>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-6)', fontSize: 'var(--text-sm)' }}>
              <div>
                <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', marginBottom: 'var(--space-1)' }}>SA</div>
                <div style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{goalie.shotsAgainst}</div>
              </div>
              <div>
                <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', marginBottom: 'var(--space-1)' }}>GA</div>
                <div style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{goalie.goalsAgainst}</div>
              </div>
              <div>
                <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', marginBottom: 'var(--space-1)' }}>SV</div>
                <div style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{goalie.saves}</div>
              </div>
              <div>
                <div style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)', marginBottom: 'var(--space-1)' }}>SV%</div>
                <div style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{goalie.savePercentage}%</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

// Game Flow Section - MiniWorm teaser with link to Analytics tab
function GameFlowSection({
  xgWormData,
  homeTeam,
  awayTeam,
  onNavigate
}: {
  xgWormData: XGWormPoint[]
  homeTeam: TeamGameStats
  awayTeam: TeamGameStats
  onNavigate: () => void
}) {
  const homeColor = getTeamColor(homeTeam.team_abbrev)
  const awayColor = getTeamColor(awayTeam.team_abbrev)

  // Transform XGWormPoint data to MiniWorm format
  const miniWormData = xgWormData.map(point => ({
    time: point.game_time_seconds,
    diff: point.cumulative_xg_diff
  }))

  // Generate insight based on final xG differential
  const finalPoint = xgWormData[xgWormData.length - 1]
  const xgDiff = finalPoint?.cumulative_xg_diff || 0
  const leadingTeam = xgDiff > 0 ? homeTeam.team_abbrev : awayTeam.team_abbrev
  const insight = Math.abs(xgDiff) > 0.5
    ? `${leadingTeam} controlled game flow with a +${Math.abs(xgDiff).toFixed(2)} expected goals advantage.`
    : 'Game flow was evenly matched throughout regulation.'

  return (
    <section style={{ marginBottom: 'var(--space-12)' }}>
      <h2 style={{
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'var(--color-text-muted)',
        marginBottom: 'var(--space-6)'
      }}>
        Game Flow
      </h2>
      <div
        onClick={onNavigate}
        style={{
          background: 'var(--color-bg-elevated)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-6)',
          cursor: 'pointer',
          transition: 'background 150ms ease'
        }}
        onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-bg-hover)'}
        onMouseLeave={(e) => e.currentTarget.style.background = 'var(--color-bg-elevated)'}
      >
        <MiniWorm
          data={miniWormData}
          homeColor={homeColor}
          awayColor={awayColor}
        />
        <p style={{ marginTop: 'var(--space-4)', fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
          {insight}
        </p>
        <div style={{ marginTop: 'var(--space-4)', fontSize: 'var(--text-sm)', color: 'var(--color-accent)', fontWeight: 500 }}>
          View full analytics →
        </div>
      </div>
    </section>
  )
}

// Top Performers Section - selects top 3 players using heuristic
function TopPerformersSection({
  playerStats,
  homeTeam,
  awayTeam
}: {
  playerStats: GamePlayerStats
  homeTeam: TeamGameStats
  awayTeam: TeamGameStats
}) {
  // Combine all players
  const allPlayers = [...playerStats.home_players, ...playerStats.away_players]

  // Filter out goalies for now (position === 'G'), sort skaters by points desc, then ixG desc
  const skaters = allPlayers
    .filter(p => p.position !== 'G')
    .sort((a, b) => {
      const pointsA = (a.points || 0)
      const pointsB = (b.points || 0)
      if (pointsB !== pointsA) return pointsB - pointsA
      return (b.ixg || 0) - (a.ixg || 0)
    })

  // Select top 3 skaters
  const topPerformers = skaters.slice(0, 3)

  if (topPerformers.length === 0) return null

  // Format for PodiumCards
  const podiumPlayers = topPerformers.map(player => {
    const teamAbbrev = player.team_id === homeTeam.team_id ? homeTeam.team_abbrev : awayTeam.team_abbrev
    const teamColor = getTeamColor(teamAbbrev)

    // Format TOI from seconds to mm:ss
    const toiMinutes = player.toi ? Math.floor(player.toi / 60) : 0
    const toiSeconds = player.toi ? Math.floor(player.toi % 60) : 0
    const toiFormatted = `${toiMinutes}:${toiSeconds.toString().padStart(2, '0')}`

    const statLine = `${player.goals || 0}G · ${player.assists || 0}A · ${toiFormatted} TOI`

    return {
      playerId: player.player_id,
      name: player.player_name,
      teamAbbrev,
      teamLogo: getTeamLogoUrl(teamAbbrev),
      position: player.position,
      statLine,
      highlight: `${player.points || 0} ${(player.points || 0) === 1 ? 'point' : 'points'}`,
      accentColor: teamColor
    }
  })

  return (
    <section style={{ marginBottom: 'var(--space-12)' }}>
      <h2 style={{
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'var(--color-text-muted)',
        marginBottom: 'var(--space-6)'
      }}>
        Top Performers
      </h2>
      <PodiumCards players={podiumPlayers} />
    </section>
  )
}

// Team Stats Section - comparison rows
function TeamStatsSection({
  homeTeam,
  awayTeam,
  homeColor,
  awayColor
}: {
  homeTeam: TeamGameStats
  awayTeam: TeamGameStats
  homeColor: string
  awayColor: string
}) {
  const stats = [
    {
      label: 'Shots on Goal',
      awayValue: awayTeam.shots_on_goal?.toString() || '0',
      homeValue: homeTeam.shots_on_goal?.toString() || '0',
      awayRaw: awayTeam.shots_on_goal || 0,
      homeRaw: homeTeam.shots_on_goal || 0,
      showBar: true
    },
    {
      label: 'Shot Attempts',
      awayValue: awayTeam.shot_attempts?.toString() || '0',
      homeValue: homeTeam.shot_attempts?.toString() || '0',
      awayRaw: awayTeam.shot_attempts || 0,
      homeRaw: homeTeam.shot_attempts || 0,
      showBar: true
    },
    {
      label: 'Expected Goals',
      awayValue: awayTeam.xgf?.toFixed(2) || '0.00',
      homeValue: homeTeam.xgf?.toFixed(2) || '0.00',
      awayRaw: awayTeam.xgf || 0,
      homeRaw: homeTeam.xgf || 0,
      showBar: true
    }
  ]

  return (
    <section style={{ marginBottom: 'var(--space-12)' }}>
      <h2 style={{
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'var(--color-text-muted)',
        marginBottom: 'var(--space-6)'
      }}>
        Team Stats
      </h2>
      <div style={{
        background: 'var(--color-bg-elevated)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-6)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4)'
      }}>
        {stats.map((stat, index) => (
          <ComparisonRow
            key={index}
            label={stat.label}
            awayValue={stat.awayValue}
            homeValue={stat.homeValue}
            awayColor={awayColor}
            homeColor={homeColor}
            showBar={stat.showBar}
            awayRaw={stat.awayRaw}
            homeRaw={stat.homeRaw}
          />
        ))}
      </div>
    </section>
  )
}

// Game Details Section - single line
function GameDetailsSection({
  venue,
  gameDate
}: {
  venue: string | null
  gameDate: string
}) {
  const formattedDate = new Date(gameDate).toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })

  return (
    <section style={{ marginBottom: 'var(--space-8)' }}>
      <p style={{
        fontSize: 'var(--text-sm)',
        color: 'var(--color-text-muted)',
        textAlign: 'center'
      }}>
        {formattedDate}{venue && ` · ${venue}`}
      </p>
    </section>
  )
}

// Analytics Tab - Placeholder with existing visualizations
function AnalyticsTab({
  gameDetail,
  playerStats: _playerStats,
  homeTeamColor,
  awayTeamColor
}: {
  gameDetail: GameDetailType
  playerStats: GamePlayerStats | null
  homeTeamColor: string
  awayTeamColor: string
}) {
  const { home_team, away_team, game_id } = gameDetail
  const [situation, setSituation] = useState('all')

  return (
    <div style={{ padding: 'var(--space-8)', maxWidth: '1280px', margin: '0 auto' }}>
      <div style={{
        padding: 'var(--space-4)',
        background: 'var(--color-bg-elevated)',
        borderRadius: 'var(--radius-lg)',
        textAlign: 'center',
        color: 'var(--color-text-secondary)',
        marginBottom: 'var(--space-6)'
      }}>
        <p style={{ fontSize: 'var(--text-sm)' }}>
          Analytics Tab - Existing visualizations preserved below (will be reorganized in Phase 2/3)
        </p>
      </div>

      {/* Existing visualizations preserved here */}
      <div className="game-detail__content">
        <XGWormChart
          gameId={game_id}
          homeTeamAbbrev={home_team.team_abbrev}
          awayTeamAbbrev={away_team.team_abbrev}
          homeTeamColor={homeTeamColor}
          awayTeamColor={awayTeamColor}
        />

        <div className="game-detail__two-column">
          <BoxscoreSummary
            homeTeamAbbrev={home_team.team_abbrev}
            awayTeamAbbrev={away_team.team_abbrev}
            homeTeamColor={homeTeamColor}
            awayTeamColor={awayTeamColor}
            homeStats={{
              score: home_team.score,
              shots_on_goal: home_team.shots_on_goal,
              shot_attempts: home_team.shot_attempts
            }}
            awayStats={{
              score: away_team.score,
              shots_on_goal: away_team.shots_on_goal,
              shot_attempts: away_team.shot_attempts
            }}
          />

          <TeamComparisonPanel
            gameId={game_id}
            homeTeamId={home_team.team_id}
            awayTeamId={away_team.team_id}
            homeTeamAbbrev={home_team.team_abbrev}
            awayTeamAbbrev={away_team.team_abbrev}
            homeTeamColor={homeTeamColor}
            awayTeamColor={awayTeamColor}
            homeTeamStats={home_team}
            awayTeamStats={away_team}
            situation={situation}
            onSituationChange={setSituation}
          />
        </div>

        <ShotMapKDE
          gameId={game_id}
          homeTeamAbbrev={home_team.team_abbrev}
          awayTeamAbbrev={away_team.team_abbrev}
          homeTeamColor={homeTeamColor}
          awayTeamColor={awayTeamColor}
          situation={situation}
        />

        <div className="game-detail__two-column">
          <PeriodBreakdownTable
            homeTeamAbbrev={home_team.team_abbrev}
            awayTeamAbbrev={away_team.team_abbrev}
            homeTeamColor={homeTeamColor}
            awayTeamColor={awayTeamColor}
            homeStats={home_team}
            awayStats={away_team}
            situation={situation}
          />

          <RollingContextPanel
            gameId={game_id}
            homeTeamId={home_team.team_id}
            awayTeamId={away_team.team_id}
            homeTeamAbbrev={home_team.team_abbrev}
            awayTeamAbbrev={away_team.team_abbrev}
            homeTeamColor={homeTeamColor}
            awayTeamColor={awayTeamColor}
            homeGameCF={home_team.cf_pct}
            awayGameCF={away_team.cf_pct}
          />
        </div>
      </div>
    </div>
  )
}

// Players Tab - Placeholder with existing player stats table
function PlayersTab({
  gameDetail,
  playerStats,
  homeTeamColor,
  awayTeamColor
}: {
  gameDetail: GameDetailType
  playerStats: GamePlayerStats | null
  homeTeamColor: string
  awayTeamColor: string
}) {
  const { home_team, away_team } = gameDetail

  return (
    <div style={{ padding: 'var(--space-8)', maxWidth: '1280px', margin: '0 auto' }}>
      <div style={{
        padding: 'var(--space-4)',
        background: 'var(--color-bg-elevated)',
        borderRadius: 'var(--radius-lg)',
        textAlign: 'center',
        color: 'var(--color-text-secondary)',
        marginBottom: 'var(--space-6)'
      }}>
        <p style={{ fontSize: 'var(--text-sm)' }}>
          Players Tab - Existing player stats table preserved below (will be reorganized in Phase 2/3)
        </p>
      </div>

      {/* Existing player stats table preserved here */}
      {playerStats && (
        <GamePlayerStatsTable
          homeTeamAbbrev={home_team.team_abbrev}
          awayTeamAbbrev={away_team.team_abbrev}
          homeTeamColor={homeTeamColor}
          awayTeamColor={awayTeamColor}
          homePlayers={playerStats.home_players}
          awayPlayers={playerStats.away_players}
        />
      )}
    </div>
  )
}

function PlayerRow({ player }: { player: PlayerGameStats }) {
  const initials = player.player_name
    .split(' ')
    .map((n: string) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="player-row">
      <div className="player-row__info">
        <div className="player-row__avatar">{initials}</div>
        <div className="player-row__details">
          <div className="player-row__name">{player.player_name}</div>
          <div className="player-row__position">{player.position}</div>
        </div>
      </div>
    </div>
  );
}

function PreviewModeContent({
  gameDetail,
  playerStats
}: {
  gameDetail: GameDetailType
  playerStats: GamePlayerStats | null
}) {
  return (
    <>
      <section className="game-detail__preview-notice">
        <p>Game preview - stats will be available after the game is played</p>
      </section>

      {/* Roster Preview */}
      {playerStats && (
        <section className="game-detail__roster-section">
          <h2 className="game-detail__section-title">Rosters</h2>
          <div className="roster-section">
            <div className="roster-section__column">
              <div className="roster-section__header">
                <img
                  src={getTeamLogoUrl(gameDetail.away_team.team_abbrev)}
                  alt={gameDetail.away_team.team_abbrev}
                  className="roster-section__logo"
                />
                <span>{gameDetail.away_team.team_abbrev}</span>
              </div>
              <div className="roster-section__players">
                {playerStats.away_players.map((player) => (
                  <PlayerRow key={player.player_id} player={player} />
                ))}
              </div>
            </div>

            <div className="roster-section__column">
              <div className="roster-section__header">
                <img
                  src={getTeamLogoUrl(gameDetail.home_team.team_abbrev)}
                  alt={gameDetail.home_team.team_abbrev}
                  className="roster-section__logo"
                />
                <span>{gameDetail.home_team.team_abbrev}</span>
              </div>
              <div className="roster-section__players">
                {playerStats.home_players.map((player) => (
                  <PlayerRow key={player.player_id} player={player} />
                ))}
              </div>
            </div>
          </div>
        </section>
      )}
    </>
  )
}

export default GameDetail
