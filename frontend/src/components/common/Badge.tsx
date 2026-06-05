import React from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'
import './Badge.css'

type BadgeVariant = 'hot' | 'cold' | 'preview' | 'live' | 'small-sample'

interface BadgeProps {
  variant: BadgeVariant
}

function Badge({ variant }: BadgeProps) {
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
    }
  }

  return (
    <span className={`badge badge--${variant}`}>
      {getContent()}
    </span>
  )
}

export default Badge
