import { useState, useEffect } from 'react';
import ChartPanel from '../common/ChartPanel';
import { getGamePlayerStats } from '../../api/games';
import { PlayerGameStats } from '../../api/types';
import { getTeamLogoUrl, getTeamColorAccent } from '../../utils/teams';
import './GoaltendingBox.css';

interface GoaltendingBoxProps {
  gameId: number;
  homeTeamId: number;
  awayTeamId: number;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
}

export default function GoaltendingBox({
  gameId,
  homeTeamId: _homeTeamId,
  awayTeamId: _awayTeamId,
  homeTeamAbbrev,
  awayTeamAbbrev
}: GoaltendingBoxProps) {
  const [homeGoalies, setHomeGoalies] = useState<PlayerGameStats[]>([]);
  const [awayGoalies, setAwayGoalies] = useState<PlayerGameStats[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchGoalies = async () => {
      try {
        const data = await getGamePlayerStats(gameId);
        const homeGs = data.home_players.filter(p => p.position === 'G');
        const awayGs = data.away_players.filter(p => p.position === 'G');
        setHomeGoalies(homeGs);
        setAwayGoalies(awayGs);
      } catch (err) {
        console.error('Error fetching goalie stats:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchGoalies();
  }, [gameId]);

  if (loading || (homeGoalies.length === 0 && awayGoalies.length === 0)) {
    return null;
  }

  const renderGoalieCard = (goalie: PlayerGameStats, teamAbbrev: string) => {
    const teamColor = getTeamColorAccent(teamAbbrev);

    return (
      <div
        key={goalie.player_id}
        className="goalie-card"
        style={{ borderTopColor: teamColor }}
      >
        <div className="goalie-card__header">
          <img
            src={getTeamLogoUrl(teamAbbrev)}
            alt={teamAbbrev}
            className="goalie-card__logo"
          />
          <div className="goalie-card__info">
            <div className="goalie-card__name">{goalie.player_name}</div>
            <div className="goalie-card__position">Goaltender</div>
          </div>
        </div>

        <div className="goalie-card__stats">
          <div className="goalie-card__stat">
            <span className="goalie-card__stat-label">TOI</span>
            <span className="goalie-card__stat-value mono">
              {goalie.toi !== null ? goalie.toi.toFixed(1) : '-'}
            </span>
          </div>
          {/* SA, GA, SV, SV% would require additional data from backend */}
          <div className="goalie-card__stat">
            <span className="goalie-card__stat-label">Stats</span>
            <span className="goalie-card__stat-value">Available soon</span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <ChartPanel
      title="Goaltending"
      subtitle="Goaltender performance"
      expandable={false}
    >
      <div className="goaltending-box">
        <div className="goaltending-box__cards">
          <div className="goaltending-box__column">
            {awayGoalies.map(g => renderGoalieCard(g, awayTeamAbbrev))}
          </div>
          <div className="goaltending-box__column">
            {homeGoalies.map(g => renderGoalieCard(g, homeTeamAbbrev))}
          </div>
        </div>
      </div>
    </ChartPanel>
  );
}
