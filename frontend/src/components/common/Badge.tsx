import { TrendingUp, TrendingDown } from 'lucide-react'
import './Badge.css'

type BadgeVariant = 'hot' | 'cold' | 'preview' | 'live' | 'small-sample' | 'luck'

interface BadgeProps {
  variant: BadgeVariant
  label?: string
}

function Badge({ variant, label }: BadgeProps) {
  const getContent = () => {
    switch (variant) {
      case 'hot':
        return (
          <>
            <TrendingUp size={12} />
            <span>Hot</span>
          </>
        )
      case 'cold':
        return (
          <>
            <TrendingDown size={12} />
            <span>Cold</span>
          </>
        )
      case 'preview':
        return <span>Preview</span>
      case 'live':
        return (
          <>
            <span className="badge__pulse-dot"></span>
            <span>Live</span>
          </>
        )
      case 'small-sample':
        return <span>Small sample</span>
      case 'luck':
        return <span>{label || 'Luck'}</span>
    }
  }

  return (
    <span className={`badge badge--${variant}`}>
      {getContent()}
    </span>
  )
}

export default Badge
