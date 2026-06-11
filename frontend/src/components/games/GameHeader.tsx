import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Badge } from '../common'
import { getTeamLogoUrl, getTeamName, getTeamColorWash, formatGameDate } from '../../utils/teams'
import { GameDetail } from '../../api/types'
import './GameHeader.css'

interface GameHeaderProps {
  gameDetail: GameDetail
}

function GameHeader({ gameDetail }: GameHeaderProps) {
  const navigate = useNavigate()
  const { home_team, away_team, is_preview, game_date, venue_name } = gameDetail

  const handleBack = () => {
    navigate('/games')
  }

  return (
    <div className="game-header-container">
      {/* Back Navigation */}
      <button className="game-header__back" onClick={handleBack}>
        <ArrowLeft size={16} />
        <span>Back to Games</span>
      </button>

      {/* Header with team color accents */}
      <div
        className="game-header"
        style={{
          background: `linear-gradient(to right, ${getTeamColorWash(away_team.team_abbrev)} 0%, var(--color-bg-base) 30%, var(--color-bg-base) 70%, ${getTeamColorWash(home_team.team_abbrev)} 100%)`
        }}
      >
        {/* Away Team */}
        <div className="game-header__team game-header__team--away">
          <img
            src={getTeamLogoUrl(away_team.team_abbrev)}
            alt={away_team.team_abbrev}
            className="game-header__logo"
          />
          <div className="game-header__team-info">
            <div className="game-header__team-name">
              {getTeamName(away_team.team_abbrev)}
            </div>
            <div className="game-header__team-label">Away</div>
          </div>
        </div>

        {/* Score / VS */}
        <div className="game-header__center">
          {is_preview ? (
            <>
              <div className="game-header__vs">vs</div>
              <div className="game-header__game-time">{/* Game time would go here if available */}</div>
            </>
          ) : (
            <>
              <div className="game-header__score">
                <span className="game-header__score-value">{away_team.score ?? 0}</span>
                <span className="game-header__score-separator">—</span>
                <span className="game-header__score-value">{home_team.score ?? 0}</span>
              </div>

              {/* Period-by-Period Score Grid */}
              <div className="period-score-grid">
                <div className="period-score-grid__header">
                  <div className="period-score-grid__cell period-score-grid__cell--empty"></div>
                  <div className="period-score-grid__cell period-score-grid__cell--header mono">1</div>
                  <div className="period-score-grid__cell period-score-grid__cell--header mono">2</div>
                  <div className="period-score-grid__cell period-score-grid__cell--header mono">3</div>
                  <div className="period-score-grid__cell period-score-grid__cell--header mono">T</div>
                </div>
                <div className="period-score-grid__row">
                  <div className="period-score-grid__cell period-score-grid__cell--team">
                    <img
                      src={getTeamLogoUrl(away_team.team_abbrev)}
                      alt={away_team.team_abbrev}
                      className="period-score-grid__logo"
                    />
                  </div>
                  <div className="period-score-grid__cell mono">{away_team.gf_p1 ?? 0}</div>
                  <div className="period-score-grid__cell mono">{away_team.gf_p2 ?? 0}</div>
                  <div className="period-score-grid__cell mono">{away_team.gf_p3 ?? 0}</div>
                  <div className="period-score-grid__cell mono">{away_team.score ?? 0}</div>
                </div>
                <div className="period-score-grid__row">
                  <div className="period-score-grid__cell period-score-grid__cell--team">
                    <img
                      src={getTeamLogoUrl(home_team.team_abbrev)}
                      alt={home_team.team_abbrev}
                      className="period-score-grid__logo"
                    />
                  </div>
                  <div className="period-score-grid__cell mono">{home_team.gf_p1 ?? 0}</div>
                  <div className="period-score-grid__cell mono">{home_team.gf_p2 ?? 0}</div>
                  <div className="period-score-grid__cell mono">{home_team.gf_p3 ?? 0}</div>
                  <div className="period-score-grid__cell mono">{home_team.score ?? 0}</div>
                </div>
              </div>
            </>
          )}

          <div className="game-header__game-type">
            <span>Regular Season</span>
            {is_preview && <Badge variant="preview" />}
          </div>

          <div className="game-header__meta">
            <span>{formatGameDate(game_date)}</span>
            {venue_name && (
              <>
                <span className="game-header__meta-separator">•</span>
                <span>{venue_name}</span>
              </>
            )}
          </div>
        </div>

        {/* Home Team */}
        <div className="game-header__team game-header__team--home">
          <div className="game-header__team-info game-header__team-info--home">
            <div className="game-header__team-name">
              {getTeamName(home_team.team_abbrev)}
            </div>
            <div className="game-header__team-label">Home</div>
          </div>
          <img
            src={getTeamLogoUrl(home_team.team_abbrev)}
            alt={home_team.team_abbrev}
            className="game-header__logo"
          />
        </div>
      </div>
    </div>
  )
}

export default GameHeader
