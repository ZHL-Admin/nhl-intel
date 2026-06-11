import { useState, useEffect } from 'react';
import ChartPanel from '../common/ChartPanel';
import { getGameShots } from '../../api/games';
import { ShotAttempt } from '../../api/types';
import { getTeamLogoUrl, getTeamColorAccent } from '../../utils/teams';
import './ScoringSummary.css';

interface ScoringSummaryProps {
  gameId: number;
  homeTeamId: number;
  awayTeamId: number;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
}

interface Goal extends ShotAttempt {
  outcome: 'goal';
  period: number;
  time_in_period: string;
  scorer_name: string;
}

export default function ScoringSummary({
  gameId,
  homeTeamId,
  awayTeamId: _awayTeamId,
  homeTeamAbbrev,
  awayTeamAbbrev
}: ScoringSummaryProps) {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchGoals = async () => {
      try {
        const data = await getGameShots(gameId, 'all');
        const allShots = [...data.home_shots, ...data.away_shots];
        const goalShots = allShots.filter(
          (shot): shot is Goal =>
            shot.outcome === 'goal' &&
            shot.period !== undefined &&
            shot.time_in_period !== undefined &&
            shot.scorer_name !== undefined
        );

        // Sort by period and time
        goalShots.sort((a, b) => {
          if (a.period !== b.period) return a.period - b.period;
          // Time format is mm:ss, convert to seconds for sorting
          const [aMin, aSec] = a.time_in_period.split(':').map(Number);
          const [bMin, bSec] = b.time_in_period.split(':').map(Number);
          return (aMin * 60 + aSec) - (bMin * 60 + bSec);
        });

        setGoals(goalShots);
      } catch (err) {
        console.error('Error fetching goals:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchGoals();
  }, [gameId]);

  if (loading || goals.length === 0) {
    return null;
  }

  // Group goals by period
  const goalsByPeriod = goals.reduce((acc, goal) => {
    const period = goal.period;
    if (!acc[period]) acc[period] = [];
    acc[period].push(goal);
    return acc;
  }, {} as Record<number, Goal[]>);

  const getPeriodName = (period: number): string => {
    if (period === 1) return '1st Period';
    if (period === 2) return '2nd Period';
    if (period === 3) return '3rd Period';
    if (period === 4) return 'Overtime';
    return `Period ${period}`;
  };

  const getSituationTag = (situation: string): string | null => {
    // Situation codes: 5v5=all strength, 5v4=PP, 4v5=PK, etc.
    if (situation.includes('5v4') || situation.includes('5v3') || situation.includes('4v3')) {
      return 'PP';
    }
    if (situation.includes('4v5') || situation.includes('3v5') || situation.includes('3v4')) {
      return 'SH';
    }
    // EN (empty net) would require additional data
    return null;
  };

  const getTeamAbbrev = (teamId: number): string => {
    return teamId === homeTeamId ? homeTeamAbbrev : awayTeamAbbrev;
  };

  return (
    <ChartPanel
      title="Scoring Summary"
      subtitle="Chronological list of all goals scored"
      expandable={false}
    >
      <div className="scoring-summary">
        {Object.entries(goalsByPeriod).map(([period, periodGoals]) => (
          <div key={period} className="scoring-summary__period">
            <h3 className="scoring-summary__period-title">{getPeriodName(Number(period))}</h3>

            <div className="scoring-summary__goals">
              {periodGoals.map((goal, idx) => {
                const teamAbbrev = getTeamAbbrev(goal.team_id);
                const teamColor = getTeamColorAccent(teamAbbrev);
                const situationTag = getSituationTag(goal.situation);

                return (
                  <div
                    key={idx}
                    className="goal-item"
                    style={{ borderLeftColor: teamColor }}
                  >
                    <div className="goal-item__header">
                      <div className="goal-item__team">
                        <img
                          src={getTeamLogoUrl(teamAbbrev)}
                          alt={teamAbbrev}
                          className="goal-item__logo"
                        />
                      </div>
                      <div className="goal-item__time mono">{goal.time_in_period}</div>
                    </div>

                    <div className="goal-item__scorer">
                      <div className="goal-item__scorer-name">
                        {goal.scorer_name}
                        {situationTag && (
                          <span className="goal-item__tag">({situationTag})</span>
                        )}
                      </div>

                      {(goal.assist1_name || goal.assist2_name) && (
                        <div className="goal-item__assists">
                          Assisted by{' '}
                          {[goal.assist1_name, goal.assist2_name]
                            .filter(Boolean)
                            .join(' and ')}
                        </div>
                      )}

                      {!goal.assist1_name && !goal.assist2_name && (
                        <div className="goal-item__assists">Unassisted</div>
                      )}
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
