import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ChartPanel from '../common/ChartPanel';
import Badge from '../common/Badge';
import { PlayerGameStats } from '../../api/types';
import './GamePlayerStatsTable.css';

interface GamePlayerStatsTableProps {
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeTeamColor: string;
  awayTeamColor: string;
  homePlayers: PlayerGameStats[];
  awayPlayers: PlayerGameStats[];
}

type SortColumn = 'toi' | 'goals' | 'first_assists' | 'second_assists' | 'points' | 'shots' | 'ixg' | 'cf' | 'hdcf' | 'rush_attempts' | 'pim';
type SortDirection = 'asc' | 'desc';

function generateTitle(homePlayers: PlayerGameStats[], awayPlayers: PlayerGameStats[]): string {
  const allPlayers = [...homePlayers, ...awayPlayers];

  // Find highest points
  const topScorer = allPlayers.reduce((max, player) => {
    const points = (player.points || 0);
    const maxPoints = (max.points || 0);
    return points > maxPoints ? player : max;
  }, allPlayers[0]);

  // Find highest ixG
  const topIxg = allPlayers.reduce((max, player) => {
    const ixg = (player.ixg || 0);
    const maxIxg = (max.ixg || 0);
    return ixg > maxIxg ? player : max;
  }, allPlayers[0]);

  if (topScorer.player_id === topIxg.player_id) {
    return `${topScorer.player_name} led all skaters with ${topScorer.points} points and ${(topIxg.ixg || 0).toFixed(2)} expected goals`;
  }

  return `${topScorer.player_name} led with ${topScorer.points} points while ${topIxg.player_name} generated ${(topIxg.ixg || 0).toFixed(2)} expected goals`;
}

function PlayerTable({
  players,
  teamAbbrev: _teamAbbrev,
  teamColor
}: {
  players: PlayerGameStats[];
  teamAbbrev: string;
  teamColor: string;
}) {
  const navigate = useNavigate();
  const [sortColumn, setSortColumn] = useState<SortColumn>('toi');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('desc');
    }
  };

  const sortedPlayers = [...players].sort((a, b) => {
    const aVal = a[sortColumn] ?? -Infinity;
    const bVal = b[sortColumn] ?? -Infinity;

    if (sortDirection === 'asc') {
      return aVal > bVal ? 1 : -1;
    }
    return aVal > bVal ? -1 : 1;
  });

  // Separate goalies and skaters
  const skaters = sortedPlayers.filter(p => p.position !== 'G');
  const goalies = sortedPlayers.filter(p => p.position === 'G');

  return (
    <div className="player-table" style={{ borderTop: `4px solid color-mix(in srgb, ${teamColor} 50%, var(--color-bg-base))`, paddingTop: 'var(--space-3)', borderRadius: 'var(--radius-md)' }}>
      {/* Skaters Table */}
      <div className="player-table__section">
        <table className="stats-table">
          <thead>
            <tr>
              <th className="stats-table__th--left">Player</th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('toi')}>
                TOI {sortColumn === 'toi' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('goals')}>
                G {sortColumn === 'goals' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('first_assists')}>
                A1 {sortColumn === 'first_assists' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('second_assists')}>
                A2 {sortColumn === 'second_assists' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('points')}>
                PTS {sortColumn === 'points' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('shots')}>
                SOG {sortColumn === 'shots' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('ixg')}>
                ixG {sortColumn === 'ixg' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('cf')}>
                iCF {sortColumn === 'cf' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('hdcf')}>
                iHDCF {sortColumn === 'hdcf' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('rush_attempts')}>
                Rush {sortColumn === 'rush_attempts' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="stats-table__th--sortable" onClick={() => handleSort('pim')}>
                PIM {sortColumn === 'pim' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
            </tr>
          </thead>
          <tbody>
            {skaters.map((player) => (
              <tr
                key={player.player_id}
                className="stats-table__row"
                onClick={() => navigate(`/players/${player.player_id}`)}
              >
                <td className="stats-table__player">
                  <div className="stats-table__player-info">
                    <div className="stats-table__avatar">
                      {player.player_name.split(' ').map(n => n[0]).join('')}
                    </div>
                    <div className="stats-table__player-details">
                      <div className="stats-table__player-name">
                        {player.player_name}
                        {player.hot_cold_flag && player.hot_cold_flag !== 'neutral' && (
                          <Badge variant={player.hot_cold_flag as 'hot' | 'cold'} />
                        )}
                      </div>
                      <div className="stats-table__player-position">{player.position}</div>
                    </div>
                  </div>
                </td>
                <td className="mono">{player.toi !== null ? player.toi.toFixed(1) : '-'}</td>
                <td className="mono">{player.goals ?? '-'}</td>
                <td className="mono">{player.first_assists ?? '-'}</td>
                <td className="mono">{player.second_assists ?? '-'}</td>
                <td className="mono">{player.points ?? '-'}</td>
                <td className="mono">{player.shots ?? '-'}</td>
                <td className="mono">
                  {player.ixg !== null ? player.ixg.toFixed(2) : '-'}
                </td>
                <td className="mono">{player.cf ?? '-'}</td>
                <td className="mono">{player.hdcf ?? '-'}</td>
                <td className="mono">{player.rush_attempts ?? '-'}</td>
                <td className="mono">{player.pim ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Goalies Table */}
      {goalies.length > 0 && (
        <div className="player-table__section">
          <h4 className="player-table__section-title">Goalies</h4>
          <table className="stats-table">
            <thead>
              <tr>
                <th className="stats-table__th--left">Player</th>
                <th>TOI</th>
                <th>SA</th>
                <th>SV</th>
                <th>GA</th>
                <th>SV%</th>
              </tr>
            </thead>
            <tbody>
              {goalies.map((player) => (
                <tr
                  key={player.player_id}
                  className="stats-table__row"
                  onClick={() => navigate(`/players/${player.player_id}`)}
                >
                  <td className="stats-table__player">
                    <div className="stats-table__player-info">
                      <div className="stats-table__avatar">
                        {player.player_name.split(' ').map(n => n[0]).join('')}
                      </div>
                      <div className="stats-table__player-details">
                        <div className="stats-table__player-name">{player.player_name}</div>
                        <div className="stats-table__player-position">{player.position}</div>
                      </div>
                    </div>
                  </td>
                  <td className="mono">{player.toi !== null ? player.toi.toFixed(1) : '-'}</td>
                  <td className="mono">-</td>
                  <td className="mono">-</td>
                  <td className="mono">-</td>
                  <td className="mono">-</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function GamePlayerStatsTable({
  homeTeamAbbrev,
  awayTeamAbbrev,
  homeTeamColor,
  awayTeamColor,
  homePlayers,
  awayPlayers
}: GamePlayerStatsTableProps) {
  const title = generateTitle(homePlayers, awayPlayers);

  return (
    <ChartPanel
      title={title}
      subtitle="Individual player performance and contributions"
      expandable={false}
    >
      <div className="game-player-stats">
        <div className="game-player-stats__tables">
          <PlayerTable
            players={awayPlayers}
            teamAbbrev={awayTeamAbbrev}
            teamColor={awayTeamColor}
          />
          <PlayerTable
            players={homePlayers}
            teamAbbrev={homeTeamAbbrev}
            teamColor={homeTeamColor}
          />
        </div>
      </div>
    </ChartPanel>
  );
}
