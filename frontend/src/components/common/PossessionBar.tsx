import React from 'react'
import './PossessionBar.css'

interface PossessionBarProps {
  homeValue: number
  awayValue: number
  homeColor?: string
  awayColor?: string
  height?: number
}

function PossessionBar({
  homeValue,
  awayValue,
  homeColor = 'var(--color-data-orange)',
  awayColor = 'var(--color-data-blue)',
  height = 28
}: PossessionBarProps) {
  const total = homeValue + awayValue
  const awayPercentage = total > 0 ? (awayValue / total) * 100 : 50
  const homePercentage = total > 0 ? (homeValue / total) * 100 : 50

  return (
    <div className="possession-bar" style={{ height: `${height}px` }}>
      <div
        className="possession-bar__away"
        style={{
          width: `${awayPercentage}%`,
          backgroundColor: awayColor,
          opacity: 0.7,
        }}
      >
        <span className="possession-bar__value possession-bar__value--left">
          {awayValue.toFixed(1)}%
        </span>
      </div>
      <div
        className="possession-bar__home"
        style={{
          width: `${homePercentage}%`,
          backgroundColor: homeColor,
          opacity: 0.7,
        }}
      >
        <span className="possession-bar__value possession-bar__value--right">
          {homeValue.toFixed(1)}%
        </span>
      </div>
    </div>
  )
}

export default PossessionBar
