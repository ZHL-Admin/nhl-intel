import { useState, useEffect, useRef, useMemo, type MouseEvent as ReactMouseEvent } from 'react';
import ChartPanel from '../common/ChartPanel';
import Tabs from '../common/Tabs';
import GoalTooltip from '../common/GoalTooltip';
import { getGameXGWorm, getGameGoals } from '../../api/games';
import { XGWormPoint, GoalDetail } from '../../api/types';
import './XGWormChart.css';

const goalKey = (timeSeconds: number, teamId: number | null | undefined) => `${timeSeconds}-${teamId}`;

interface XGWormChartProps {
  gameId: number;
  homeTeamId: number;
  awayTeamId: number;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeTeamColor: string;
  awayTeamColor: string;
}

const PAD = { top: 24, right: 24, bottom: 28, left: 46 };

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

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function WormSvg({
  data,
  goalMap,
  homeTeamId,
  homeTeamColor,
  awayTeamColor,
  homeTeamAbbrev,
  awayTeamAbbrev
}: {
  data: XGWormPoint[];
  goalMap: Map<string, GoalDetail>;
  homeTeamId: number;
  homeTeamColor: string;
  awayTeamColor: string;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [dims, setDims] = useState({ w: 0, h: 0 });
  const [hover, setHover] = useState<XGWormPoint | null>(null);
  const [activeGoal, setActiveGoal] = useState<XGWormPoint | null>(null);

  // Draw to fit the panel's (fixed-height) content box exactly: the viewBox matches the
  // box's pixel size, so scaling is uniform (round dots) and nothing is clipped.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setDims({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Clear any open goal/line tooltip when the underlying data changes (e.g. All/5v5 toggle)
  useEffect(() => {
    setActiveGoal(null);
    setHover(null);
  }, [data]);

  const { w, h } = dims;
  const ready = w > 0 && h > 0 && data.length > 0;

  const plotW = w - PAD.left - PAD.right;
  const plotH = h - PAD.top - PAD.bottom;
  const zeroY = PAD.top + plotH / 2;

  const maxTime = Math.max(3600, ...data.map(d => d.game_time_seconds));
  const maxAbs = Math.max(0.2, ...data.map(d => Math.abs(d.cumulative_xg_diff)));
  // Symmetric domain keeps "Even" at the vertical center; data fills out toward the edge.
  const range = maxAbs * 1.08;

  const xScale = (t: number) => PAD.left + (t / maxTime) * plotW;
  const yScale = (v: number) => zeroY - (v / range) * (plotH / 2);

  const linePath = data
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(p.game_time_seconds)} ${yScale(p.cumulative_xg_diff)}`)
    .join(' ');

  const buildArea = (clampAbove: boolean) => {
    if (!ready) return '';
    const pts = data
      .map(p => {
        const y = yScale(p.cumulative_xg_diff);
        const cy = clampAbove ? Math.min(y, zeroY) : Math.max(y, zeroY);
        return `L ${xScale(p.game_time_seconds)} ${cy}`;
      })
      .join(' ');
    const x0 = xScale(data[0].game_time_seconds);
    const xN = xScale(data[data.length - 1].game_time_seconds);
    return `M ${x0} ${zeroY} ${pts} L ${xN} ${zeroY} Z`;
  };

  const goals = data.filter(p => p.event_type === 'goal');

  const lastTick = Math.ceil(maxTime / 600) * 10;
  const xTicks: number[] = [];
  for (let m = 0; m <= lastTick; m += 10) xTicks.push(m);

  const step = range <= 1 ? 0.5 : 1;
  const yTicks: number[] = [];
  for (let v = step; v < range; v += step) yTicks.push(v);

  const handleMove = (e: ReactMouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg || !ready) return;
    const rect = svg.getBoundingClientRect();
    const vbX = ((e.clientX - rect.left) / rect.width) * w;
    const t = ((vbX - PAD.left) / plotW) * maxTime;
    let nearest = data[0];
    for (const p of data) {
      if (Math.abs(p.game_time_seconds - t) < Math.abs(nearest.game_time_seconds - t)) nearest = p;
    }
    setHover(nearest);
  };

  return (
    <div className="xg-worm-plot" ref={containerRef}>
      <div className="xg-worm-legend">
        <span className="xg-worm-legend__item">
          <span className="xg-worm-legend__swatch" style={{ background: homeTeamColor }} />{homeTeamAbbrev}
        </span>
        <span className="xg-worm-legend__item">
          <span className="xg-worm-legend__swatch" style={{ background: awayTeamColor }} />{awayTeamAbbrev}
        </span>
      </div>

      {ready && (
        <svg
          ref={svgRef}
          className="xg-worm-svg"
          viewBox={`0 0 ${w} ${h}`}
          width="100%"
          height="100%"
          onMouseMove={handleMove}
          onMouseLeave={() => setHover(null)}
        >
          {xTicks.map(m => {
            const x = xScale(m * 60);
            if (x > w - PAD.right + 1) return null;
            return (
              <g key={`x${m}`}>
                <line x1={x} y1={PAD.top} x2={x} y2={PAD.top + plotH} stroke="var(--color-border-subtle)" strokeWidth={1} />
                <text x={x} y={h - 10} textAnchor="middle" fontSize={12} fill="var(--color-text-muted)">{m}&apos;</text>
              </g>
            );
          })}

          {yTicks.map(v => (
            <g key={`y${v}`}>
              <line x1={PAD.left} y1={yScale(v)} x2={w - PAD.right} y2={yScale(v)} stroke="var(--color-border-subtle)" strokeDasharray="3 3" strokeWidth={1} />
              <line x1={PAD.left} y1={yScale(-v)} x2={w - PAD.right} y2={yScale(-v)} stroke="var(--color-border-subtle)" strokeDasharray="3 3" strokeWidth={1} />
              <text x={PAD.left - 8} y={yScale(v) + 4} textAnchor="end" fontSize={11} fill="var(--color-text-muted)">+{v}</text>
              <text x={PAD.left - 8} y={yScale(-v) + 4} textAnchor="end" fontSize={11} fill="var(--color-text-muted)">−{v}</text>
            </g>
          ))}

          <path d={buildArea(true)} fill={homeTeamColor} fillOpacity={0.15} />
          <path d={buildArea(false)} fill={awayTeamColor} fillOpacity={0.15} />

          <line x1={PAD.left} y1={zeroY} x2={w - PAD.right} y2={zeroY} stroke="var(--color-border)" strokeWidth={1} />
          <text x={w - PAD.right} y={zeroY - 6} textAnchor="end" fontSize={11} fill="var(--color-text-muted)">Even</text>

          <path d={linePath} fill="none" stroke="var(--color-text-muted)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

          {goals.map((g, i) => {
            const cx = xScale(g.game_time_seconds);
            const cy = yScale(g.cumulative_xg_diff);
            const color = g.team_id === homeTeamId ? homeTeamColor : awayTeamColor;
            const above = g.cumulative_xg_diff >= 0;
            const isActive = activeGoal === g;
            return (
              <g
                key={`goal${i}`}
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setActiveGoal(g)}
                onMouseLeave={() => setActiveGoal(null)}
                onClick={() => setActiveGoal(isActive ? null : g)}
              >
                {/* Enlarged invisible hit area for easy hover / tap */}
                <circle cx={cx} cy={cy} r={14} fill="transparent" />
                <circle cx={cx} cy={cy} r={isActive ? 7 : 5} fill={color} stroke="var(--color-bg-surface)" strokeWidth={1.5} />
                {g.label && (
                  <text x={cx} y={above ? cy - 10 : cy + 18} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--color-text-primary)">
                    {g.label}
                  </text>
                )}
              </g>
            );
          })}

          {hover && !activeGoal && (
            <g pointerEvents="none">
              <line x1={xScale(hover.game_time_seconds)} y1={PAD.top} x2={xScale(hover.game_time_seconds)} y2={PAD.top + plotH} stroke="var(--color-border-strong)" strokeWidth={1} />
              <circle cx={xScale(hover.game_time_seconds)} cy={yScale(hover.cumulative_xg_diff)} r={4} fill="var(--color-text-primary)" />
            </g>
          )}
        </svg>
      )}

      {hover && !activeGoal && ready && (
        <div
          className="xg-worm-tooltip"
          style={{
            left: `${(xScale(hover.game_time_seconds) / w) * 100}%`,
            top: `${(yScale(hover.cumulative_xg_diff) / h) * 100}%`
          }}
        >
          <div className="xg-worm-tooltip__time">{formatClock(hover.game_time_seconds)}</div>
          <div className="xg-worm-tooltip__value">
            {hover.cumulative_xg_diff >= 0
              ? `${homeTeamAbbrev} +${hover.cumulative_xg_diff.toFixed(2)}`
              : `${awayTeamAbbrev} +${Math.abs(hover.cumulative_xg_diff).toFixed(2)}`} xG
          </div>
        </div>
      )}

      {activeGoal && ready && (() => {
        const detail = goalMap.get(goalKey(activeGoal.game_time_seconds, activeGoal.team_id));
        const color = activeGoal.team_id === homeTeamId ? homeTeamColor : awayTeamColor;
        const dotX = xScale(activeGoal.game_time_seconds);
        const dotY = yScale(activeGoal.cumulative_xg_diff);
        // Keep the tooltip inside the chart: flip horizontally near the edges and
        // drop below the dot when it's near the top.
        const edge = 150;
        const tx = dotX < edge ? '0%' : dotX > w - edge ? '-100%' : '-50%';
        const ty = dotY < h * 0.35 ? '14px' : 'calc(-100% - 14px)';
        return (
          <GoalTooltip
            detail={detail}
            label={activeGoal.label}
            accentColor={color}
            left={`${(dotX / w) * 100}%`}
            top={`${(dotY / h) * 100}%`}
            transform={`translate(${tx}, ${ty})`}
          />
        );
      })()}
    </div>
  );
}

export default function XGWormChart(props: XGWormChartProps) {
  const [data, setData] = useState<XGWormPoint[]>([]);
  const [goals, setGoals] = useState<GoalDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [situation, setSituation] = useState('all');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getGameXGWorm(props.gameId, situation)
      .then(worm => {
        if (active) setData(worm);
      })
      .catch(() => {
        if (active) setError('Failed to load xG data');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [props.gameId, situation]);

  // Goal details are situation-independent; fetch once per game.
  useEffect(() => {
    let active = true;
    getGameGoals(props.gameId)
      .then(g => {
        if (active) setGoals(g);
      })
      .catch(() => {
        if (active) setGoals([]);
      });
    return () => {
      active = false;
    };
  }, [props.gameId]);

  const goalMap = useMemo(() => {
    const m = new Map<string, GoalDetail>();
    for (const g of goals) m.set(goalKey(g.game_time_seconds, g.team_id), g);
    return m;
  }, [goals]);

  const title = generateTitle(data, props.homeTeamAbbrev, props.awayTeamAbbrev);

  return (
    <ChartPanel
      title={title}
      subtitle={
        situation === '5v5'
          ? 'Cumulative even-strength (5v5) expected goals differential over game time'
          : 'Cumulative expected goals differential over game time, all situations'
      }
      expandable={false}
      footer={
        <Tabs
          options={[
            { value: 'all', label: 'All' },
            { value: '5v5', label: '5v5' }
          ]}
          value={situation}
          onChange={setSituation}
        />
      }
    >
      {loading ? (
        <div className="xg-worm-loading">
          <div className="skeleton-loader" style={{ width: '100%', height: '100%' }} />
        </div>
      ) : error || data.length === 0 ? (
        <div className="xg-worm-error">
          <p>{error || 'No xG data available'}</p>
        </div>
      ) : (
        <WormSvg
          data={data}
          goalMap={goalMap}
          homeTeamId={props.homeTeamId}
          homeTeamColor={props.homeTeamColor}
          awayTeamColor={props.awayTeamColor}
          homeTeamAbbrev={props.homeTeamAbbrev}
          awayTeamAbbrev={props.awayTeamAbbrev}
        />
      )}
    </ChartPanel>
  );
}
