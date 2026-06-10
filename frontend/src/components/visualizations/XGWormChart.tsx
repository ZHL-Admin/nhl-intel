import { useState, useEffect } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ReferenceLine,
  ReferenceDot
} from 'recharts';
import ChartPanel, { useChartPanelHeight } from '../common/ChartPanel';
import Tabs from '../common/Tabs';
import { getGameXGWorm } from '../../api/games';
import { XGWormPoint } from '../../api/types';
import './XGWormChart.css';

interface XGWormChartProps {
  gameId: number;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeTeamColor: string;
  awayTeamColor: string;
}

function generateTitle(
  data: XGWormPoint[],
  homeTeamAbbrev: string,
  awayTeamAbbrev: string
): string {
  if (data.length === 0) return 'Expected goals flow through the game';

  const maxAbsValue = Math.max(...data.map(d => Math.abs(d.cumulative_xg_diff)));

  if (maxAbsValue < 0.5) {
    return `${homeTeamAbbrev} and ${awayTeamAbbrev} were evenly matched in expected goals throughout`;
  }

  let maxDiff = 0;
  let maxDiffTime = 0;
  let leadingTeam = '';

  for (const point of data) {
    if (Math.abs(point.cumulative_xg_diff) > Math.abs(maxDiff)) {
      maxDiff = point.cumulative_xg_diff;
      maxDiffTime = point.game_time_seconds;
      leadingTeam = maxDiff > 0 ? homeTeamAbbrev : awayTeamAbbrev;
    }
  }

  const maxDiffMinutes = Math.floor(maxDiffTime / 60);
  const absMaxDiff = Math.abs(maxDiff).toFixed(1);

  const otherTeam = leadingTeam === homeTeamAbbrev ? awayTeamAbbrev : homeTeamAbbrev;

  return `${leadingTeam} built a ${absMaxDiff} xG lead through ${maxDiffMinutes} minutes before ${otherTeam}'s push`;
}

function XGWormChartInner({
  gameId,
  homeTeamColor,
  awayTeamColor
}: XGWormChartProps) {
  const [data, setData] = useState<XGWormPoint[]>([]);
  const [situation] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const height = useChartPanelHeight();

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const wormData = await getGameXGWorm(gameId, situation);
        setData(wormData);
      } catch (err) {
        console.error('Error fetching xG worm data:', err);
        setError('Failed to load xG data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [gameId, situation]);

  if (loading) {
    return (
      <div className="xg-worm-loading">
        <div className="skeleton-loader" style={{ width: '100%', height: `${height}px` }} />
      </div>
    );
  }

  if (error || data.length === 0) {
    return (
      <div className="xg-worm-error">
        <p>{error || 'No xG data available'}</p>
      </div>
    );
  }

  const chartData = data.map(point => ({
    ...point,
    gameTimeMinutes: point.game_time_seconds / 60,
    positiveValue: point.cumulative_xg_diff > 0 ? point.cumulative_xg_diff : null,
    negativeValue: point.cumulative_xg_diff < 0 ? point.cumulative_xg_diff : null,
  }));

  const goals = data.filter(point => point.event_type === 'goal');

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart
        data={chartData}
        margin={{ top: 10, right: 30, left: 20, bottom: 20 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-subtle)" vertical={false} />

        <XAxis
          dataKey="gameTimeMinutes"
          label={{ value: 'Game Time (minutes)', position: 'insideBottom', offset: -10 }}
          stroke="var(--color-text-secondary)"
          tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
        />

        <YAxis
          label={{ value: 'xG Difference', angle: -90, position: 'insideLeft' }}
          stroke="var(--color-text-secondary)"
          tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
        />

        <ReferenceLine
          y={0}
          stroke="var(--color-data-neutral)"
          strokeWidth={1}
          label={{ value: 'Even', fill: 'var(--color-text-muted)', fontSize: 11 }}
        />

        {/* Positive area (home team leading) */}
        <Area
          type="monotone"
          dataKey="positiveValue"
          fill={homeTeamColor}
          fillOpacity={0.15}
          stroke="none"
          connectNulls
        />

        {/* Negative area (away team leading) */}
        <Area
          type="monotone"
          dataKey="negativeValue"
          fill={awayTeamColor}
          fillOpacity={0.15}
          stroke="none"
          connectNulls
        />

        {/* Main line - colored by current value */}
        <Line
          type="monotone"
          dataKey="cumulative_xg_diff"
          stroke="var(--color-text-primary)"
          strokeWidth={2}
          dot={false}
          connectNulls
        />

        {/* Goal markers */}
        {goals.map((goal, index) => (
          <ReferenceDot
            key={index}
            x={goal.game_time_seconds / 60}
            y={goal.cumulative_xg_diff}
            r={5}
            fill="var(--color-bg-surface)"
            stroke={goal.team_id === parseInt(homeTeamColor) ? homeTeamColor : awayTeamColor}
            strokeWidth={2}
            label={{
              value: goal.label || '',
              position: goal.cumulative_xg_diff > 0 ? 'top' : 'bottom',
              fill: 'var(--color-text-primary)',
              fontSize: 10
            }}
          />
        ))}

        <RechartsTooltip
          contentStyle={{
            backgroundColor: 'var(--color-bg-overlay)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-md)',
            fontSize: '13px',
            padding: '8px 12px'
          }}
          labelStyle={{ color: 'var(--color-text-secondary)', marginBottom: '4px' }}
          formatter={(value) => {
            const formatted = typeof value === 'number' ? value.toFixed(2) : String(value);
            return [formatted, 'xG Diff'];
          }}
          labelFormatter={(value) => `${Math.floor(value as number)}:${String(Math.round(((value as number) % 1) * 60)).padStart(2, '0')}`}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default function XGWormChart(props: XGWormChartProps) {
  const [data, setData] = useState<XGWormPoint[]>([]);
  const [situation, setSituation] = useState('all');

  useEffect(() => {
    const fetchTitleData = async () => {
      try {
        const wormData = await getGameXGWorm(props.gameId, situation);
        setData(wormData);
      } catch (err) {
        console.error('Error fetching xG worm data for title:', err);
      }
    };

    fetchTitleData();
  }, [props.gameId, situation]);

  const title = generateTitle(data, props.homeTeamAbbrev, props.awayTeamAbbrev);

  return (
    <ChartPanel
      sectionNumber="01"
      title={title}
      subtitle="Cumulative expected goals differential over game time"
      footer={
        <Tabs
          options={[
            { value: 'all', label: 'All' },
            { value: '5v5', label: '5v5' },
            { value: 'ev', label: 'EV' },
          ]}
          value={situation}
          onChange={setSituation}
        />
      }
    >
      <XGWormChartInner {...props} />
    </ChartPanel>
  );
}
