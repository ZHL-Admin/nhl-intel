import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Game } from '../../api/types'
import { Badge, PossessionBar } from '../common'
import { getTeamLogoUrl, getTeamColor } from '../../utils/teams'
import './GameCard.css'

interface GameCardProps {
  game: Game
}

function GameCard({ game }: GameCardProps) {
  const navigate = useNavigate()
  const [homeLogoError, setHomeLogoError] = useState(false)
  const [awayLogoError, setAwayLogoError] = useState(false)

  const handleClick = () => {
    navigate(`/games/${game.game_id}`)
  }

  const handleTeamClick = (e: React.MouseEvent, teamId: number) => {
    e.stopPropagation()
    navigate(`/teams/${teamId}`)
  }

  const renderTeamLogo = (abbrev: string, hasError: boolean, onError: () => void) => {
    if (hasError) {
      return <div className="game-card__team-logo-fallback">{abbrev}</div>
    }
    return (
      <img
        src={getTeamLogoUrl(abbrev)}
        alt={`${abbrev} logo`}
        className="game-card__team-logo"
        onError={onError}
      />
    )
  }

  const generateNote = (): string => {
    if (game.ai_note) return game.ai_note

    if (game.is_preview) {
      const homeRank = game.home_cf_rank || 16
      const awayRank = game.away_cf_rank || 16
      if (homeRank < awayRank - 5) {
        return `${game.home_team_abbrev} has a significant possession advantage this season`
      } else if (awayRank < homeRank - 5) {
        return `${game.away_team_abbrev} has a significant possession advantage this season`
      }
      return 'Evenly matched teams based on season metrics'
    }

    if (game.home_cf_pct && game.away_cf_pct) {
      const homeCF = game.home_cf_pct
      const awayCF = game.away_cf_pct
      const diff = Math.abs(homeCF - awayCF)

      if (diff > 10) {
        const leader = homeCF > awayCF ? game.home_team_abbrev : game.away_team_abbrev
        return `${leader} dominated possession despite the score`
      } else if (diff < 3) {
        return 'Even possession throughout the game'
      }
    }

    return 'Competitive matchup'
  }

  if (game.is_preview) {
    return (
      <div className="game-card game-card--preview" onClick={handleClick}>
        <Badge variant="preview" />

        <div className="game-card__header">
          <div className="game-card__team">
            {renderTeamLogo(game.away_team_abbrev, awayLogoError, () => setAwayLogoError(true))}
            <span
              className="game-card__team-abbrev game-card__team-abbrev--clickable"
              onClick={(e) => handleTeamClick(e, game.away_team_id)}
            >
              {game.away_team_abbrev}
            </span>
          </div>
          <div className="game-card__vs">vs</div>
          <div className="game-card__team">
            <span
              className="game-card__team-abbrev game-card__team-abbrev--clickable"
              onClick={(e) => handleTeamClick(e, game.home_team_id)}
            >
              {game.home_team_abbrev}
            </span>
            {renderTeamLogo(game.home_team_abbrev, homeLogoError, () => setHomeLogoError(true))}
          </div>
        </div>

        <div className="game-card__meta">
          <span className="game-card__time">{game.game_time || 'TBD'}</span>
          {game.home_cf_rank && game.away_cf_rank && (
            <span className="game-card__ranks">
              {game.away_team_abbrev} #{game.away_cf_rank} CF% vs {game.home_team_abbrev} #{game.home_cf_rank} CF%
            </span>
          )}
        </div>

        <div className="game-card__note">{generateNote()}</div>
      </div>
    )
  }

  return (
    <div className={`game-card ${game.is_live ? 'game-card--live' : ''}`} onClick={handleClick}>
      {game.is_live && <Badge variant="live" />}

      <div className="game-card__header">
        <div className="game-card__team">
          {renderTeamLogo(game.away_team_abbrev, awayLogoError, () => setAwayLogoError(true))}
          <span
            className="game-card__team-abbrev game-card__team-abbrev--clickable"
            onClick={(e) => handleTeamClick(e, game.away_team_id)}
          >
            {game.away_team_abbrev}
          </span>
        </div>
        <div className="game-card__score mono">
          <span>{game.away_score ?? 0}</span>
          <span className="game-card__score-separator">-</span>
          <span>{game.home_score ?? 0}</span>
        </div>
        <div className="game-card__team">
          <span
            className="game-card__team-abbrev game-card__team-abbrev--clickable"
            onClick={(e) => handleTeamClick(e, game.home_team_id)}
          >
            {game.home_team_abbrev}
          </span>
          {renderTeamLogo(game.home_team_abbrev, homeLogoError, () => setHomeLogoError(true))}
        </div>
      </div>

      {game.is_live && game.period && (
        <div className="game-card__live-status">
          {game.period} {game.time_remaining && `- ${game.time_remaining}`}
        </div>
      )}

      {game.home_cf_pct !== undefined && game.away_cf_pct !== undefined && (
        <div className="game-card__possession">
          <PossessionBar
            homeValue={game.home_cf_pct}
            awayValue={game.away_cf_pct}
            homeColor={getTeamColor(game.home_team_abbrev)}
            awayColor={getTeamColor(game.away_team_abbrev)}
            height={36}
          />
        </div>
      )}

      <div className="game-card__note">{generateNote()}</div>
    </div>
  )
}

export default GameCard
