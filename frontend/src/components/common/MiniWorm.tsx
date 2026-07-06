import './MiniWorm.css';

interface MiniWormProps {
  data: { time: number; diff: number }[];
  /** Kept for call-site compatibility; R8 sparklines are single-ink (ice), no team fills/markers. */
  goals?: { time: number; label: string }[];
  homeColor?: string;
  awayColor?: string;
  width?: number;
  height?: number;
}

/**
 * MiniWorm — the R8 sparkline (§6). A single 1.5px ice stroke of the score/xG differential over
 * time with a last-point dot; no fills, no axes. Fixed 96x28 box; lives only inside rows and
 * identity headers. (The full worm with fills, baseline, and goal markers is R3, in GameDetail.)
 */
export default function MiniWorm({ data, width = 96, height = 28 }: MiniWormProps) {
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
      <path
        d={pathData}
        fill="none"
        stroke="var(--color-ice-600)"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={xScale(last.time)} cy={yScale(last.diff)} r={2.5} fill="var(--color-ice-600)" />
    </svg>
  );
}
