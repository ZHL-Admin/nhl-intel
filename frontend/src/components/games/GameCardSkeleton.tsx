import { SkeletonLoader } from '../common'
import './GameCard.css'

function GameCardSkeleton() {
  return (
    <div className="game-card">
      <div className="game-card__header">
        <div className="game-card__team">
          <SkeletonLoader width={40} height={40} borderRadius={4} />
          <SkeletonLoader width={50} height={20} />
        </div>
        <SkeletonLoader width={80} height={32} />
        <div className="game-card__team">
          <SkeletonLoader width={50} height={20} />
          <SkeletonLoader width={40} height={40} borderRadius={4} />
        </div>
      </div>
      <div style={{ margin: 'var(--space-2) 0' }}>
        <SkeletonLoader height={36} borderRadius={4} />
      </div>
      <SkeletonLoader height={16} />
    </div>
  )
}

export default GameCardSkeleton
