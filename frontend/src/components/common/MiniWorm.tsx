import './MiniWorm.css';

interface MiniWormProps {
  data: { time: number; diff: number }[];
  /** Kept for call-site compatibility; R8 sparklines are single-ink, no fills. */
  goals?: { time: number; label: string }[];
  homeColor?: string;
  awayColor?: string;
  /** Stroke color; defaults to ice data ink. Pass a team color on the scoreboard (§01). */
  color?: string;
  /** Draw a hairline midline at zero differential (§01 chart grammar). */
  midline?: boolean;
  width?: number;
  height?: number;
}

/**
 * MiniWorm — the R8 sparkline (§6). A single 1.5px stroke of the score/xG differential over
 * time with a last-point dot; no fills, no axes. Team-colored on the scoreboard with an optional
 * hairline midline. (The full worm with fills, baseline, and goal markers is R3, in GameDetail.)
 */
export default function MiniWorm({
  data, color = 'var(--color-ice-600)', midline = false, width = 96, height = 28,
}: MiniWormProps) {
  if (data.length === 0) {
    return <div className="mini-worm mini-worm--empty" style={{ width, height }} />;
  }

  const maxTime = Math.max(...data.map((d) => d.time)) || 1;
  const maxDiff = Math.max(...data.map((d) => Math.abs(d.diff)), 1e-6);
  const range = maxDiff * 1.1; // 10% headroom

  const xScale = (time: number) => (time / maxTime) * width;
  const yScale = (diff: number) => height / 2 - (diff / range) * (height / 2);

  const pathData = data
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(p.time)} ${yScale(p.diff)}`)
    .join(' ');
  const last = data[data.length - 1];

  return (
    <svg className="mini-worm" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      {midline && (
        <line x1={0} y1={height / 2} x2={width} y2={height / 2}
          stroke="var(--color-border)" strokeWidth={1} />
      )}
      <path
        d={pathData}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={xScale(last.time)} cy={yScale(last.diff)} r={2.5} fill={color} />
    </svg>
  );
}
