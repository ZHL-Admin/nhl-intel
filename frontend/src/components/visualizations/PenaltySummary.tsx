import ChartPanel from '../common/ChartPanel';
import { getTeamLogoUrl, getTeamColorAccent } from '../../utils/teams';
import './PenaltySummary.css';

interface PenaltySummaryProps {
  gameId: number;
  homeTeamId: number;
  awayTeamId: number;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
}

interface Penalty {
  period: number;
  time: string;
  playerName: string;
  teamId: number;
  infraction: string;
  duration: number;
}

export default function PenaltySummary({
  gameId: _gameId,
  homeTeamId,
  awayTeamId: _awayTeamId,
  homeTeamAbbrev,
  awayTeamAbbrev
}: PenaltySummaryProps) {
  // Placeholder: penalty data not yet available in pipeline
  // When available, fetch from play-by-play data
  const penalties: Penalty[] = [];

  // Don't render if no penalties
  if (penalties.length === 0) {
    return null;
  }

  const getPeriodName = (period: number): string => {
    if (period === 1) return '1st Period';
    if (period === 2) return '2nd Period';
    if (period === 3) return '3rd Period';
    if (period === 4) return 'Overtime';
    return `Period ${period}`;
  };

  const getTeamAbbrev = (teamId: number): string => {
    return teamId === homeTeamId ? homeTeamAbbrev : awayTeamAbbrev;
  };

  // Group by period
  const penaltiesByPeriod = penalties.reduce((acc, penalty) => {
    if (!acc[penalty.period]) acc[penalty.period] = [];
    acc[penalty.period].push(penalty);
    return acc;
  }, {} as Record<number, Penalty[]>);

  return (
    <ChartPanel
      title="Penalty Summary"
      subtitle="Infractions and penalties assessed"
      expandable={false}
    >
      <div className="penalty-summary">
        {Object.entries(penaltiesByPeriod).map(([period, periodPenalties]) => (
          <div key={period} className="penalty-summary__period">
            <h3 className="penalty-summary__period-title">{getPeriodName(Number(period))}</h3>

            <div className="penalty-summary__penalties">
              {periodPenalties.map((penalty, idx) => {
                const teamAbbrev = getTeamAbbrev(penalty.teamId);
                const teamColor = getTeamColorAccent(teamAbbrev);

                return (
                  <div
                    key={idx}
                    className="penalty-item"
                    style={{ borderLeftColor: teamColor }}
                  >
                    <div className="penalty-item__header">
                      <div className="penalty-item__team">
                        <img
                          src={getTeamLogoUrl(teamAbbrev)}
                          alt={teamAbbrev}
                          className="penalty-item__logo"
                        />
                      </div>
                      <div className="penalty-item__time mono">{penalty.time}</div>
                    </div>

                    <div className="penalty-item__details">
                      <div className="penalty-item__player">{penalty.playerName}</div>
                      <div className="penalty-item__infraction">
                        {penalty.infraction} - {penalty.duration} minutes
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </ChartPanel>
  );
}
