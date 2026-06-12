import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Game } from '../../api/types';
import MiniWorm from '../common/MiniWorm';
import { getGameXGWorm } from '../../api/games';
import { getTeamLogoUrl, getTeamColor } from '../../utils/teams';
import './GameOfTheNight.css';

interface GameOfTheNightProps {
  game: Game;
}

export default function GameOfTheNight({ game }: GameOfTheNightProps) {
  const navigate = useNavigate();
  const [homeLogoError, setHomeLogoError] = useState(false);
  const [awayLogoError, setAwayLogoError] = useState(false);
  const [wormData, setWormData] = useState<{ time: number; diff: number }[]>([]);
  const [wormGoals, setWormGoals] = useState<{ time: number; label: string }[]>([]);

  useEffect(() => {
    let active = true;
    getGameXGWorm(game.game_id)
      .then((points) => {
        if (!active) return;
        setWormData(points.map((p) => ({ time: p.game_time_seconds, diff: p.cumulative_xg_diff })));
        setWormGoals(
          points
            .filter((p) => p.event_type === 'goal')
            .map((p) => ({ time: p.game_time_seconds, label: p.label || '' }))
        );
      })
      .catch(() => {
        if (active) setWormData([]);
      });
    return () => {
      active = false;
    };
  }, [game.game_id]);

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

        {wormData.length > 0 && (
          <div className="game-of-night__right">
            <div className="game-of-night__worm-label">Expected Goals Flow</div>
            <MiniWorm
              data={wormData}
              goals={wormGoals}
              homeColor={getTeamColor(game.home_team_abbrev)}
              awayColor={getTeamColor(game.away_team_abbrev)}
              width={400}
              height={80}
            />
          </div>
        )}
      </div>
    </div>
  );
}
