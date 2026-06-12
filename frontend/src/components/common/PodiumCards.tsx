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
  function PlayerCard({ player, rank }: { player: PodiumPlayer; rank: number }) {
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
        style={{ borderLeftColor: player.accentColor }}
      >
        <span className="podium-card__rank">{rank}</span>

        <div className="podium-card__headshot-container">
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
            alt=""
            aria-hidden="true"
            className="podium-card__team-logo"
          />
        </div>

        <div className="podium-card__info">
          <div className="podium-card__name-row">
            <span className="podium-card__name">{player.name}</span>
            <span className="podium-card__position">{player.position}</span>
          </div>
          <div className="podium-card__stat-line mono">{player.statLine}</div>
        </div>

        {player.highlight && (
          <span
            className="podium-card__highlight"
            style={{ backgroundColor: player.accentColor }}
          >
            {player.highlight}
          </span>
        )}
      </Link>
    );
  }

  return (
    <div className="podium-cards">
      {title && <h3 className="podium-cards__title">{title}</h3>}

      <div className="podium-cards__grid">
        {players.slice(0, 3).map((player, i) => (
          <PlayerCard key={player.playerId} player={player} rank={i + 1} />
        ))}
      </div>
    </div>
  );
}
