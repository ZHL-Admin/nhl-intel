import { useState, useEffect } from 'react';
import ChartPanel from '../common/ChartPanel';
import SkeletonLoader from '../common/SkeletonLoader';
import { getTeamTrends } from '../../api/teams';
import { TeamTrends } from '../../api/types';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import './RollingContextPanel.css';

interface RollingContextPanelProps {
  gameId: number;
  homeTeamId: number;
  awayTeamId: number;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeTeamColor: string;
  awayTeamColor: string;
  homeGameCF: number | null;
  awayGameCF: number | null;
}

function renderSparkline(data: number[], color: string): JSX.Element | null {
  if (data.length === 0) return null; // V9: no placeholder dashes — a no-data cell doesn't render

  const width = 60;
  const height = 24;
  const padding = 2;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data
    .map((val, idx) => {
      const x = (idx / (data.length - 1)) * width;
      const y = height - padding - ((val - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(' ');

  // Highlight the last point (current game) if it exists
  const lastPoint = data.length > 0 ? {
    x: width,
    y: height - padding - ((data[data.length - 1] - min) / range) * (height - padding * 2)
  } : null;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="sparkline">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
      />
      {lastPoint && (
        <circle
          cx={lastPoint.x}
          cy={lastPoint.y}
          r="3"
          fill={color}
          stroke="var(--color-bg-surface)"
          strokeWidth="1.5"
        />
      )}
    </svg>
  );
}

function TeamRollingContext({
  teamId,
  teamAbbrev,
  teamColor,
  gameCF
}: {
  teamId: number;
  teamAbbrev: string;
  teamColor: string;
  gameCF: number | null;
}) {
  const [trends, setTrends] = useState<TeamTrends | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTrends = async () => {
      setLoading(true);
      try {
        const data = await getTeamTrends(teamId);
        setTrends(data);
      } catch (err) {
        console.error('Error fetching team trends:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchTrends();
  }, [teamId]);

  if (loading || !trends) {
    return (
      <div className="rolling-context__row">
        <div className="rolling-context__team">{teamAbbrev}</div>
        <div className="rolling-context__loading"><SkeletonLoader height={24} /></div>
      </div>
    );
  }

  const last10CF = trends.cf_pct_10gp.map(d => d.value);
  const rolling5CF = trends.cf_pct_5gp.length > 0
    ? trends.cf_pct_5gp[trends.cf_pct_5gp.length - 1].value
    : null;

  // V9: no claim without numbers — if a team has no rolling data, its row doesn't render (no dashes).
  if (last10CF.length === 0 && rolling5CF === null) return null;

  // Determine if this game was above or below rolling average
  let trend: 'above' | 'below' | 'consistent' = 'consistent';
  if (gameCF !== null && rolling5CF !== null) {
    const diff = gameCF - rolling5CF;
    if (Math.abs(diff) > 0.05) {
      trend = diff > 0 ? 'above' : 'below';
    }
  }

  const TrendIcon = trend === 'above' ? TrendingUp : trend === 'below' ? TrendingDown : Minus;
  const trendColor = trend === 'above' ? 'var(--color-success)' : trend === 'below' ? 'var(--color-danger)' : 'var(--color-text-muted)';

  return (
    <div className="rolling-context__row">
      <div className="rolling-context__team">
        <span className="rolling-context__team-name">{teamAbbrev}</span>
      </div>
      <div className="rolling-context__sparkline">
        {renderSparkline(last10CF, teamColor)}
      </div>
      <div className="rolling-context__value mono" title={rolling5CF === null ? 'Rolling 5-game CF% not yet available' : undefined}>
        {rolling5CF !== null ? (rolling5CF * 100).toFixed(1) + '%' : '—'}
      </div>
      <div className="rolling-context__trend" style={{ color: trendColor }}>
        <TrendIcon size={16} />
      </div>
    </div>
  );
}

function generateTitle(
  homeGameCF: number | null,
  awayGameCF: number | null,
  homeTeamAbbrev: string
): string {
  // V9: state the subject, not an unverified claim. The rows carry the actual numbers.
  void homeGameCF; void awayGameCF; void homeTeamAbbrev;
  return 'Rolling form · last 10 games, 5v5 CF%';
}

export default function RollingContextPanel({
  homeTeamId,
  awayTeamId,
  homeTeamAbbrev,
  awayTeamAbbrev,
  homeTeamColor,
  awayTeamColor,
  homeGameCF,
  awayGameCF
}: RollingContextPanelProps) {
  const title = generateTitle(homeGameCF, awayGameCF, homeTeamAbbrev);

  return (
    <ChartPanel
      title={title}
      subtitle="Performance in context of recent 10-game trend"
      expandable={false}
    >
      <div className="rolling-context">
        <div className="rolling-context__header">
          <div className="rolling-context__header-item">Team</div>
          <div className="rolling-context__header-item">Last 10 Games</div>
          <div className="rolling-context__header-item">5-Game CF%</div>
          <div className="rolling-context__header-item">Trend</div>
        </div>

        <TeamRollingContext
          teamId={awayTeamId}
          teamAbbrev={awayTeamAbbrev}
          teamColor={awayTeamColor}
          gameCF={awayGameCF}
        />

        <TeamRollingContext
          teamId={homeTeamId}
          teamAbbrev={homeTeamAbbrev}
          teamColor={homeTeamColor}
          gameCF={homeGameCF}
        />
      </div>
    </ChartPanel>
  );
}
