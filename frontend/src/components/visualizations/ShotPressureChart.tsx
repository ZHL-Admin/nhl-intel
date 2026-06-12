import { useState, useEffect, useRef, useMemo, type MouseEvent as ReactMouseEvent } from 'react';
import ChartPanel from '../common/ChartPanel';
import GoalTooltip from '../common/GoalTooltip';
import { getGamePressure, getGameGoals } from '../../api/games';
import { PressurePoint, GoalDetail } from '../../api/types';
import './ShotPressureChart.css';

const goalKey = (timeSeconds: number, teamId: number) => `${timeSeconds}-${teamId}`;

interface ShotPressureChartProps {
  gameId: number;
  homeTeamId: number;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeTeamColor: string;
  awayTeamColor: string;
}

const PAD = { top: 22, right: 20, bottom: 28, left: 36 };

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function generateTitle(data: PressurePoint[], home: string, away: string): string {
  if (data.length === 0) return 'Unblocked shot rate over game time';
  const hAvg = data.reduce((a, p) => a + p.home_rate, 0) / data.length;
  const aAvg = data.reduce((a, p) => a + p.away_rate, 0) / data.length;
  if (Math.abs(hAvg - aAvg) < 3) return `${home} and ${away} traded shot pressure evenly`;
  return `${hAvg > aAvg ? home : away} generated more sustained shot pressure`;
}

