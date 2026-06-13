import { useState, useEffect } from 'react'
import { Calendar, MapPin, Lightbulb } from 'lucide-react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { PageLayout, SkeletonLoader, IdentityHeader, TabNav, PodiumCards, ComparisonRow } from '../components/common'
import Badge from '../components/common/Badge'
import GameTimelineStack from '../components/visualizations/GameTimelineStack'
import ShotMapKDE from '../components/visualizations/ShotMapKDE'
import PeriodBreakdownTable from '../components/visualizations/PeriodBreakdownTable'
import RollingContextPanel from '../components/visualizations/RollingContextPanel'
import { getGameDetail, getGamePlayerStats, getGameTeamStats, getGameGoals, getGameGoaltending, getGamePressure, getGameSpecialTeams, getGameGoalieDanger, getGameShotQuality, getGameSkaterImpact } from '../api/games'
import { GameDetail as GameDetailType, GamePlayerStats, PlayerGameStats, TeamGameStats, TeamComparisonStats, GoalDetail, GoaltenderStat, PressurePoint, SpecialTeamsStat, GoalieDangerStat, ShotQualityRow, SkaterImpact } from '../api/types'
import { getTeamLogoUrl, getTeamColor, getPlayerHeadshotUrl } from '../utils/teams'
import './GameDetail.css'

// NHL game ids encode the type in the 5th-6th digits: 01 preseason, 02 regular, 03 playoffs.
function gameTypeLabel(gameId: number): string {
  const t = String(gameId).slice(4, 6)
  if (t === '03') return 'Playoffs'
  if (t === '01') return 'Preseason'
  if (t === '02') return 'Regular Season'
  return ''
}

// For playoff games, ids encode round + series + game in the final digits (e.g. ...0415 = Cup Final, Game 5).
function seriesLabel(gameId: number): string | null {
  const s = String(gameId)
  if (s.slice(4, 6) !== '03') return null
  const roundNames: Record<string, string> = { '1': 'Round 1', '2': 'Round 2', '3': 'Conf. Final', '4': 'Cup Final' }
  const round = roundNames[s[7]] || 'Playoffs'
  const game = parseInt(s[9], 10)
  return Number.isNaN(game) ? round : `${round} · Game ${game}`
}

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

  // Preview games: single focused preview page (no tabs)
  if (is_preview) {
    return (
      <PageLayout>
        <div className="game-detail">
          {/* Preview Header */}
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
                <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 500, color: 'var(--color-text-muted)' }}>
                  vs
                </div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', marginTop: 'var(--space-2)' }}>
                  {new Date(gameDetail.game_date).toLocaleDateString('en-US', {
                    weekday: 'long',
                    month: 'long',
                    day: 'numeric'
                  })}
                </div>
                <Badge variant="preview" />
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

          <PreviewModeContent
            gameDetail={gameDetail}
            playerStats={playerStats}
            homeTeamColor={homeTeamColor}
            awayTeamColor={awayTeamColor}
          />
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
          absoluteBack
          leftContent={
            <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-1)' }}>
              {/* Status */}
              <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--color-text-secondary)' }}>
                Final
              </span>
              {/* Playoff series (under Final, above the score) */}
              {seriesLabel(gameDetail.game_id) && (
                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-secondary)' }}>
                  {seriesLabel(gameDetail.game_id)}
                </span>
              )}

              {/* Scoreboard row: logos, abbreviations and score all centered on one line */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-6)', flexWrap: 'wrap', marginTop: 'var(--space-1)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                  <img src={getTeamLogoUrl(away_team.team_abbrev)} alt={away_team.team_abbrev} style={{ width: 46, height: 46 }} />
                  <span style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{away_team.team_abbrev}</span>
                </div>

                <div style={{ fontSize: 'var(--text-4xl)', fontWeight: 700, fontFamily: 'var(--font-mono)', lineHeight: 1, whiteSpace: 'nowrap' }}>
                  <span style={{ color: (away_team.score ?? 0) >= (home_team.score ?? 0) ? 'var(--color-text-primary)' : 'var(--color-text-muted)' }}>
                    {away_team.score ?? 0}
                  </span>
                  <span style={{ color: 'var(--color-text-muted)', margin: '0 var(--space-3)' }}>–</span>
                  <span style={{ color: (home_team.score ?? 0) >= (away_team.score ?? 0) ? 'var(--color-text-primary)' : 'var(--color-text-muted)' }}>
                    {home_team.score ?? 0}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                  <span style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{home_team.team_abbrev}</span>
                  <img src={getTeamLogoUrl(home_team.team_abbrev)} alt={home_team.team_abbrev} style={{ width: 46, height: 46 }} />
                </div>
              </div>

              {/* Date · arena · (type when not a playoff series) */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flexWrap: 'wrap', gap: 'var(--space-5)', marginTop: 'var(--space-3)', fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                  <Calendar size={14} />
                  {new Date(gameDetail.game_date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
                </span>
                {gameDetail.venue_name && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                    <MapPin size={14} />
                    {gameDetail.venue_name}
                  </span>
                )}
                {!seriesLabel(gameDetail.game_id) && gameTypeLabel(gameDetail.game_id) && (
                  <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--color-text-muted)' }}>
                    {gameTypeLabel(gameDetail.game_id)}
                  </span>
                )}
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
const lastNameOf = (name: string) => (name || '').trim().split(' ').slice(-1)[0] || name

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--color-text-muted)', marginBottom: 'var(--space-4)' }}>
      {children}
    </h2>
  )
}

// Weighted single-game impact score for skaters (inspired by Game Score).
function skaterGameScore(p: PlayerGameStats): number {
  const goals = p.goals ?? 0
  const a1 = p.first_assists
  const a2 = p.second_assists
  const assistScore = (a1 != null || a2 != null) ? 0.70 * (a1 ?? 0) + 0.45 * (a2 ?? 0) : 0.55 * (p.assists ?? 0)
  return 0.75 * goals + assistScore + 0.70 * (p.ixg ?? 0) + 0.07 * (p.shots ?? 0) + 0.05 * ((p.ihdcf ?? p.hdcf) ?? 0)
}

