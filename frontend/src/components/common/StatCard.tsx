import { Info } from 'lucide-react'
import Tooltip from './Tooltip'
import './StatCard.css'

interface StatCardProps {
  label: string
  value: string | number
  rank?: number
  /** Pre-formatted rank line (e.g. "4th of 248") for within-position ranks; takes precedence over
   *  `rank` and skips the NHL-wide wording/tiering. Pair with `rankTier` for color. */
  rankText?: string
  rankTier?: 'top' | 'mid' | 'bottom'
  /** 0..1 within-position percentile. Renders a thin fill bar and drives a green/amber/red
   *  gradient on the rank pill (so e.g. 6th and 129th do not read as equally good). */
  percentile?: number | null
  tooltip?: string
  sparklineData?: number[]
  trendDelta?: number
  trendLabel?: string
}

// Percentile -> design-token color (green strong / amber soft / red weak).
const pctFg = (p: number) => (p >= 0.66 ? 'var(--color-success)' : p >= 0.33 ? 'var(--color-warning)' : 'var(--color-danger)')
const pctBgVar = (p: number) => (p >= 0.66 ? 'var(--color-success-bg)' : p >= 0.33 ? 'var(--color-warning-bg)' : 'var(--color-danger-bg)')

function StatCard({ label, value, rank, rankText, rankTier, percentile, tooltip, sparklineData, trendDelta, trendLabel }: StatCardProps) {
  const getRankTier = (rank: number): string => {
    if (rank <= 10) return 'top'
    if (rank >= 23) return 'bottom'
    return 'mid'
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
          style={{ stroke: 'var(--color-team-primary)' }}
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

  return (
    <div className="stat-card">
      <div className="stat-card__header">
        <span className="stat-card__label">{label}</span>
        {tooltip && (
          <Tooltip content={tooltip}>
            <Info size={14} className="stat-card__info-icon" />
          </Tooltip>
        )}
      </div>
      <div className="stat-card__value mono">{value}</div>
      {percentile != null && (
        <div className="stat-card__pctbar" aria-hidden="true">
          <span style={{ width: `${Math.round(percentile * 100)}%`, background: pctFg(percentile) }} />
        </div>
      )}
      {rankText !== undefined ? (
        <div
          className={`stat-card__rank${percentile == null ? ` stat-card__rank--${rankTier ?? 'mid'}` : ''}`}
          style={percentile != null ? { color: pctFg(percentile), background: pctBgVar(percentile) } : undefined}>
          {rankText}
        </div>
      ) : rank !== undefined && (
        <div className={`stat-card__rank stat-card__rank--${getRankTier(rank)}`}>
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
}

export default StatCard
