import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { PageLayout, SkeletonLoader, Badge, PossessionBar, Tooltip } from '../components/common'
import GameHeader from '../components/games/GameHeader'
import ShotMap from '../components/visualizations/ShotMap'
import { getGameDetail, getGamePlayerStats, getGameShots } from '../api/games'
import { GameDetail as GameDetailType, GamePlayerStats, GameShots } from '../api/types'
import { getTeamLogoUrl, getTeamColor } from '../utils/teams'
import './GameDetail.css'

function GameDetail() {
  const { gameId } = useParams<{ gameId: string }>()
  const navigate = useNavigate()

  const [gameDetail, setGameDetail] = useState<GameDetailType | null>(null)
  const [playerStats, setPlayerStats] = useState<GamePlayerStats | null>(null)
  const [shotData, setShotData] = useState<GameShots | null>(null)
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
        const [detail, players, shots] = await Promise.all([
          getGameDetail(parseInt(gameId)),
          getGamePlayerStats(parseInt(gameId)),
          getGameShots(parseInt(gameId))
        ])

        setGameDetail(detail)
        setPlayerStats(players)
        setShotData(shots)
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
          <CompletedGameContent gameDetail={gameDetail} playerStats={playerStats} shotData={shotData} />
        )}
      </div>
    </PageLayout>
  )
}

