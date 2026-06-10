import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { PageLayout, SkeletonLoader } from '../components/common'
import GameHeader from '../components/games/GameHeader'
import XGWormChart from '../components/visualizations/XGWormChart'
import TeamComparisonPanel from '../components/visualizations/TeamComparisonPanel'
import ShotMapKDE from '../components/visualizations/ShotMapKDE'
import PeriodBreakdownTable from '../components/visualizations/PeriodBreakdownTable'
import GamePlayerStatsTable from '../components/visualizations/GamePlayerStatsTable'
import RollingContextPanel from '../components/visualizations/RollingContextPanel'
import { getGameDetail, getGamePlayerStats } from '../api/games'
import { GameDetail as GameDetailType, GamePlayerStats, PlayerGameStats } from '../api/types'
import { getTeamLogoUrl, getTeamColor } from '../utils/teams'
import './GameDetail.css'

function GameDetail() {
  const { gameId } = useParams<{ gameId: string }>()
  const navigate = useNavigate()

  const [gameDetail, setGameDetail] = useState<GameDetailType | null>(null)
  const [playerStats, setPlayerStats] = useState<GamePlayerStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

  const { is_preview } = gameDetail

  return (
    <PageLayout>
      <div className="game-detail">
        {/* New Game Header */}
        <GameHeader gameDetail={gameDetail} />

        {/* Team Comparison Panel or Season Matchup Panel */}
        {is_preview ? (
          <PreviewModeContent gameDetail={gameDetail} playerStats={playerStats} />
        ) : (
          <CompletedGameContent gameDetail={gameDetail} playerStats={playerStats} />
        )}
      </div>
    </PageLayout>
  )
}

function CompletedGameContent({
  gameDetail,
  playerStats
}: {
  gameDetail: GameDetailType
  playerStats: GamePlayerStats | null
}) {
  const { home_team, away_team, game_id } = gameDetail
  const homeTeamColor = getTeamColor(home_team.team_abbrev)
  const awayTeamColor = getTeamColor(away_team.team_abbrev)

  return (
    <div className="game-detail__content">
      {/* Section 01: xG Worm Chart */}
      <XGWormChart
        gameId={game_id}
        homeTeamAbbrev={home_team.team_abbrev}
        awayTeamAbbrev={away_team.team_abbrev}
        homeTeamColor={homeTeamColor}
        awayTeamColor={awayTeamColor}
      />

      {/* Section 02: Team Comparison Panel */}
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
      />

      {/* Section 03: KDE Shot Map */}
      <ShotMapKDE
        gameId={game_id}
        homeTeamAbbrev={home_team.team_abbrev}
        awayTeamAbbrev={away_team.team_abbrev}
        homeTeamColor={homeTeamColor}
        awayTeamColor={awayTeamColor}
      />

      {/* Section 04: Period Breakdown Table */}
      <PeriodBreakdownTable
        homeTeamAbbrev={home_team.team_abbrev}
        awayTeamAbbrev={away_team.team_abbrev}
        homeTeamColor={homeTeamColor}
        awayTeamColor={awayTeamColor}
        homeStats={home_team}
        awayStats={away_team}
      />

      {/* Section 05: Player Performance Tables */}
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

      {/* Section 06: Rolling Context Panel */}
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
