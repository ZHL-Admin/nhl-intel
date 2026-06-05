import React from 'react'
import './SkeletonLoader.css'

interface SkeletonLoaderProps {
  width?: string | number
  height?: string | number
  borderRadius?: string | number
}

function SkeletonLoader({
  width = '100%',
  height = '20px',
  borderRadius = '4px'
}: SkeletonLoaderProps) {
  const style: React.CSSProperties = {
    width: typeof width === 'number' ? `${width}px` : width,
    height: typeof height === 'number' ? `${height}px` : height,
    borderRadius: typeof borderRadius === 'number' ? `${borderRadius}px` : borderRadius,
  }

  return <div className="skeleton-loader" style={style} />
}

export default SkeletonLoader
