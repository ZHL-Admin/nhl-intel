import ChartPanel from '../common/ChartPanel';
import './BoxscoreSummary.css';

interface BoxscoreSummaryProps {
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeTeamColor: string;
  awayTeamColor: string;
  homeStats: {
    score: number | null | undefined;
    shots_on_goal: number | null | undefined;
    shot_attempts: number | null | undefined;
  };
  awayStats: {
    score: number | null | undefined;
    shots_on_goal: number | null | undefined;
    shot_attempts: number | null | undefined;
  };
}

function generateTitle(
  homeStats: BoxscoreSummaryProps['homeStats'],
  awayStats: BoxscoreSummaryProps['awayStats'],
  homeTeamAbbrev: string,
  awayTeamAbbrev: string
): string {
  const homeSOG = homeStats.shots_on_goal ?? 0;
  const awaySOG = awayStats.shots_on_goal ?? 0;
  const homeScore = homeStats.score ?? 0;
  const awayScore = awayStats.score ?? 0;

  if (homeSOG === awaySOG && homeScore === awayScore) {
    return `${homeTeamAbbrev} and ${awayTeamAbbrev} matched each other in shots and goals`;
  }

  // Find the more interesting stat to highlight
  const shotDiff = Math.abs(homeSOG - awaySOG);
  const scoreDiff = Math.abs(homeScore - awayScore);

  if (scoreDiff >= 2) {
    const winner = homeScore > awayScore ? homeTeamAbbrev : awayTeamAbbrev;
    const winnerScore = Math.max(homeScore, awayScore);
    const loserScore = Math.min(homeScore, awayScore);
    return `${winner} wins ${winnerScore}-${loserScore}`;
  }

  if (shotDiff >= 5) {
    const leader = homeSOG > awaySOG ? homeTeamAbbrev : awayTeamAbbrev;
    const leaderSOG = Math.max(homeSOG, awaySOG);
    const otherSOG = Math.min(homeSOG, awaySOG);
    return `${leader} outshot opponent ${leaderSOG}-${otherSOG}`;
  }

  return `Final: ${awayTeamAbbrev} ${awayScore}, ${homeTeamAbbrev} ${homeScore}`;
}

export default function BoxscoreSummary(props: BoxscoreSummaryProps) {
  const { homeTeamAbbrev, awayTeamAbbrev, homeTeamColor, awayTeamColor, homeStats, awayStats } = props;

  const title = generateTitle(homeStats, awayStats, homeTeamAbbrev, awayTeamAbbrev);

  const formatValue = (value: number | null | undefined): string => {
    return value !== null && value !== undefined ? value.toString() : '-';
  };

  return (
    <ChartPanel
      title={title}
      subtitle="Key game statistics"
      expandable={false}
    >
      <div className="boxscore-summary">
        <div className="boxscore-summary__tables">
          {/* Away Team Table */}
          <div className="boxscore-summary__table" style={{ borderTop: `4px solid color-mix(in srgb, ${awayTeamColor} 50%, var(--color-bg-base))` }}>
            <div className="boxscore-summary__stats">
              <div className="boxscore-summary__stat-row">
                <span className="boxscore-summary__stat-label">Goals</span>
                <span className="boxscore-summary__stat-value">{formatValue(awayStats.score)}</span>
              </div>
              <div className="boxscore-summary__stat-row">
                <span className="boxscore-summary__stat-label">Shots on Goal</span>
                <span className="boxscore-summary__stat-value">{formatValue(awayStats.shots_on_goal)}</span>
              </div>
              <div className="boxscore-summary__stat-row">
                <span className="boxscore-summary__stat-label">Shot Attempts</span>
                <span className="boxscore-summary__stat-value">{formatValue(awayStats.shot_attempts)}</span>
              </div>
            </div>
          </div>

          {/* Home Team Table */}
          <div className="boxscore-summary__table" style={{ borderTop: `4px solid color-mix(in srgb, ${homeTeamColor} 50%, var(--color-bg-base))` }}>
            <div className="boxscore-summary__stats">
              <div className="boxscore-summary__stat-row">
                <span className="boxscore-summary__stat-label">Goals</span>
                <span className="boxscore-summary__stat-value">{formatValue(homeStats.score)}</span>
              </div>
              <div className="boxscore-summary__stat-row">
                <span className="boxscore-summary__stat-label">Shots on Goal</span>
                <span className="boxscore-summary__stat-value">{formatValue(homeStats.shots_on_goal)}</span>
              </div>
              <div className="boxscore-summary__stat-row">
                <span className="boxscore-summary__stat-label">Shot Attempts</span>
                <span className="boxscore-summary__stat-value">{formatValue(homeStats.shot_attempts)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </ChartPanel>
  );
}
