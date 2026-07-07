import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { PageLayout, PageCard, SkeletonLoader, TabNav, PodiumCards, ComparisonRow, MatchupPreviewCard } from '../components/common'
import Badge from '../components/common/Badge'
import GameNarrative from '../components/games/GameNarrative'
import { usePageTitle } from '../hooks/usePageTitle'
import GameTimelineStack from '../components/visualizations/GameTimelineStack'
import ShotMapKDE from '../components/visualizations/ShotMapKDE'
import PeriodBreakdownTable from '../components/visualizations/PeriodBreakdownTable'
import RollingContextPanel from '../components/visualizations/RollingContextPanel'
import { getGameDetail, getGamePlayerStats, getGameGoalieDanger, getGameShotQuality, getGameSkaterImpact, getGameGoals } from '../api/games'
import { getGoalieSeason } from '../api/goalies'
import { GameDetail as GameDetailType, GamePlayerStats, PlayerGameStats, GoalieDangerStat, ShotQualityRow, SkaterImpact, GoalDetail } from '../api/types'
import { getTeamLogoUrl, getTeamColor } from '../utils/teams'
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

// §02 signature: the serif score masthead. Away/home names in Newsreader display-2 flank the
// score in Newsreader 44 tabular; each name is underlined by a 3px rule in its team color (team
// color as a line, never a fill); a mono status line sits beneath. The red rule (PageCard) closes it.
function GameMasthead({ away, home, awayColor, homeColor, awayScore, homeScore, status, preview }: {
  away: string; home: string; awayColor: string; homeColor: string
  awayScore: number | null; homeScore: number | null; status: string; preview?: boolean
}) {
  const awayLeads = !preview && (awayScore ?? 0) >= (homeScore ?? 0)
  const homeLeads = !preview && (homeScore ?? 0) >= (awayScore ?? 0)
  return (
    <div className="game-masthead">
      <div className="game-masthead__grid">
        <div className="game-masthead__team game-masthead__team--away">
          <img className="game-masthead__logo" src={getTeamLogoUrl(away)} alt=""
            onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
          <span className="game-masthead__name" style={{ borderColor: awayColor }}>{away}</span>
        </div>
        <div className="game-masthead__score">
          {preview ? (
            <span className="game-masthead__vs">vs</span>
          ) : (
            <span className="num">
              <span className={awayLeads ? '' : 'game-masthead__trail'}>{awayScore ?? 0}</span>
              <span className="game-masthead__dash">–</span>
              <span className={homeLeads ? '' : 'game-masthead__trail'}>{homeScore ?? 0}</span>
            </span>
          )}
        </div>
        <div className="game-masthead__team game-masthead__team--home">
          <span className="game-masthead__name" style={{ borderColor: homeColor }}>{home}</span>
          <img className="game-masthead__logo" src={getTeamLogoUrl(home)} alt=""
            onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
        </div>
      </div>
      <p className="game-masthead__status">{status}</p>
    </div>
  )
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
  // Normalize legacy tab params (overview/analytics → game, players → box) so old deep links resolve.
  const rawTab = searchParams.get('tab')
  const activeTab = rawTab === 'players' || rawTab === 'box' ? 'box' : 'game'

  usePageTitle(
    gameDetail?.away_team && gameDetail?.home_team
      ? `${gameDetail.away_team.team_abbrev} @ ${gameDetail.home_team.team_abbrev}`
      : 'Game'
  )

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
        setError('Couldn’t load this game. Retry.')
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
          <PageCard title="Game Detail">
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
          </PageCard>
        </div>
      </PageLayout>
    )
  }

  if (error || !gameDetail) {
    return (
      <PageLayout>
        <div className="game-detail">
          <PageCard title="Game detail" back={{ to: '/games', label: 'Games' }}>
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
          </PageCard>
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
          <PageCard
            back={{ to: '/games', label: 'Games' }}
            header={
              <GameMasthead
                away={away_team.team_abbrev}
                home={home_team.team_abbrev}
                awayColor={awayTeamColor}
                homeColor={homeTeamColor}
                awayScore={null}
                homeScore={null}
                preview
                status={[
                  new Date(gameDetail.game_date).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }),
                  gameDetail.venue_name,
                  'Preview',
                ].filter(Boolean).join('  ·  ')}
              />
            }
          >
            <div style={{ marginBottom: 'var(--space-6)' }}>
              <MatchupPreviewCard gameId={gameDetail.game_id} />
            </div>

            <PreviewModeContent
              gameDetail={gameDetail}
              playerStats={playerStats}
              homeTeamColor={homeTeamColor}
              awayTeamColor={awayTeamColor}
            />
          </PageCard>
        </div>
      </PageLayout>
    )
  }

  // Completed games: use IdentityHeader + TabNav
  // Blueprint 2.3: two tabs. The narrative (overview + analytics, led by the verdict) is "The game";
  // the full player/goalie tables are "Box score".
  const tabs = [
    { value: 'game', label: 'The game' },
    { value: 'box', label: 'Box score' }
  ]

  return (
    <PageLayout>
      <div className="game-detail">
        <PageCard
          back={{ to: '/games', label: 'Games' }}
          header={
            <GameMasthead
              away={away_team.team_abbrev}
              home={home_team.team_abbrev}
              awayColor={awayTeamColor}
              homeColor={homeTeamColor}
              awayScore={away_team.score}
              homeScore={home_team.score}
              status={[
                seriesLabel(gameDetail.game_id) || 'Final',
                new Date(gameDetail.game_date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }),
                gameDetail.venue_name,
                !seriesLabel(gameDetail.game_id) ? gameTypeLabel(gameDetail.game_id) : '',
              ].filter(Boolean).join('  ·  ')}
            />
          }
          controls={
            <TabNav
              tabs={tabs}
              activeTab={activeTab}
              onChange={handleTabChange}
            />
          }
        >
          <CompletedGameTabContent
            activeTab={activeTab}
            gameDetail={gameDetail}
            playerStats={playerStats}
            homeTeamColor={homeTeamColor}
            awayTeamColor={awayTeamColor}
          />
        </PageCard>
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
  if (activeTab === 'box') {
    return <PlayersTab gameDetail={gameDetail} playerStats={playerStats} homeTeamColor={homeTeamColor} awayTeamColor={awayTeamColor} />
  }
  // "The game" (K1–K8): verdict + moments + comparison lead (GameNarrative), then the timeline,
  // shot map, who-drove, and receipts (AnalyticsTab, deduped). The old Overview cards — insight strip,
  // game-flow teaser, top performers, matchup context, standalone team stats, goalie duel — are gone;
  // the scoring timeline moves to Box score.
  return (
    <>
      <GameNarrative
        game={gameDetail}
        timeline={
          <GameTimelineStack
            gameId={gameDetail.game_id}
            homeTeamId={gameDetail.home_team.team_id}
            awayTeamId={gameDetail.away_team.team_id}
            homeAbbrev={gameDetail.home_team.team_abbrev}
            awayAbbrev={gameDetail.away_team.team_abbrev}
            homeColor={homeTeamColor}
            awayColor={awayTeamColor}
          />
        }
      />
      <div className="page-divider" />
      <AnalyticsTab gameDetail={gameDetail} playerStats={playerStats} homeTeamColor={homeTeamColor} awayTeamColor={awayTeamColor} />
    </>
  )
}

