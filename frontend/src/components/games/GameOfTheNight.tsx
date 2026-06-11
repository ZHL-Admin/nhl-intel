import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Game } from '../../api/types';
import MiniWorm from '../common/MiniWorm';
import { getTeamLogoUrl, getTeamColor } from '../../utils/teams';
import './GameOfTheNight.css';

interface GameOfTheNightProps {
  game: Game;
}

export default function GameOfTheNight({ game }: GameOfTheNightProps) {
  const navigate = useNavigate();
  const [homeLogoError, setHomeLogoError] = useState(false);
  const [awayLogoError, setAwayLogoError] = useState(false);

  const handleClick = () => {
    navigate(`/games/${game.game_id}`);
  };

  const renderTeamLogo = (abbrev: string, hasError: boolean, onError: () => void) => {
    if (hasError) {
      return <div className="game-of-night__logo-fallback">{abbrev}</div>;
    }
    return (
      <img
        src={getTeamLogoUrl(abbrev)}
        alt={`${abbrev} logo`}
        className="game-of-night__logo"
        onError={onError}
      />
    );
  };

  // Generate mock xG worm data (in real implementation, this would come from API)
  const generateMockXGData = () => {
    const points = [];
    for (let time = 0; time <= 3600; time += 300) {
      const diff = Math.random() * 2 - 1;
      points.push({ time, diff });
    }
    return points;
  };

  const xgData = generateMockXGData();

  const generateNote = (): string => {
    if (game.ai_note) return game.ai_note;

    if (game.home_cf_pct && game.away_cf_pct) {
      const homeCF = game.home_cf_pct;
      const awayCF = game.away_cf_pct;
      const diff = Math.abs(homeCF - awayCF);

      if (diff > 10) {
        const leader = homeCF > awayCF ? game.home_team_abbrev : game.away_team_abbrev;
        return `${leader} controlled 60%+ of shot attempts in a commanding performance`;
      } else if (diff < 3) {
        return 'Back-and-forth battle with neither team able to establish control';
      }
    }

    return 'Closely contested game throughout all three periods';
  };

  return (
    <div className="game-of-night" onClick={handleClick}>
      <div className="game-of-night__label">Game of the Night</div>

      <div className="game-of-night__content">
        <div className="game-of-night__left">
          <div className="game-of-night__matchup">
            <div className="game-of-night__team">
              {renderTeamLogo(game.away_team_abbrev, awayLogoError, () => setAwayLogoError(true))}
              <div>
                <div className="game-of-night__team-abbrev">{game.away_team_abbrev}</div>
                <div className="game-of-night__score mono">{game.away_score ?? 0}</div>
              </div>
            </div>

            <div className="game-of-night__team">
              <div style={{ textAlign: 'right' }}>
                <div className="game-of-night__team-abbrev">{game.home_team_abbrev}</div>
                <div className="game-of-night__score mono">{game.home_score ?? 0}</div>
              </div>
              {renderTeamLogo(game.home_team_abbrev, homeLogoError, () => setHomeLogoError(true))}
            </div>
          </div>

          <div className="game-of-night__note">{generateNote()}</div>
        </div>

        <div className="game-of-night__right">
          <div className="game-of-night__worm-label">Expected Goals Flow</div>
          <MiniWorm
            data={xgData}
            homeColor={getTeamColor(game.home_team_abbrev)}
            awayColor={getTeamColor(game.away_team_abbrev)}
            width={400}
            height={80}
          />
        </div>
      </div>
    </div>
  );
}