function OverviewTab({ gameDetail, playerStats }: { gameDetail: GameDetailType; playerStats: GamePlayerStats | null }) {
  const { home_team, away_team, game_id } = gameDetail
  const homeColor = getTeamColor(home_team.team_abbrev)
  const awayColor = getTeamColor(away_team.team_abbrev)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [goals, setGoals] = useState<GoalDetail[]>([])
  const [pressure, setPressure] = useState<PressurePoint[]>([])
  const [teamStats, setTeamStats] = useState<TeamComparisonStats | null>(null)
  const [goaltending, setGoaltending] = useState<GoaltenderStat[]>([])

  useEffect(() => {
    let active = true
    getGameGoals(game_id).then(d => { if (active) setGoals(d) }).catch(() => {})
    getGamePressure(game_id).then(d => { if (active) setPressure(d) }).catch(() => {})
    getGameTeamStats(game_id).then(d => { if (active) setTeamStats(d) }).catch(() => {})
    getGameGoaltending(game_id).then(d => { if (active) setGoaltending(d) }).catch(() => {})
    return () => { active = false }
  }, [game_id])

  const handleNavigateToAnalytics = () => {
    searchParams.set('tab', 'analytics')
    navigate({ search: searchParams.toString() })
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: 'var(--space-8)' }}>
      <InsightBanner home={home_team} away={away_team} teamStats={teamStats} goaltending={goaltending} />

      <div className="overview-grid">
        <div className="overview-col">
          <GameFlowMini
            pressure={pressure}
            goals={goals}
            homeTeamId={home_team.team_id}
            homeColor={homeColor}
            awayColor={awayColor}
            homeAbbrev={home_team.team_abbrev}
            awayAbbrev={away_team.team_abbrev}
            onNavigate={handleNavigateToAnalytics}
          />
          <ScoringTimeline goals={goals} homeTeamId={home_team.team_id} />
        </div>

        <div className="overview-col">
          {playerStats && <TopPerformersList playerStats={playerStats} homeTeam={home_team} awayTeam={away_team} />}
          <TeamStatsCompact teamStats={teamStats} homeTeam={home_team} awayTeam={away_team} homeColor={homeColor} awayColor={awayColor} />
          <GoalieDuel goaltending={goaltending} />
        </div>
      </div>
    </div>
  )
}

// One-line natural-language summary of the game from the available data.
function InsightBanner({ home, away, teamStats, goaltending }: { home: TeamGameStats; away: TeamGameStats; teamStats: TeamComparisonStats | null; goaltending: GoaltenderStat[] }) {
  if (!teamStats) return null
  const xgHome = home.xgf ?? 0
  const xgAway = away.xgf ?? 0
  const maxXg = Math.max(xgHome, xgAway)
  const minXg = Math.min(xgHome, xgAway)
  const xgLeader = xgAway > xgHome ? away.team_abbrev : home.team_abbrev
  const xgTrail = xgAway > xgHome ? home.team_abbrev : away.team_abbrev

  const parts: string[] = []
  if (maxXg > 0.1) parts.push(`${xgLeader} out-chanced ${xgTrail} ${maxXg.toFixed(2)}–${minXg.toFixed(2)} xG`)

  const bestG = goaltending.length
    ? [...goaltending].sort((a, b) => (b.shots_against - b.goals_against) / Math.max(1, b.shots_against) - (a.shots_against - a.goals_against) / Math.max(1, a.shots_against))[0]
    : null
  const tail: string[] = []
  if (bestG) tail.push(`${lastNameOf(bestG.goalie_name)} stopped ${bestG.shots_against - bestG.goals_against} of ${bestG.shots_against}`)

  const ppMade = Math.max(teamStats.home_pp_goals, teamStats.away_pp_goals)
  if (ppMade > 0) {
    const homeLead = teamStats.home_pp_goals >= teamStats.away_pp_goals
    const ppTeam = homeLead ? home.team_abbrev : away.team_abbrev
    const ppOpp = homeLead ? teamStats.away_penalties : teamStats.home_penalties
    tail.push(`${ppTeam} went ${ppMade}/${Math.max(ppMade, ppOpp)} on the power play`)
  }

  if (parts.length === 0 && tail.length === 0) return null
  const text = (parts.length ? parts[0] : tail.shift() || '') + (tail.length ? ', but ' + tail.join('; ') : '') + '.'

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', background: 'var(--color-bg-elevated)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4) var(--space-5)', marginBottom: 'var(--space-10)' }}>
      <Lightbulb size={18} style={{ color: 'var(--color-warning)', flexShrink: 0 }} />
      <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)' }}>{text}</span>
    </div>
  )
}

// Compact shot-attempt momentum line with team-colored goal dots, clickable to Analytics.
function GameFlowMini({ pressure, goals, homeTeamId, homeColor, awayColor, homeAbbrev, awayAbbrev, onNavigate }: {
  pressure: PressurePoint[]
  goals: GoalDetail[]
  homeTeamId: number
  homeColor: string
  awayColor: string
  homeAbbrev: string
  awayAbbrev: string
  onNavigate: () => void
}) {
  if (pressure.length === 0) return null
  const W = 600
  const H = 150
  const PAD = { top: 14, right: 12, bottom: 24, left: 12 }
  const plotW = W - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom
  const centerY = PAD.top + plotH / 2
  const maxTime = Math.max(3600, ...pressure.map(p => p.game_time_seconds))
  const mom = pressure.map(p => ({ t: p.game_time_seconds, m: p.home_rate - p.away_rate }))
  const maxAbs = Math.max(10, ...mom.map(d => Math.abs(d.m)))
  const xS = (t: number) => PAD.left + (t / maxTime) * plotW
  const yS = (m: number) => centerY - (m / maxAbs) * (plotH / 2)
  const line = mom.map((d, i) => `${i ? 'L' : 'M'} ${xS(d.t)} ${yS(d.m)}`).join(' ')
  // Closed area from the line down to the centre line, shaded by team via clip halves.
  const area = `M ${xS(mom[0].t)} ${centerY} ` + mom.map(d => `L ${xS(d.t)} ${yS(d.m)}`).join(' ') + ` L ${xS(mom[mom.length - 1].t)} ${centerY} Z`
  const momAt = (t: number) => { let n = mom[0]; for (const d of mom) if (Math.abs(d.t - t) < Math.abs(n.t - t)) n = d; return n.m }

  return (
    <section className="overview-card">
      <SectionTitle>Game flow · shot attempt momentum</SectionTitle>
      <div onClick={onNavigate} style={{ cursor: 'pointer' }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
          <defs>
            <clipPath id="gf-home"><rect x={0} y={0} width={W} height={centerY} /></clipPath>
            <clipPath id="gf-away"><rect x={0} y={centerY} width={W} height={H - centerY} /></clipPath>
          </defs>
          {/* team shading: home above the centre line, away below */}
          <path d={area} fill={homeColor} fillOpacity={0.16} clipPath="url(#gf-home)" />
          <path d={area} fill={awayColor} fillOpacity={0.16} clipPath="url(#gf-away)" />
          {[1200, 2400].filter(t => t < maxTime).map(t => (
            <line key={t} x1={xS(t)} y1={PAD.top} x2={xS(t)} y2={PAD.top + plotH} stroke="var(--color-border-subtle)" strokeWidth={1} />
          ))}
          <line x1={PAD.left} y1={centerY} x2={W - PAD.right} y2={centerY} stroke="var(--color-border)" strokeWidth={1} />
          {[600, 1800, 3000].filter(t => t < maxTime).map((t, i) => (
            <text key={i} x={xS(t)} y={H - 7} textAnchor="middle" fontSize={11} fill="var(--color-text-muted)">P{i + 1}</text>
          ))}
          <path d={line} fill="none" stroke="var(--color-text-muted)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {goals.map((g, i) => (
            <circle key={i} cx={xS(g.game_time_seconds)} cy={yS(momAt(g.game_time_seconds))} r={4.5} fill={g.team_id === homeTeamId ? homeColor : awayColor} stroke="var(--color-bg-surface)" strokeWidth={1.5} />
          ))}
        </svg>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)', marginTop: 'var(--space-1)', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', flexWrap: 'wrap' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}><span style={{ width: 8, height: 8, borderRadius: '50%', background: awayColor }} />{awayAbbrev} goal</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}><span style={{ width: 8, height: 8, borderRadius: '50%', background: homeColor }} />{homeAbbrev} goal</span>
        <span>· click to view full analytics</span>
      </div>
    </section>
  )
}

