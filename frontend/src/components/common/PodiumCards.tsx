import { useState } from 'react';
import { Link } from 'react-router-dom';
import { getPlayerHeadshotUrl } from '../../utils/teams';
import './PodiumCards.css';

export interface PodiumPlayer {
  playerId: number;
  name: string;
  teamAbbrev: string;
  teamLogo: string;
  position: string;
  statLine: string;
  highlight?: string;
  accentColor: string;
  seasonId?: string; // Optional override for specific season
}

interface PodiumCardsProps {
  players: PodiumPlayer[];
  title?: string;
}

export default function PodiumCards({ players, title }: PodiumCardsProps) {
  if (players.length === 0) return null;

  const getInitials = (name: string): string => {
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  };

  // Component for each player card with headshot error handling
  function PlayerCard({ player }: { player: PodiumPlayer }) {
    const [headshotError, setHeadshotError] = useState(false);
    const headshotUrl = getPlayerHeadshotUrl(
      player.playerId,
      player.teamAbbrev,
      player.seasonId
    );

    return (
      <Link
        key={player.playerId}
        to={`/players/${player.playerId}`}
        className="podium-card"
        style={{ borderTopColor: player.accentColor }}
      >
        <div className="podium-card__headshot-container"
        >
          {!headshotError ? (
            <img
              src={headshotUrl}
              alt={player.name}
              className="podium-card__headshot"
              onError={() => setHeadshotError(true)}
            />
          ) : (
            <div className="podium-card__headshot podium-card__headshot--fallback">
              {getInitials(player.name)}
            </div>
          )}
          <img
            src={player.teamLogo}
            alt="Team"
            className="podium-card__team-logo"
          />
        </div>

        <div className="podium-card__name-container">
        <div className="podium-card__name">{player.name}</div>
        <div className="podium-card__position">{player.position}</div>
        </div>
        <div className="podium-card__stat-line mono">{player.statLine}</div>

        {player.highlight && (
          <div
            className="podium-card__highlight"
            style={{ backgroundColor: player.accentColor }}
          >
            {player.highlight}
          </div>
        )}
      </Link>
    );
  }

  return (
    <div className="podium-cards">
      {title && <h3 className="podium-cards__title">{title}</h3>}

      <div className="podium-cards__grid">
        {players.slice(0, 3).map(player => (
          <PlayerCard key={player.playerId} player={player} />
        ))}
      </div>
    </div>
  );
}
