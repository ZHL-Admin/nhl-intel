import Tooltip from './Tooltip'
import './StatCard.css'

interface StatCardProps {
  label: string
  value: string | number
  rank?: number
  tooltip?: string
  sparklineData?: number[]
  trendDelta?: number
  trendLabel?: string
}

function StatCard({ label, value, rank, tooltip, sparklineData, trendDelta, trendLabel }: StatCardProps) {
  const getRankColor = (rank: number): string => {
    if (rank <= 10) return 'var(--color-data-positive)'
    if (rank >= 23) return 'var(--color-data-negative)'
    return 'var(--color-text-muted)'
  }

  const getRankText = (rank: number): string => {
    const suffix = rank === 1 ? 'st' : rank === 2 ? 'nd' : rank === 3 ? 'rd' : 'th'
    return `${rank}${suffix} in NHL`
  }

  const renderSparkline = () => {
    if (!sparklineData || sparklineData.length === 0) return null

    const width = 40
    const height = 20
    const padding = 2

    // Normalize data to fit viewBox
    const min = Math.min(...sparklineData)
    const max = Math.max(...sparklineData)
    const range = max - min || 1 // Avoid division by zero

    const points = sparklineData
      .map((val, idx) => {
        const x = (idx / (sparklineData.length - 1)) * width
        const y = height - padding - ((val - min) / range) * (height - padding * 2)
        return `${x},${y}`
      })
      .join(' ')

    const sparklineColor = getComputedStyle(document.documentElement)
      .getPropertyValue('--color-team-primary')
      .trim() || 'var(--color-data-1)'

    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="stat-card__sparkline"
      >
        <polyline
          points={points}
          fill="none"
          stroke={sparklineColor}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    )
  }

  const getTrendDeltaColor = (delta: number): string => {
    if (delta > 0.1) return 'var(--color-success)'
    if (delta < -0.1) return 'var(--color-danger)'
    return 'var(--color-text-muted)'
  }

  const formatTrendDelta = (delta: number): string => {
    if (delta > 0) return `+${delta.toFixed(1)}`
    return delta.toFixed(1)
  }

  const card = (
    <div className="stat-card">
      <div className="stat-card__label">{label}</div>
      <div className="stat-card__value mono">{value}</div>
      {rank !== undefined && (
        <div
          className="stat-card__rank"
          style={{ color: getRankColor(rank) }}
        >
          {getRankText(rank)}
        </div>
      )}
      {sparklineData && sparklineData.length > 0 && (
        <div className="stat-card__trend">
          {renderSparkline()}
          {trendDelta !== undefined && (
            <span
              className="stat-card__trend-delta mono"
              style={{ color: getTrendDeltaColor(trendDelta) }}
            >
              {formatTrendDelta(trendDelta)}
            </span>
          )}
          {trendLabel && (
            <span className="stat-card__trend-label">{trendLabel}</span>
          )}
        </div>
      )}
    </div>
  )

  if (tooltip) {
    return <Tooltip content={tooltip}>{card}</Tooltip>
  }

  return card
}

export default StatCard