// Condensed goal-by-goal list with running score.
function ScoringTimeline({ goals, homeTeamId }: { goals: GoalDetail[]; homeTeamId: number }) {
  if (goals.length === 0) return null
  const sorted = [...goals].sort((a, b) => a.game_time_seconds - b.game_time_seconds)
  let hs = 0
  let as = 0
  return (
    <section className="overview-card">
      <SectionTitle>Scoring timeline</SectionTitle>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {sorted.map((g, i) => {
          if (g.team_id === homeTeamId) hs++; else as++
          const color = getTeamColor(g.team_abbrev)
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', padding: 'var(--space-2) 0 var(--space-2) var(--space-3)', borderLeft: `3px solid ${color}`, borderBottom: i < sorted.length - 1 ? '1px solid var(--color-border-subtle)' : 'none' }}>
              <span style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--color-text-muted)', flexShrink: 0, width: 58 }}>P{g.period} {g.time_in_period}</span>
              <span style={{ flex: 1, fontSize: 'var(--text-sm)', minWidth: 0 }}>
                <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{lastNameOf(g.scorer_name || 'Goal')}</span>
                {g.strength !== 'EV' && <span style={{ color: 'var(--color-text-secondary)', fontWeight: 600 }}> ({g.strength})</span>}
                {g.assists.length > 0 && <span style={{ color: 'var(--color-text-muted)' }}> · {g.assists.map(lastNameOf).join(', ')}</span>}
              </span>
              <span style={{ fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--color-text-primary)', flexShrink: 0 }}>{as}–{hs}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

// A circular player headshot with a team-logo badge and initials fallback.
function PlayerAvatar({ playerId, name, teamAbbrev, size = 44 }: { playerId: number; name: string; teamAbbrev: string; size?: number }) {
  const [err, setErr] = useState(false)
  const initials = name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      {!err ? (
        <img
          src={getPlayerHeadshotUrl(playerId, teamAbbrev)}
          alt={name}
          onError={() => setErr(true)}
          style={{ width: '100%', height: '100%', borderRadius: 'var(--radius-full)', objectFit: 'cover', border: '1px solid var(--color-border-subtle)', background: 'var(--color-bg-elevated)' }}
        />
      ) : (
        <div style={{ width: '100%', height: '100%', borderRadius: 'var(--radius-full)', background: 'var(--color-bg-elevated)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-secondary)' }}>{initials}</div>
      )}
      <img src={getTeamLogoUrl(teamAbbrev)} alt="" aria-hidden="true" style={{ position: 'absolute', bottom: -3, right: -3, width: size * 0.4, height: size * 0.4, borderRadius: 'var(--radius-full)', border: '1.5px solid var(--color-bg-surface)', background: 'var(--color-bg-surface)' }} />
    </div>
  )
}

// Top-3 impact players as rich rows: headshot, full stat line, points pill.
function TopPerformersList({ playerStats, homeTeam, awayTeam }: { playerStats: GamePlayerStats; homeTeam: TeamGameStats; awayTeam: TeamGameStats }) {
  const skaters = [...playerStats.home_players, ...playerStats.away_players]
    .filter(p => p.position !== 'G')
    .sort((a, b) => skaterGameScore(b) - skaterGameScore(a))
    .slice(0, 3)
  if (skaters.length === 0) return null
  return (
    <section className="overview-card">
      <SectionTitle>Top performers</SectionTitle>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {skaters.map((p, i) => {
          const abbrev = p.team_id === homeTeam.team_id ? homeTeam.team_abbrev : awayTeam.team_abbrev
          const accent = getTeamColor(abbrev)
          const goals = p.goals ?? 0
          const assists = p.assists ?? 0
          const points = p.points ?? (goals + assists)
          return (
            <Link key={p.player_id} to={`/players/${p.player_id}`} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', padding: 'var(--space-3) 0', borderBottom: i < skaters.length - 1 ? '1px solid var(--color-border-subtle)' : 'none', textDecoration: 'none' }}>
              <span style={{ width: 14, flexShrink: 0, fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', textAlign: 'center' }}>{i + 1}</span>
              <PlayerAvatar playerId={p.player_id} name={p.player_name} teamAbbrev={abbrev} />
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-2)' }}>
                  <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.player_name}</span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', flexShrink: 0 }}>{p.position}</span>
                </span>
                <span style={{ display: 'block', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)', marginTop: '2px' }}>{goals}G · {assists}A · {(p.ixg ?? 0).toFixed(2)} ixG</span>
              </span>
              <span style={{ flexShrink: 0, fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-inverse)', background: accent, padding: '2px var(--space-2)', borderRadius: 'var(--radius-full)', whiteSpace: 'nowrap' }}>{points} PTS</span>
            </Link>
          )
        })}
      </div>
    </section>
  )
}

// Key team comparison with an "All stats" expander.
function TeamStatsCompact({ teamStats, homeTeam, awayTeam, homeColor, awayColor }: { teamStats: TeamComparisonStats | null; homeTeam: TeamGameStats; awayTeam: TeamGameStats; homeColor: string; awayColor: string }) {
  const [showAll, setShowAll] = useState(false)
  if (!teamStats) {
    return (
      <section className="overview-card">
        <SectionTitle>Team stats · {awayTeam.team_abbrev} / {homeTeam.team_abbrev}</SectionTitle>
        <SkeletonLoader height={180} />
      </section>
    )
  }
  const ts = teamStats
  const foTotal = ts.home_faceoff_wins + ts.away_faceoff_wins
  const awayFo = foTotal ? (ts.away_faceoff_wins / foTotal) * 100 : 0
  const homeFo = foTotal ? (ts.home_faceoff_wins / foTotal) * 100 : 0
  const awayPpOpp = Math.max(ts.away_pp_goals, ts.home_penalties)
  const homePpOpp = Math.max(ts.home_pp_goals, ts.away_penalties)

  const key = [
    { label: 'Expected goals', av: (awayTeam.xgf ?? 0).toFixed(2), hv: (homeTeam.xgf ?? 0).toFixed(2), ar: awayTeam.xgf ?? 0, hr: homeTeam.xgf ?? 0, bar: true },
    { label: 'Power play', av: `${ts.away_pp_goals}/${awayPpOpp}`, hv: `${ts.home_pp_goals}/${homePpOpp}`, ar: ts.away_pp_goals, hr: ts.home_pp_goals, bar: !(ts.away_pp_goals === 0 && ts.home_pp_goals === 0) },
    { label: 'Faceoff %', av: awayFo.toFixed(1), hv: homeFo.toFixed(1), ar: ts.away_faceoff_wins, hr: ts.home_faceoff_wins, bar: foTotal > 0 },
    { label: 'Hits', av: String(ts.away_hits), hv: String(ts.home_hits), ar: ts.away_hits, hr: ts.home_hits, bar: true },
  ]
  const rest = [
    { label: 'Shots on goal', av: String(ts.away_sog), hv: String(ts.home_sog), ar: ts.away_sog, hr: ts.home_sog, bar: true },
    { label: 'Blocked shots', av: String(ts.away_blocks), hv: String(ts.home_blocks), ar: ts.away_blocks, hr: ts.home_blocks, bar: true },
    { label: 'Penalty minutes', av: String(ts.away_pim), hv: String(ts.home_pim), ar: ts.away_pim, hr: ts.home_pim, bar: !(ts.away_pim === 0 && ts.home_pim === 0) },
    { label: 'Giveaways', av: String(ts.away_giveaways), hv: String(ts.home_giveaways), ar: ts.away_giveaways, hr: ts.home_giveaways, bar: true },
    { label: 'Takeaways', av: String(ts.away_takeaways), hv: String(ts.home_takeaways), ar: ts.away_takeaways, hr: ts.home_takeaways, bar: true },
  ]
  const rows = showAll ? [...key, ...rest] : key

  return (
    <section className="overview-card">
      <SectionTitle>Team stats · {awayTeam.team_abbrev} / {homeTeam.team_abbrev}</SectionTitle>
      <div className="team-stats-compact" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
        {rows.map(r => (
          <ComparisonRow key={r.label} label={r.label} awayValue={r.av} homeValue={r.hv} awayRaw={r.ar} homeRaw={r.hr} awayColor={awayColor} homeColor={homeColor} showBar={r.bar} />
        ))}
      </div>
      <button
        onClick={() => setShowAll(!showAll)}
        style={{ marginTop: 'var(--space-5)', width: '100%', padding: 'var(--space-2)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', background: 'transparent', color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)', fontWeight: 500, cursor: 'pointer' }}
      >
        {showAll ? 'Fewer stats ↑' : 'All stats ↗'}
      </button>
    </section>
  )
}

// A single labelled stat block (value over caption).
function GoalieStat({ value, label }: { value: string; label: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 44 }}>
      <span style={{ fontSize: 'var(--text-base)', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--color-text-primary)' }}>{value}</span>
      <span style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-muted)', marginTop: '2px' }}>{label}</span>
    </div>
  )
}

// Goaltending duel: each goalie with headshot, clean stat blocks, and GSAX.
function GoalieDuel({ goaltending }: { goaltending: GoaltenderStat[] }) {
  if (goaltending.length === 0) return null
  return (
    <section className="overview-card">
      <SectionTitle>Goaltending duel</SectionTitle>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {goaltending.map((g, i) => {
          const saves = g.shots_against - g.goals_against
          const svpct = g.shots_against ? (saves / g.shots_against).toFixed(3).replace(/^0/, '') : '—'
          return (
            <div key={g.player_id} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', padding: 'var(--space-3) 0', borderBottom: i < goaltending.length - 1 ? '1px solid var(--color-border-subtle)' : 'none' }}>
              <PlayerAvatar playerId={g.player_id} name={g.goalie_name} teamAbbrev={g.team_abbrev} size={40} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {g.goalie_name}<span style={{ fontWeight: 400, color: 'var(--color-text-muted)' }}> · {g.team_abbrev}</span>
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: g.gsax >= 0 ? 'var(--color-success)' : 'var(--color-danger)', marginTop: '2px' }}>
                  {g.gsax >= 0 ? '+' : ''}{g.gsax.toFixed(2)} goals saved above expected
                </div>
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-4)', flexShrink: 0 }}>
                <GoalieStat value={`${saves}/${g.shots_against}`} label="SV/SA" />
                <GoalieStat value={svpct} label="SV%" />
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

// ── Analytics panel building blocks ──────────────────────────────────────────

function PanelHeader({ title, subtitle, isNew }: { title: string; subtitle?: string; isNew?: boolean }) {
  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text-primary)', margin: 0 }}>{title}</h3>
        {isNew && (
          <span style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-accent)', background: 'var(--color-accent-subtle)', padding: '1px 6px', borderRadius: 'var(--radius-full)' }}>New</span>
        )}
      </div>
      {subtitle && <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: '3px 0 0' }}>{subtitle}</p>}
    </div>
  )
}

function PanelCaption({ children }: { children: React.ReactNode }) {
  return <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: 'var(--space-4) 0 0', lineHeight: 1.5 }}>{children}</p>
}

// Single-game impact score from a SkaterImpact row (Game Score style).
function impactScore(p: SkaterImpact): number {
  return 0.75 * p.goals + 0.55 * p.assists + 0.70 * p.ixg + 0.07 * p.shots + 0.05 * p.ihdcf
}

// "Special teams decided it" — PP/PK detail by team.
function SpecialTeamsPanel({ gameId }: { gameId: number }) {
  const [rows, setRows] = useState<SpecialTeamsStat[]>([])
  useEffect(() => { let a = true; getGameSpecialTeams(gameId).then(d => { if (a) setRows(d) }).catch(() => {}); return () => { a = false } }, [gameId])
  if (rows.length < 2) return null
  const ordered = [...rows].sort((x, y) => Number(x.is_home) - Number(y.is_home)) // away first
  const lead = [...rows].sort((x, y) => y.pp_goals - x.pp_goals || (y.pp_goals - y.pp_xg) - (x.pp_goals - x.pp_xg))[0]
  const ppDelta = lead.pp_goals - lead.pp_xg
  return (
    <section className="overview-card">
      <PanelHeader title="Special teams decided it" subtitle="Power play detail by team" isNew />
      <table className="analytics-table">
        <thead>
          <tr><th></th><th>PP</th><th>PP xG</th><th>PP shots</th><th>PK saves</th></tr>
        </thead>
        <tbody>
          {ordered.map(t => (
            <tr key={t.team_abbrev}>
              <td>{t.team_abbrev}</td>
              <td>{t.pp_goals}/{t.pp_opp}</td>
              <td>{t.pp_xg.toFixed(2)}</td>
              <td>{t.pp_shots}</td>
              <td>{t.pk_saves}/{t.pk_shots}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {lead.pp_goals > 0 && (
        <PanelCaption>
          {lead.team_abbrev} converted {lead.pp_goals} of {lead.pp_opp} chances on {lead.pp_xg.toFixed(2)} xG, {ppDelta >= 0 ? 'scoring' : 'finishing'} {Math.abs(ppDelta).toFixed(2)} {ppDelta >= 0 ? 'above' : 'below'} expected on the power play alone.
        </PanelCaption>
      )}
    </section>
  )
}

// "<Goalie> stole one" — goals saved above expected, by shot danger.
function GoalieDangerPanel({ gameId }: { gameId: number }) {
  const [rows, setRows] = useState<GoalieDangerStat[]>([])
  useEffect(() => { let a = true; getGameGoalieDanger(gameId).then(d => { if (a) setRows(d) }).catch(() => {}); return () => { a = false } }, [gameId])
  if (rows.length === 0) return null
  const best = [...rows].sort((x, y) => y.gsax - x.gsax)[0]
  const swing = rows.length >= 2 ? Math.abs(rows[0].gsax - rows[1].gsax) : Math.abs(best.gsax)
  const title = best.gsax > 0.5 ? `${lastNameOf(best.goalie_name)} stole one` : 'Goaltending by danger'
  return (
    <section className="overview-card">
      <PanelHeader title={title} subtitle="Goals saved above expected, by shot danger" isNew />
      <table className="analytics-table">
        <thead>
          <tr><th></th><th>High</th><th>Med</th><th>Low</th><th>GSAx</th></tr>
        </thead>
        <tbody>
          {rows.map(g => (
            <tr key={g.player_id}>
              <td>{lastNameOf(g.goalie_name)} <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>{g.team_abbrev}</span></td>
              <td>{g.high_saves}/{g.high_shots}</td>
              <td>{g.med_saves}/{g.med_shots}</td>
              <td>{g.low_saves}/{g.low_shots}</td>
              <td style={{ color: g.gsax >= 0 ? 'var(--color-success)' : 'var(--color-danger)', fontWeight: 700 }}>{g.gsax >= 0 ? '+' : ''}{g.gsax.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length >= 2 && <PanelCaption>A {swing.toFixed(1)}-goal swing between the two creases.</PanelCaption>}
    </section>
  )
}

// "Control and danger" — team rate bars, away left / home right.
function ControlDangerBars({ homeTeam, awayTeam, homeColor, awayColor }: { homeTeam: TeamGameStats; awayTeam: TeamGameStats; homeColor: string; awayColor: string }) {
  const homeXgf = homeTeam.xgf ?? 0
  const awayXgf = awayTeam.xgf ?? 0
  const totalXg = homeXgf + awayXgf
  const rows = [
    { label: 'Corsi for %', av: (awayTeam.cf_pct ?? 0).toFixed(1), hv: (homeTeam.cf_pct ?? 0).toFixed(1), ar: awayTeam.cf_pct ?? 0, hr: homeTeam.cf_pct ?? 0, bar: awayTeam.cf_pct != null && homeTeam.cf_pct != null },
    { label: 'Expected goals %', av: (totalXg ? (awayXgf / totalXg) * 100 : 50).toFixed(1), hv: (totalXg ? (homeXgf / totalXg) * 100 : 50).toFixed(1), ar: awayXgf, hr: homeXgf, bar: totalXg > 0 },
    { label: 'High-danger chances /60', av: (awayTeam.hdcf_per60 ?? 0).toFixed(1), hv: (homeTeam.hdcf_per60 ?? 0).toFixed(1), ar: awayTeam.hdcf_per60 ?? 0, hr: homeTeam.hdcf_per60 ?? 0, bar: awayTeam.hdcf_per60 != null && homeTeam.hdcf_per60 != null },
    { label: 'Zone entry success % (proxy)', av: ((awayTeam.zone_entry_proxy_success_rate ?? 0) * 100).toFixed(1), hv: ((homeTeam.zone_entry_proxy_success_rate ?? 0) * 100).toFixed(1), ar: awayTeam.zone_entry_proxy_success_rate ?? 0, hr: homeTeam.zone_entry_proxy_success_rate ?? 0, bar: awayTeam.zone_entry_proxy_success_rate != null && homeTeam.zone_entry_proxy_success_rate != null },
  ]
  return (
    <section className="overview-card">
      <PanelHeader title="Control and danger" subtitle={`Team rates, ${awayTeam.team_abbrev} left / ${homeTeam.team_abbrev} right`} />
      <div className="team-stats-compact" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
        {rows.map(r => (
          <ComparisonRow key={r.label} label={r.label} awayValue={r.av} homeValue={r.hv} awayRaw={r.ar} homeRaw={r.hr} awayColor={awayColor} homeColor={homeColor} showBar={r.bar} />
        ))}
      </div>
    </section>
  )
}

// "Shot quality ladder" — attempts/goals by danger band per team.
function ShotQualityLadder({ gameId }: { gameId: number }) {
  const [rows, setRows] = useState<ShotQualityRow[]>([])
  useEffect(() => { let a = true; getGameShotQuality(gameId).then(d => { if (a) setRows(d) }).catch(() => {}); return () => { a = false } }, [gameId])
  if (rows.length === 0) return null
  const away = rows[0].away_abbrev
  const home = rows[0].home_abbrev
  const high = rows.find(r => r.band === 'High danger')
  const homeFin = high && high.home_attempts ? Math.round((high.home_goals / high.home_attempts) * 100) : 0
  const awayFin = high && high.away_attempts ? Math.round((high.away_goals / high.away_attempts) * 100) : 0
  return (
    <section className="overview-card">
      <PanelHeader title="Shot quality ladder" subtitle="Attempts by danger band, and what they became" isNew />
      <table className="analytics-table">
        <thead>
          <tr><th>Band</th><th>{away} att / G</th><th>{home} att / G</th></tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.band}>
              <td>{r.band}</td>
              <td>{r.away_attempts} / {r.away_goals}</td>
              <td>{r.home_attempts} / {r.home_goals}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {high && <PanelCaption>{home} finished {homeFin}% of high-danger looks; {away} finished {awayFin}%.</PanelCaption>}
    </section>
  )
}

// "Who drove the game" — skater impact table with an All-skaters expander.
function SkaterImpactTable({ gameId }: { gameId: number }) {
  const [rows, setRows] = useState<SkaterImpact[]>([])
  const [showAll, setShowAll] = useState(false)
  useEffect(() => { let a = true; getGameSkaterImpact(gameId).then(d => { if (a) setRows(d) }).catch(() => {}); return () => { a = false } }, [gameId])
  if (rows.length === 0) return null
  const sorted = [...rows].sort((x, y) => impactScore(y) - impactScore(x))
  const shown = showAll ? sorted : sorted.slice(0, 4)
  return (
    <section className="overview-card">
      <PanelHeader title="Who drove the game" subtitle="Top skaters by game score · individual xG and high-danger chances" isNew />
      <table className="analytics-table">
        <thead>
          <tr><th>Skater</th><th>Game score</th><th>ixG</th><th>HDC</th><th>TOI</th></tr>
        </thead>
        <tbody>
          {shown.map(p => (
            <tr key={p.player_id}>
              <td><span style={{ fontWeight: 600 }}>{lastNameOf(p.player_name)}</span> <span style={{ color: 'var(--color-text-muted)' }}>{p.team_abbrev}</span></td>
              <td style={{ fontWeight: 700 }}>{impactScore(p).toFixed(2)}</td>
              <td>{p.ixg.toFixed(2)}</td>
              <td>{p.ihdcf}</td>
              <td>{p.toi}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        onClick={() => setShowAll(!showAll)}
        style={{ marginTop: 'var(--space-4)', padding: 'var(--space-2) var(--space-4)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', background: 'transparent', color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)', fontWeight: 500, cursor: 'pointer' }}
      >
        {showAll ? 'Fewer skaters ↑' : 'All skaters ↗'}
      </button>
    </section>
  )
}

// Analytics Tab - Rebuilt per PART 1 specifications
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

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: 'var(--space-8)' }}>
      {/* 1. Timeline stack — what happened, three synced lanes */}
      <section style={{ marginBottom: 'var(--space-10)' }}>
        <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text-primary)', margin: 0 }}>Game timeline: three synced views of the same 60 minutes</h2>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', margin: '4px 0 var(--space-6)' }}>Goals marked once on the shared rail · hover any minute to read all three lanes</p>
        <GameTimelineStack
          gameId={game_id}
          homeTeamId={home_team.team_id}
          awayTeamId={away_team.team_id}
          homeAbbrev={home_team.team_abbrev}
          awayAbbrev={away_team.team_abbrev}
          homeColor={homeTeamColor}
          awayColor={awayTeamColor}
        />
      </section>

      {/* 2. Why the score diverged from xG: special teams + goaltending */}
      <div className="analytics-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <SpecialTeamsPanel gameId={game_id} />
        <GoalieDangerPanel gameId={game_id} />
      </div>

      {/* 3. The underlying battle: control bars + shot quality */}
      <div className="analytics-grid" style={{ marginBottom: 'var(--space-8)' }}>
        <ControlDangerBars homeTeam={home_team} awayTeam={away_team} homeColor={homeTeamColor} awayColor={awayTeamColor} />
        <ShotQualityLadder gameId={game_id} />
      </div>

      {/* 4. Who drove the game */}
      <div style={{ marginBottom: 'var(--space-10)' }}>
        <SkaterImpactTable gameId={game_id} />
      </div>

      {/* 5. Shot maps per team */}
      <div style={{ marginBottom: 'var(--space-10)' }}>
        <ShotMapKDE
          gameId={game_id}
          homeTeamAbbrev={home_team.team_abbrev}
          awayTeamAbbrev={away_team.team_abbrev}
          homeTeamColor={homeTeamColor}
          awayTeamColor={awayTeamColor}
          situation="all"
        />
      </div>

      {/* 6. Period breakdown + 10-game form context */}
      <div className="analytics-grid">
        <PeriodBreakdownTable
          homeTeamAbbrev={home_team.team_abbrev}
          awayTeamAbbrev={away_team.team_abbrev}
          homeTeamColor={homeTeamColor}
          awayTeamColor={awayTeamColor}
          homeStats={home_team}
          awayStats={away_team}
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
  )
}

// Players Tab - Rebuilt per PART 2 specifications
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
  const [sortColumn, setSortColumn] = useState<string>('toi')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')

  if (!playerStats) return null

  // Separate skaters and goalies
  const awaySkaters = playerStats.away_players.filter(p => p.position !== 'G')
  const homeSkaters = playerStats.home_players.filter(p => p.position !== 'G')
  const goalies = [...playerStats.away_players, ...playerStats.home_players].filter(p => p.position === 'G')

  // Format TOI from seconds to mm:ss
  const formatTOI = (seconds: number | null): string => {
    if (!seconds) return '0:00'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  // Calculate shooting percentage
  const calculateSH = (goals: number | null, shots: number | null): string => {
    if (!goals || !shots || shots === 0) return '0.0'
    return ((goals / shots) * 100).toFixed(1)
  }

  // Sort function
  const sortPlayers = (players: PlayerGameStats[]) => {
    return [...players].sort((a, b) => {
      let aVal: any = a[sortColumn as keyof PlayerGameStats]
      let bVal: any = b[sortColumn as keyof PlayerGameStats]

      // Handle null values
      if (aVal === null) aVal = -Infinity
      if (bVal === null) bVal = -Infinity

      if (sortDirection === 'asc') {
        return aVal > bVal ? 1 : -1
      } else {
        return aVal < bVal ? 1 : -1
      }
    })
  }

  const handleSort = (column: string) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortColumn(column)
      setSortDirection('desc')
    }
  }

  const renderSkaterTable = (players: PlayerGameStats[], teamAbbrev: string, teamColor: string) => {
    const sorted = sortPlayers(players)

    return (
      <div style={{
        background: 'var(--color-bg-surface)',
        borderRadius: 'var(--radius-lg)',
        borderTop: `3px solid ${teamColor}`,
        overflow: 'hidden'
      }}>
        <div style={{
          padding: 'var(--space-4) var(--space-6)',
          borderBottom: '1px solid var(--color-border)'
        }}>
          <h3 style={{
            fontSize: 'var(--text-base)',
            fontWeight: 600,
            color: 'var(--color-text-primary)',
            margin: 0
          }}>
            {teamAbbrev}
          </h3>
        </div>

        <div style={{ maxHeight: sorted.length > 14 ? '600px' : 'auto', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{
              position: sorted.length > 14 ? 'sticky' : 'static',
              top: 0,
              background: 'var(--color-bg-surface)',
              zIndex: 1
            }}>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                <th onClick={() => handleSort('player_name')} style={{ ...headerStyle, textAlign: 'left', width: '200px' }}>Player</th>
                <th onClick={() => handleSort('toi')} style={{ ...headerStyle, width: '70px' }}>TOI</th>
                <th onClick={() => handleSort('goals')} style={headerStyle}>G</th>
                <th onClick={() => handleSort('first_assists')} style={headerStyle}>A1</th>
                <th onClick={() => handleSort('second_assists')} style={headerStyle}>A2</th>
                <th onClick={() => handleSort('points')} style={headerStyle}>P</th>
                <th onClick={() => handleSort('shots')} style={headerStyle}>SOG</th>
                <th onClick={() => handleSort('goals')} style={headerStyle}>SH%</th>
                <th onClick={() => handleSort('ixg')} style={headerStyle}>ixG</th>
                <th onClick={() => handleSort('cf')} style={headerStyle}>iCF</th>
                <th onClick={() => handleSort('hdcf')} style={headerStyle}>iSCF</th>
                <th onClick={() => handleSort('ihdcf')} style={headerStyle}>iHDCF</th>
                <th onClick={() => handleSort('pim')} style={headerStyle}>PIM</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((player, idx) => (
                <tr
                  key={player.player_id}
                  style={{
                    borderBottom: '1px solid var(--color-border-subtle)',
                    background: idx % 2 === 0 ? 'var(--color-bg-surface)' : 'var(--color-bg-elevated)',
                    cursor: 'pointer',
                    transition: 'background 100ms ease'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-bg-elevated)'}
                  onMouseLeave={(e) => e.currentTarget.style.background = idx % 2 === 0 ? 'var(--color-bg-surface)' : 'var(--color-bg-elevated)'}
                >
                  <td style={{ ...cellStyle, textAlign: 'left' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                      <div style={{
                        width: '28px',
                        height: '28px',
                        borderRadius: '50%',
                        background: 'var(--color-bg-elevated)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 'var(--text-xs)',
                        fontWeight: 600,
                        color: 'var(--color-text-muted)'
                      }}>
                        {player.player_name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                      </div>
                      <div>
                        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{player.player_name}</div>
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{player.position}</div>
                      </div>
                    </div>
                  </td>
                  <td style={cellStyle}>{formatTOI(player.toi)}</td>
                  <td style={cellStyle}>{player.goals ?? 0}</td>
                  <td style={cellStyle}>{player.first_assists ?? 0}</td>
                  <td style={cellStyle}>{player.second_assists ?? 0}</td>
                  <td style={cellStyle}>{player.points ?? 0}</td>
                  <td style={cellStyle}>{player.shots ?? 0}</td>
                  <td style={cellStyle}>{calculateSH(player.goals, player.shots)}</td>
                  <td style={cellStyle}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
                      {player.ixg?.toFixed(2) ?? '0.00'}
                      {player.hot_cold_flag === 'hot' && <Badge variant="hot" />}
                      {player.hot_cold_flag === 'cold' && <Badge variant="cold" />}
                    </div>
                  </td>
                  <td style={cellStyle}>{player.cf ?? 0}</td>
                  <td style={cellStyle}>—</td>
                  <td style={cellStyle}>{player.ihdcf ?? player.hdcf ?? 0}</td>
                  <td style={cellStyle}>{player.pim ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  const headerStyle = {
    padding: 'var(--space-3) var(--space-2)',
    fontSize: 'var(--text-xs)',
    fontWeight: 500,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.06em',
    color: 'var(--color-text-muted)',
    textAlign: 'right' as const,
    cursor: 'pointer',
    userSelect: 'none' as const
  }

  const cellStyle = {
    padding: 'var(--space-3) var(--space-2)',
    fontSize: 'var(--text-sm)',
    fontFamily: 'var(--font-mono)',
    textAlign: 'right' as const,
    color: 'var(--color-text-primary)'
  }

  return (
    <div style={{ padding: 'var(--space-8) 0', maxWidth: '1280px', margin: '0 auto' }}>
      <h2 style={{
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'var(--color-text-muted)',
        marginBottom: 'var(--space-6)'
      }}>
        Skaters
      </h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)', marginBottom: 'var(--space-12)' }}>
        {renderSkaterTable(awaySkaters, away_team.team_abbrev, awayTeamColor)}
        {renderSkaterTable(homeSkaters, home_team.team_abbrev, homeTeamColor)}
      </div>

      {goalies.length > 0 && (
        <>
          <h2 style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: 'var(--color-text-muted)',
            marginBottom: 'var(--space-6)'
          }}>
            Goalies
          </h2>
          <div style={{
            background: 'var(--color-bg-surface)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-6)',
            fontSize: 'var(--text-sm)',
            color: 'var(--color-text-secondary)',
            textAlign: 'center'
          }}>
            Detailed goalie statistics not yet available
          </div>
        </>
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
  const [showRosters, setShowRosters] = useState(false)

  // Calculate xGF% for matchup comparison (using placeholder data)
  const homeXGF = home_team.xgf || 0
  const awayXGF = away_team.xgf || 0
  const totalXG = homeXGF + awayXGF
  const homeXGFPct = totalXG > 0 ? ((homeXGF / totalXG) * 100) : 50
  const awayXGFPct = totalXG > 0 ? ((awayXGF / totalXG) * 100) : 50

  // Select top 3 players based on hot streak (placeholder logic using ixG)
  const allPlayers = playerStats
    ? [...playerStats.home_players, ...playerStats.away_players].filter(p => p.position !== 'G')
    : []

  const topPlayers = allPlayers
    .sort((a, b) => (b.ixg_per60 || 0) - (a.ixg_per60 || 0))
    .slice(0, 3)
    .map(player => {
      const teamAbbrev = player.team_id === home_team.team_id ? home_team.team_abbrev : away_team.team_abbrev
      const teamColor = getTeamColor(teamAbbrev)

      return {
        playerId: player.player_id,
        name: player.player_name,
        teamAbbrev,
        teamLogo: getTeamLogoUrl(teamAbbrev),
        position: player.position,
        statLine: `${(player.ixg_per60 || 0).toFixed(1)} ixG/60`,
        highlight: 'Hot streak',
        accentColor: teamColor
      }
    })

  return (
    <div style={{ padding: 'var(--space-8) 0', maxWidth: '1280px', margin: '0 auto' }}>
      {/* 1. Matchup Comparison */}
      <section style={{ marginBottom: 'var(--space-16)' }}>
        <h2 style={{
          fontSize: 'var(--text-sm)',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: 'var(--color-text-muted)',
          marginBottom: 'var(--space-2)'
        }}>
          Matchup
        </h2>
        <p style={{
          fontSize: 'var(--text-sm)',
          color: 'var(--color-text-secondary)',
          marginBottom: 'var(--space-6)'
        }}>
          Season averages · {gameDetail.season}
        </p>

        <div style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <ComparisonRow
            label="CF%"
            awayValue={away_team.cf_pct?.toFixed(1) || '50.0'}
            homeValue={home_team.cf_pct?.toFixed(1) || '50.0'}
            awayRaw={away_team.cf_pct || 50}
            homeRaw={home_team.cf_pct || 50}
            awayColor={awayTeamColor}
            homeColor={homeTeamColor}
            showBar={true}
            tooltip="Corsi For Percentage - season average"
          />
          <ComparisonRow
            label="xGF%"
            awayValue={awayXGFPct.toFixed(1)}
            homeValue={homeXGFPct.toFixed(1)}
            awayRaw={awayXGFPct}
            homeRaw={homeXGFPct}
            awayColor={awayTeamColor}
            homeColor={homeTeamColor}
            showBar={true}
            tooltip="Expected Goals For Percentage - season average"
          />
          <ComparisonRow
            label="GF/GP"
            awayValue="—"
            homeValue="—"
            awayRaw={0}
            homeRaw={0}
            awayColor={awayTeamColor}
            homeColor={homeTeamColor}
            showBar={false}
            tooltip="Goals for per game - data not yet available"
          />
          <ComparisonRow
            label="GA/GP"
            awayValue="—"
            homeValue="—"
            awayRaw={0}
            homeRaw={0}
            awayColor={awayTeamColor}
            homeColor={homeTeamColor}
            showBar={false}
            tooltip="Goals against per game - data not yet available"
          />
          <ComparisonRow
            label="Faceoff %"
            awayValue="—"
            homeValue="—"
            awayRaw={0}
            homeRaw={0}
            awayColor={awayTeamColor}
            homeColor={homeTeamColor}
            showBar={false}
            tooltip="Faceoff win percentage - data not yet available"
          />
          <ComparisonRow
            label="PP%"
            awayValue="—"
            homeValue="—"
            awayRaw={0}
            homeRaw={0}
            awayColor={awayTeamColor}
            homeColor={homeTeamColor}
            showBar={false}
            tooltip="Power play percentage - data not yet available"
          />
        </div>
      </section>

      {/* 2. Players to Watch */}
      {topPlayers.length > 0 && (
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: 'var(--color-text-muted)',
            marginBottom: 'var(--space-6)'
          }}>
            Players to Watch
          </h2>
          <PodiumCards players={topPlayers} />
        </section>
      )}

      {/* 3. Projected Rosters (disclosure) */}
      {playerStats && (
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <button
            onClick={() => setShowRosters(!showRosters)}
            style={{
              background: 'none',
              border: 'none',
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--color-accent)',
              cursor: 'pointer',
              padding: 0,
              marginBottom: showRosters ? 'var(--space-6)' : 0,
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)'
            }}
          >
            View full rosters {showRosters ? '▾' : '▸'}
          </button>

          {showRosters && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)' }}>
              <div style={{
                background: 'var(--color-bg-surface)',
                borderRadius: 'var(--radius-lg)',
                padding: 'var(--space-6)',
                borderTop: `3px solid ${awayTeamColor}`
              }}>
                <h3 style={{
                  fontSize: 'var(--text-base)',
                  fontWeight: 600,
                  marginBottom: 'var(--space-4)',
                  color: 'var(--color-text-primary)'
                }}>
                  {away_team.team_abbrev}
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  {playerStats.away_players.map((player) => (
                    <PlayerRow key={player.player_id} player={player} />
                  ))}
                </div>
              </div>

              <div style={{
                background: 'var(--color-bg-surface)',
                borderRadius: 'var(--radius-lg)',
                padding: 'var(--space-6)',
                borderTop: `3px solid ${homeTeamColor}`
              }}>
                <h3 style={{
                  fontSize: 'var(--text-base)',
                  fontWeight: 600,
                  marginBottom: 'var(--space-4)',
                  color: 'var(--color-text-primary)'
                }}>
                  {home_team.team_abbrev}
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  {playerStats.home_players.map((player) => (
                    <PlayerRow key={player.player_id} player={player} />
                  ))}
                </div>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

export default GameDetail
