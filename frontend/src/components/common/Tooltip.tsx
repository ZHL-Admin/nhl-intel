import React, { useState, useRef, useEffect } from 'react'
import './Tooltip.css'

interface TooltipProps {
  content: string
  children: React.ReactNode
}

function Tooltip({ content, children }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [position, setPosition] = useState({ top: 0, left: 0 })
  const timeoutRef = useRef<number | null>(null)
  const triggerRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  const showTooltip = () => {
    timeoutRef.current = window.setTimeout(() => {
      setIsVisible(true)
      updatePosition()
    }, 300)
  }

  const hideTooltip = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    setIsVisible(false)
  }

  const updatePosition = () => {
    if (!triggerRef.current || !tooltipRef.current) return

    const triggerRect = triggerRef.current.getBoundingClientRect()
    const tooltipRect = tooltipRef.current.getBoundingClientRect()

    let top = triggerRect.top - tooltipRect.height - 8
    let left = triggerRect.left + (triggerRect.width - tooltipRect.width) / 2

    if (top < 8) {
      top = triggerRect.bottom + 8
    }

    if (left < 8) {
      left = 8
    } else if (left + tooltipRect.width > window.innerWidth - 8) {
      left = window.innerWidth - tooltipRect.width - 8
    }

    setPosition({ top, left })
  }

  useEffect(() => {
    if (isVisible) {
      updatePosition()
    }
  }, [isVisible])

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  return (
    <>
      <div
        ref={triggerRef}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        tabIndex={0}
        role="button"
        aria-label={content}
        className="tooltip-trigger"
      >
        {children}
      </div>
      {isVisible && (
        <div
          ref={tooltipRef}
          className="tooltip"
          style={{
            position: 'fixed',
            top: `${position.top}px`,
            left: `${position.left}px`,
          }}
        >
          {content}
        </div>
      )}
    </>
  )
}

export default Tooltip