// Overview Tab - Complete implementation with additional data fetching
const lastNameOf = (name: string) => (name || '').trim().split(' ').slice(-1)[0] || name


// Weighted single-game impact score for skaters (inspired by Game Score).

function PanelHeader({ title, subtitle }: { title: string; subtitle?: string; isNew?: boolean }) {
  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text-primary)', margin: 0 }}>{title}</h3>
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
function GoalieDangerPanel({ gameId }: { gameId: number }) {
  const [rows, setRows] = useState<GoalieDangerStat[]>([])
  // NHL Edge second opinion (season last-10 save %) per goalie, fetched on demand (Phase 2.5)
  const [edge, setEdge] = useState<Record<number, number | null>>({})
  useEffect(() => { let a = true; getGameGoalieDanger(gameId).then(d => { if (a) setRows(d) }).catch(() => {}); return () => { a = false } }, [gameId])
  useEffect(() => {
    let active = true
    rows.forEach(g => {
      getGoalieSeason(g.player_id).then(s => {
        if (active) setEdge(prev => ({ ...prev, [g.player_id]: s.edge_last10_save_pct }))
      }).catch(() => {})
    })
    return () => { active = false }
  }, [rows])
  if (rows.length === 0) return null
  const best = [...rows].sort((x, y) => y.gsax - x.gsax)[0]
  const swing = rows.length >= 2 ? Math.abs(rows[0].gsax - rows[1].gsax) : Math.abs(best.gsax)
  // K7/F1: neutral title; "stole one" language only when the danger-GSAx licenses a theft (≥ 1.5).
  const title = best.gsax >= 1.5 ? `${lastNameOf(best.goalie_name)} stole one` : 'Goaltending'
  const hasEdge = Object.values(edge).some(v => v != null)
  return (
    <section className="overview-card">
      <PanelHeader title={title} subtitle="Goals saved above expected, by shot danger" isNew />
      <table className="analytics-table">
        <thead>
          <tr><th></th><th>High</th><th>Med</th><th>Low</th><th>GSAx</th>{hasEdge && <th title="NHL Edge last-10 save %, an independent measured second opinion">NHL Edge</th>}</tr>
        </thead>
        <tbody>
          {rows.map(g => (
            <tr key={g.player_id}>
              <td>{lastNameOf(g.goalie_name)} <span style={{ color: 'var(--color-text-muted)', fontWeight: 400 }}>{g.team_abbrev}</span></td>
              <td>{g.high_saves}/{g.high_shots}</td>
              <td>{g.med_saves}/{g.med_shots}</td>
              <td>{g.low_saves}/{g.low_shots}</td>
              <td style={{ color: g.gsax >= 0 ? 'var(--color-success)' : 'var(--color-danger)', fontWeight: 700 }}>{g.gsax >= 0 ? '+' : ''}{g.gsax.toFixed(2)}</td>
              {hasEdge && <td style={{ color: 'var(--color-text-muted)' }}>{edge[g.player_id] != null ? `.${Math.round((edge[g.player_id] as number) * 1000)}` : '—'}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length >= 2 && <PanelCaption>A {swing.toFixed(1)}-goal swing between the two creases.</PanelCaption>}
    </section>
  )
}

// "Control and danger" — team rate bars, away left / home right. The Adjusted toggle
// (Phase 2.3) swaps Corsi/xG shares for their score-state-adjusted variants and the
// hits/giveaways/takeaways rows for their rink (scorer-bias) adjusted counts.
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

  // Final order (K1–K8): the timeline + comparison live in GameNarrative above; here the shot map,
  // who drove, then the receipts two-col (period breakdown, shot quality, goaltending, rolling context).
  // Special-teams and control-and-danger folded into the comparison; goalie duel merged into one panel.
  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: 'var(--space-2) 0' }}>
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

      <div style={{ marginBottom: 'var(--space-10)' }}>
        <SkaterImpactTable gameId={game_id} />
      </div>

      <h2 className="page-region-title" style={{ marginBottom: 'var(--space-4)' }}>Receipts</h2>
      {/* V4: two explicit height-assigned columns so neither strands whitespace. */}
      <div className="gd-receipts">
        <div className="gd-receipts__col">
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
        <div className="gd-receipts__col">
          <ShotQualityLadder gameId={game_id} />
          <GoalieDangerPanel gameId={game_id} />
        </div>
      </div>
    </div>
  )
}

