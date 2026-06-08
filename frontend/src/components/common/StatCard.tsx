import Tooltip from './Tooltip'
import './StatCard.css'

interface StatCardProps {
  label: string
  value: string | number
  rank?: number
  tooltip?: string
}

function StatCard({ label, value, rank, tooltip }: StatCardProps) {
  const getRankColor = (rank: number): string => {
    if (rank <= 10) return 'var(--color-data-positive)'
    if (rank >= 23) return 'var(--color-data-negative)'
    return 'var(--color-text-muted)'
  }

  const getRankText = (rank: number): string => {
    const suffix = rank === 1 ? 'st' : rank === 2 ? 'nd' : rank === 3 ? 'rd' : 'th'
    return `${rank}${suffix} in NHL`
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
    </div>
  )

  if (tooltip) {
    return <Tooltip content={tooltip}>{card}</Tooltip>
  }

  return card
}

export default StatCard
