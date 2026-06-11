import './MiniWorm.css';

interface MiniWormProps {
  data: { time: number; diff: number }[];
  goals?: { time: number; label: string }[];
  homeColor: string;
  awayColor: string;
  width?: number;
  height?: number;
}

export default function MiniWorm({
  data,
  goals = [],
  homeColor,
  awayColor,
  width = 300,
  height = 60
}: MiniWormProps) {
  if (data.length === 0) {
    return <div className="mini-worm mini-worm--empty" style={{ width, height }} />;
  }

  const maxTime = Math.max(...data.map(d => d.time));
  const maxDiff = Math.max(...data.map(d => Math.abs(d.diff)));
  const range = maxDiff * 1.1; // 10% padding

  const xScale = (time: number) => (time / maxTime) * width;
  const yScale = (diff: number) => height / 2 - (diff / range) * (height / 2);

  // Generate path
  const pathData = data.map((point, i) => {
    const x = xScale(point.time);
    const y = yScale(point.diff);
    return i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`;
  }).join(' ');

  // Generate positive and negative area fills
  const positiveAreaData = data.map((point, i) => {
    const x = xScale(point.time);
    const y = Math.min(yScale(point.diff), height / 2);
    if (i === 0) return `M ${x} ${height / 2} L ${x} ${y}`;
    return `L ${x} ${y}`;
  }).join(' ') + ` L ${xScale(data[data.length - 1].time)} ${height / 2} Z`;

  const negativeAreaData = data.map((point, i) => {
    const x = xScale(point.time);
    const y = Math.max(yScale(point.diff), height / 2);
    if (i === 0) return `M ${x} ${height / 2} L ${x} ${y}`;
    return `L ${x} ${y}`;
  }).join(' ') + ` L ${xScale(data[data.length - 1].time)} ${height / 2} Z`;

  return (
    <svg
      className="mini-worm"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
    >
      {/* Positive area (home leading) */}
      <path
        d={positiveAreaData}
        fill={homeColor}
        fillOpacity={0.15}
      />

      {/* Negative area (away leading) */}
      <path
        d={negativeAreaData}
        fill={awayColor}
        fillOpacity={0.15}
      />

      {/* Zero reference line */}
      <line
        x1={0}
        y1={height / 2}
        x2={width}
        y2={height / 2}
        stroke="var(--color-border-subtle)"
        strokeWidth={1}
      />

      {/* Line */}
      <path
        d={pathData}
        fill="none"
        stroke="var(--color-text-muted)"
        strokeWidth={1.5}
      />

      {/* Goal dots */}
      {goals.map((goal, i) => {
        const dataPoint = data.find(d => d.time >= goal.time) || data[data.length - 1];
        const teamColor = dataPoint.diff > 0 ? homeColor : awayColor;

        return (
          <circle
            key={i}
            cx={xScale(goal.time)}
            cy={yScale(dataPoint.diff)}
            r={4}
            fill={teamColor}
          />
        );
      })}
    </svg>
  );
}
