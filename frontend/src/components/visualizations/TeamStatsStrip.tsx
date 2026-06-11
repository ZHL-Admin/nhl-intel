import ChartPanel from '../common/ChartPanel';
import './TeamStatsStrip.css';

interface TeamStatsStripProps {
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeTeamColor: string;
  awayTeamColor: string;
  homeStats: {
    shots_on_goal: number | null | undefined;
    // Add more stats as they become available
  };
  awayStats: {
    shots_on_goal: number | null | undefined;
    // Add more stats as they become available
  };
}

export default function TeamStatsStrip({
  homeTeamAbbrev: _homeTeamAbbrev,
  awayTeamAbbrev: _awayTeamAbbrev,
  homeTeamColor: _homeTeamColor,
  awayTeamColor: _awayTeamColor,
  homeStats,
  awayStats
}: TeamStatsStripProps) {
  const formatValue = (value: number | null | undefined): string => {
    return value !== null && value !== undefined ? value.toString() : '-';
  };

  return (
    <ChartPanel
      title="Team Statistics"
      subtitle="Key statistical comparisons"
      expandable={false}
    >
      <div className="team-stats-strip">
        {/* Shots on Goal */}
        <div className="team-stats-strip__row">
          <div className="team-stats-strip__value mono">{formatValue(awayStats.shots_on_goal)}</div>
          <div className="team-stats-strip__label">Shots on Goal</div>
          <div className="team-stats-strip__value mono">{formatValue(homeStats.shots_on_goal)}</div>
        </div>

        {/* More stats can be added here as data becomes available */}
        {/* Faceoff Win %, Power Plays, Hits, Penalty Minutes, Blocked Shots */}
      </div>
    </ChartPanel>
  );
}