// Players Tab - Rebuilt per PART 2 specifications
// K2: compact scoring summary — table-stakes reference at the top of Box score.
function ScoringSummary({ gameId, homeTeamId }: { gameId: number; homeTeamId: number }) {
  const [goals, setGoals] = useState<GoalDetail[]>([])
  useEffect(() => { let a = true; getGameGoals(gameId).then(d => { if (a) setGoals(d) }).catch(() => {}); return () => { a = false } }, [gameId])
  if (goals.length === 0) return null
  let home = 0, away = 0
  const rows = [...goals].sort((x, y) => x.game_time_seconds - y.game_time_seconds).map((g) => {
    if (g.team_id === homeTeamId) home++; else away++
    const period = g.game_time_seconds < 3600 ? Math.floor(g.game_time_seconds / 1200) + 1 : 4
    return { ...g, periodLabel: period > 3 ? 'OT' : `P${period}`, scoreAfter: `${away}–${home}` }
  })
  return (
    <section className="scoring-summary">
      <h2 className="page-region-title">Scoring summary</h2>
      <div className="scoring-summary__rows">
        {rows.map((g, i) => (
          <div className="scoring-summary__row" key={i}>
            <span className="scoring-summary__per mono">{g.periodLabel}</span>
            <span className="scoring-summary__time mono">{g.time_in_period}</span>
            <span className="scoring-summary__team mono">{g.team_abbrev}</span>
            <span className="scoring-summary__scorer">{g.scorer_name ?? 'Goal'}{g.assists?.length ? <span className="scoring-summary__assists"> ({g.assists.join(', ')})</span> : null}</span>
            {g.strength && g.strength !== 'EV' && <span className="scoring-summary__strength">{g.strength}</span>}
            <span className="scoring-summary__score mono">{g.scoreAfter}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

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
        background: 'var(--color-bg-elevated)',
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
              background: 'var(--color-bg-elevated)',
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
      <ScoringSummary gameId={gameDetail.game_id} homeTeamId={home_team.team_id} />
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
            background: 'var(--color-bg-elevated)',
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
                background: 'var(--color-bg-elevated)',
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
                background: 'var(--color-bg-elevated)',
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