function CompletedGameContent({
  gameDetail,
  playerStats,
  shotData
}: {
  gameDetail: GameDetailType
  playerStats: GamePlayerStats | null
  shotData: GameShots | null
}) {
  const { home_team, away_team } = gameDetail

  const xgf_pct_home = home_team.xgf && home_team.xga
    ? (home_team.xgf / (home_team.xgf + home_team.xga)) * 100
    : null

  const xgf_pct_away = away_team.xgf && away_team.xga
    ? (away_team.xgf / (away_team.xgf + away_team.xga)) * 100
    : null

  return (
    <>
      {/* Team Comparison Panel */}
      <section className="game-detail__comparison-panel">

        {/* Metrics */}
        <div className="comparison-panel__metrics">
          {/* CF% */}
          {away_team.cf_pct !== null && home_team.cf_pct !== null && (
            <div className="comparison-metric">
              <div className="comparison-metric__label">
                <Tooltip content="Corsi For Percentage at 5v5 - shot attempts for divided by total shot attempts">
                  CF%
                </Tooltip>
              </div>
              <div className="comparison-metric__bar">
                <PossessionBar
                  homeValue={home_team.cf_pct * 100}
                  awayValue={away_team.cf_pct * 100}
                  homeColor={getTeamColor(home_team.team_abbrev)}
                  awayColor={getTeamColor(away_team.team_abbrev)}
                />
              </div>
            </div>
          )}

          {/* xGF% */}
          {xgf_pct_away !== null && xgf_pct_home !== null && (
            <div className="comparison-metric">
              <div className="comparison-metric__label">
                <Tooltip content="Expected Goals For Percentage at 5v5 - expected goals for divided by total expected goals">
                  xGF%
                </Tooltip>
              </div>
              <div className="comparison-metric__bar">
                <PossessionBar
                  homeValue={xgf_pct_home}
                  awayValue={xgf_pct_away}
                  homeColor={getTeamColor(home_team.team_abbrev)}
                  awayColor={getTeamColor(away_team.team_abbrev)}
                />
              </div>
            </div>
          )}

          {/* HDCF / HDCA */}
          {away_team.hdcf_per60 !== null && home_team.hdcf_per60 !== null && (
            <div className="comparison-metric">
              <div className="comparison-metric__label">
                <Tooltip content="High Danger Chances For/Against per 60 minutes at 5v5">
                  HDCF / HDCA
                </Tooltip>
              </div>
              <div className="comparison-metric__side-by-side">
                <div className="comparison-metric__value">
                  {away_team.hdcf_per60.toFixed(1)} / {away_team.hdca_per60?.toFixed(1) ?? '-'}
                </div>
                <div className="comparison-metric__value">
                  {home_team.hdcf_per60.toFixed(1)} / {home_team.hdca_per60?.toFixed(1) ?? '-'}
                </div>
              </div>
            </div>
          )}

          {/* Zone Entry Success Rate */}
          {away_team.zone_entry_success_rate !== null && home_team.zone_entry_success_rate !== null && (
            <div className="comparison-metric">
              <div className="comparison-metric__label">
                <Tooltip content="Percentage of zone entries that were controlled (with possession)">
                  Zone Entry %
                </Tooltip>
              </div>
              <div className="comparison-metric__side-by-side">
                <div className="comparison-metric__value">
                  {(away_team.zone_entry_success_rate * 100).toFixed(1)}%
                </div>
                <div className="comparison-metric__value">
                  {(home_team.zone_entry_success_rate * 100).toFixed(1)}%
                </div>
              </div>
            </div>
          )}

          {/* Shot Attempts */}
          {away_team.shot_attempts !== null && home_team.shot_attempts !== null && (
            <div className="comparison-metric">
              <div className="comparison-metric__label">
                <Tooltip content="Total shot attempts (shots, misses, and blocks) at 5v5">
                  Shot Attempts
                </Tooltip>
              </div>
              <div className="comparison-metric__side-by-side">
                <div className="comparison-metric__value">
                  {away_team.shot_attempts}
                </div>
                <div className="comparison-metric__value">
                  {home_team.shot_attempts}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Shot Map */}
      {shotData && shotData.home_shots.length > 0 && shotData.away_shots.length > 0 ? (
        <section className="game-detail__shot-map">
          <ShotMap
            mode="game"
            homeShots={shotData.home_shots}
            awayShots={shotData.away_shots}
            homeTeamColor={getTeamColor(home_team.team_abbrev)}
            awayTeamColor={getTeamColor(away_team.team_abbrev)}
            homeTeamAbbrev={home_team.team_abbrev}
            awayTeamAbbrev={away_team.team_abbrev}
          />
        </section>
      ) : (
        <section className="game-detail__shot-map-placeholder">
          <h2 className="game-detail__section-title">Shot Map</h2>
          <div className="shot-map-placeholder">
            <p className="shot-map-placeholder__label">Shot data unavailable</p>
          </div>
        </section>
      )}

      {/* Roster Section */}
      {playerStats && (
        <section className="game-detail__roster-section">
          <h2 className="game-detail__section-title">Rosters</h2>
          <div className="roster-section">
            {/* Away Team Roster */}
            <div className="roster-section__column">
              <div className="roster-section__header">
                <img
                  src={getTeamLogoUrl(away_team.team_abbrev)}
                  alt={away_team.team_abbrev}
                  className="roster-section__logo"
                />
                <span>{away_team.team_abbrev}</span>
              </div>
              <div className="roster-section__players">
                {playerStats.away_players.map((player) => (
                  <PlayerRow key={player.player_id} player={player} />
                ))}
              </div>
            </div>

            {/* Home Team Roster */}
            <div className="roster-section__column">
              <div className="roster-section__header">
                <img
                  src={getTeamLogoUrl(home_team.team_abbrev)}
                  alt={home_team.team_abbrev}
                  className="roster-section__logo"
                />
                <span>{home_team.team_abbrev}</span>
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

function PlayerRow({ player }: { player: any }) {
  const navigate = useNavigate()

  const handleClick = () => {
    navigate(`/players/${player.player_id}`)
  }

  return (
    <div className="player-row" onClick={handleClick}>
      <div className="player-row__info">
        <div className="player-row__avatar">
          {player.player_name.split(' ').map((n: string) => n[0]).join('')}
        </div>
        <div className="player-row__details">
          <div className="player-row__name">
            {player.player_name}
            {player.hot_cold_flag && player.hot_cold_flag !== 'neutral' && (
              <Badge variant={player.hot_cold_flag as 'hot' | 'cold'} />
            )}
          </div>
          <div className="player-row__position">{player.position}</div>
        </div>
      </div>
      <div className="player-row__stats">
        {player.toi !== null && (
          <div className="player-row__stat">
            <span className="player-row__stat-label">TOI</span>
            <span className="player-row__stat-value">{player.toi.toFixed(1)}</span>
          </div>
        )}
        {player.goals !== null && (
          <div className="player-row__stat">
            <span className="player-row__stat-label">G</span>
            <span className="player-row__stat-value">{player.goals}</span>
          </div>
        )}
        {player.assists !== null && (
          <div className="player-row__stat">
            <span className="player-row__stat-label">A</span>
            <span className="player-row__stat-value">{player.assists}</span>
          </div>
        )}
        {player.ixg !== null && (
          <div className="player-row__stat">
            <span className="player-row__stat-label">ixG</span>
            <span className="player-row__stat-value">{player.ixg.toFixed(2)}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default GameDetail