function PressureSvg({
  data,
  goals,
  homeTeamId,
  homeTeamColor,
  awayTeamColor,
  homeTeamAbbrev,
  awayTeamAbbrev
}: {
  data: PressurePoint[];
  goals: GoalDetail[];
  homeTeamId: number;
  homeTeamColor: string;
  awayTeamColor: string;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [dims, setDims] = useState({ w: 0, h: 0 });
  const [hover, setHover] = useState<PressurePoint | null>(null);
  const [activeGoal, setActiveGoal] = useState<GoalDetail | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setDims({ w: el.clientWidth, h: el.clientHeight });
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => { setHover(null); setActiveGoal(null); }, [data]);

  // Running-score label per goal (e.g. "CAR 3-1"), matching the xG worm's format.
  const labelMap = useMemo(() => {
    const m = new Map<string, string>();
    let hs = 0;
    let as = 0;
    for (const g of [...goals].sort((a, b) => a.game_time_seconds - b.game_time_seconds)) {
      if (g.team_id === homeTeamId) hs++; else as++;
      m.set(goalKey(g.game_time_seconds, g.team_id), `${g.team_abbrev} ${hs}-${as}`);
    }
    return m;
  }, [goals, homeTeamId]);

  const { w, h } = dims;
  const ready = w > 0 && h > 0 && data.length > 0;

  const plotW = w - PAD.left - PAD.right;
  const plotH = h - PAD.top - PAD.bottom;
  const centerY = PAD.top + plotH / 2;

  const maxTime = Math.max(3600, ...data.map(d => d.game_time_seconds));
  const maxRate = Math.max(60, ...data.map(d => Math.max(d.home_rate, d.away_rate))) * 1.05;

  const xScale = (t: number) => PAD.left + (t / maxTime) * plotW;
  const yUp = (r: number) => centerY - (r / maxRate) * (plotH / 2);
  const yDown = (r: number) => centerY + (r / maxRate) * (plotH / 2);

  const areaPath = (value: (p: PressurePoint) => number, up: boolean) => {
    if (!ready) return '';
    const pts = data
      .map(p => `L ${xScale(p.game_time_seconds)} ${up ? yUp(value(p)) : yDown(value(p))}`)
      .join(' ');
    const x0 = xScale(data[0].game_time_seconds);
    const xN = xScale(data[data.length - 1].game_time_seconds);
    return `M ${x0} ${centerY} ${pts} L ${xN} ${centerY} Z`;
  };

  const lastTick = Math.ceil(maxTime / 600) * 10;
  const xTicks: number[] = [];
  for (let m = 0; m <= lastTick; m += 10) xTicks.push(m);

  const yRefs = [55, 110].filter(v => v < maxRate);

  // Rate of the given team at the sample nearest to time t (to place goal dots on the curve)
  const rateAt = (t: number, isHome: boolean) => {
    if (!data.length) return 0;
    let nearest = data[0];
    for (const p of data) {
      if (Math.abs(p.game_time_seconds - t) < Math.abs(nearest.game_time_seconds - t)) nearest = p;
    }
    return isHome ? nearest.home_rate : nearest.away_rate;
  };

  const goalY = (g: GoalDetail) => {
    const isHome = g.team_id === homeTeamId;
    return isHome ? yUp(rateAt(g.game_time_seconds, true)) : yDown(rateAt(g.game_time_seconds, false));
  };

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
    <div className="pressure-plot" ref={containerRef}>
      <div className="pressure-legend">
        <span className="pressure-legend__item">
          <span className="pressure-legend__swatch" style={{ background: homeTeamColor }} />{homeTeamAbbrev} ▲
        </span>
        <span className="pressure-legend__item">
          <span className="pressure-legend__swatch" style={{ background: awayTeamColor }} />{awayTeamAbbrev} ▼
        </span>
      </div>

      {ready && (
        <svg
          ref={svgRef}
          className="pressure-svg"
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

          {yRefs.map(v => (
            <g key={`y${v}`}>
              <line x1={PAD.left} y1={yUp(v)} x2={w - PAD.right} y2={yUp(v)} stroke="var(--color-border-subtle)" strokeDasharray="3 3" strokeWidth={1} />
              <line x1={PAD.left} y1={yDown(v)} x2={w - PAD.right} y2={yDown(v)} stroke="var(--color-border-subtle)" strokeDasharray="3 3" strokeWidth={1} />
              <text x={PAD.left - 4} y={yUp(v) + 3} textAnchor="end" fontSize={10} fill="var(--color-text-muted)">{v}</text>
              <text x={PAD.left - 4} y={yDown(v) + 3} textAnchor="end" fontSize={10} fill="var(--color-text-muted)">{v}</text>
            </g>
          ))}

          {/* Pressure areas: home above the axis, away below */}
          <path d={areaPath(p => p.home_rate, true)} fill={homeTeamColor} fillOpacity={0.5} />
          <path d={areaPath(p => p.away_rate, false)} fill={awayTeamColor} fillOpacity={0.5} />

          {/* Center axis */}
          <line x1={PAD.left} y1={centerY} x2={w - PAD.right} y2={centerY} stroke="var(--color-border-strong)" strokeWidth={1} />

          {/* Goal markers — solid team dot on the scoring team's curve + running-score label */}
          {goals.map((g, i) => {
            const x = xScale(g.game_time_seconds);
            const isHome = g.team_id === homeTeamId;
            const cy = goalY(g);
            const color = isHome ? homeTeamColor : awayTeamColor;
            const isActive = activeGoal === g;
            const label = labelMap.get(goalKey(g.game_time_seconds, g.team_id));
            const labelY = isHome ? cy + 16 : cy - 10; // toward the center axis to stay in-bounds
            return (
              <g
                key={`goal${i}`}
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setActiveGoal(g)}
                onMouseLeave={() => setActiveGoal(null)}
                onClick={() => setActiveGoal(isActive ? null : g)}
              >
                <circle cx={x} cy={cy} r={14} fill="transparent" />
                <circle cx={x} cy={cy} r={isActive ? 7 : 5} fill={color} stroke="var(--color-bg-surface)" strokeWidth={1.5} />
                {label && (
                  <text x={x} y={labelY} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--color-text-primary)">
                    {label}
                  </text>
                )}
              </g>
            );
          })}

          {hover && !activeGoal && (
            <line
              x1={xScale(hover.game_time_seconds)} y1={PAD.top}
              x2={xScale(hover.game_time_seconds)} y2={PAD.top + plotH}
              stroke="var(--color-border-strong)" strokeWidth={1} pointerEvents="none"
            />
          )}
        </svg>
      )}

      {hover && !activeGoal && ready && (
        <div
          className="pressure-tooltip"
          style={{
            left: `${(xScale(hover.game_time_seconds) / w) * 100}%`,
            top: '6px',
            transform: xScale(hover.game_time_seconds) > w - 110 ? 'translateX(-100%)'
              : xScale(hover.game_time_seconds) < 110 ? 'translateX(0)' : 'translateX(-50%)'
          }}
        >
          <div className="pressure-tooltip__time">{formatClock(hover.game_time_seconds)}</div>
          <div className="pressure-tooltip__row" style={{ color: homeTeamColor }}>
            {homeTeamAbbrev} {hover.home_rate.toFixed(0)}/60
          </div>
          <div className="pressure-tooltip__row" style={{ color: awayTeamColor }}>
            {awayTeamAbbrev} {hover.away_rate.toFixed(0)}/60
          </div>
        </div>
      )}

      {activeGoal && ready && (() => {
        const x = xScale(activeGoal.game_time_seconds);
        const cy = goalY(activeGoal);
        const color = activeGoal.team_id === homeTeamId ? homeTeamColor : awayTeamColor;
        const label = labelMap.get(goalKey(activeGoal.game_time_seconds, activeGoal.team_id));
        const edge = 130;
        const tx = x < edge ? '0%' : x > w - edge ? '-100%' : '-50%';
        const ty = cy < h * 0.45 ? '14px' : 'calc(-100% - 14px)';
        return (
          <GoalTooltip
            detail={activeGoal}
            label={label}
            accentColor={color}
            left={`${(x / w) * 100}%`}
            top={`${(cy / h) * 100}%`}
            transform={`translate(${tx}, ${ty})`}
          />
        );
      })()}
    </div>
  );
}

export default function ShotPressureChart(props: ShotPressureChartProps) {
  const [data, setData] = useState<PressurePoint[]>([]);
  const [goals, setGoals] = useState<GoalDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getGamePressure(props.gameId)
      .then(p => { if (active) setData(p); })
      .catch(() => { if (active) setError('Failed to load shot pressure'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [props.gameId]);

  useEffect(() => {
    let active = true;
    getGameGoals(props.gameId)
      .then(g => { if (active) setGoals(g); })
      .catch(() => { if (active) setGoals([]); });
    return () => { active = false; };
  }, [props.gameId]);

  const title = generateTitle(data, props.homeTeamAbbrev, props.awayTeamAbbrev);

  return (
    <ChartPanel
      title={title}
      subtitle="Smoothed unblocked shots per 60, all situations"
      expandable={false}
    >
      {loading ? (
        <div className="pressure-loading">
          <div className="skeleton-loader" style={{ width: '100%', height: '100%' }} />
        </div>
      ) : error || data.length === 0 ? (
        <div className="pressure-error">
          <p>{error || 'No shot data available'}</p>
        </div>
      ) : (
        <PressureSvg
          data={data}
          goals={goals}
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
