import { useEffect, useRef, useState, useMemo } from 'react'
import * as d3 from 'd3'
import { hexbin } from 'd3-hexbin'
import './ShotMap.css'

export interface ShotAttempt {
  x: number
  y: number
  outcome: 'goal' | 'shot_on_goal' | 'missed_shot' | 'blocked_shot'
  situation: string
}

type SituationFilter = 'all' | '5v5' | 'pp' | 'pk'

interface ShotMapProps {
  homeShots: ShotAttempt[]
  awayShots: ShotAttempt[]
  homeTeamColor: string
  awayTeamColor: string
  homeTeamAbbrev: string
  awayTeamAbbrev: string
  situation?: SituationFilter
  title?: string
}

function ShotMap({
  homeShots,
  awayShots,
  homeTeamColor,
  awayTeamColor,
  homeTeamAbbrev,
  awayTeamAbbrev,
  situation = 'all',
  title
}: ShotMapProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [selectedSituation, setSelectedSituation] = useState<SituationFilter>(situation)

  // Helper: Parse NHL numeric situation codes to text
  const parseSituation = (code: string): string => {
    // NHL situation codes: format is typically XXYY where XX=away skaters, YY=home skaters
    // Common codes: 1551 = 5v5, 1451 = 4v5, 1541 = 5v4, 1360 = 3v6 (EN), etc.
    if (code === '1551') return '5v5'
    if (code === '1541') return '5v4'
    if (code === '1451') return '4v5'
    if (code === '1531') return '5v3'
    if (code === '1351') return '3v5'
    if (code === '1441') return '4v4'
    if (code === '1331') return '3v3'
    if (code === '1560' || code === '651') return '5v6' // Goalie pulled
    if (code === '1650' || code === '561') return '6v5' // Goalie pulled

    // If code doesn't match, try to parse manually
    // Codes are typically 4 digits, but treat as string
    return code
  }

  // Normalize shots to offensive zone and filter by situation
  const processShots = (shots: ShotAttempt[]) => {
    return shots
      .map(shot => ({
        ...shot,
        // Normalize x to offensive zone (always positive)
        normalizedX: Math.abs(shot.x),
        normalizedY: shot.y,
        parsedSituation: parseSituation(shot.situation)
      }))
      .filter(shot => {
        // Filter by situation
        if (selectedSituation === 'all') return true

        if (selectedSituation === '5v5') {
          return shot.parsedSituation === '5v5'
        }

        if (selectedSituation === 'pp') {
          return ['5v4', '5v3', '4v3', '6v5'].includes(shot.parsedSituation)
        }

        if (selectedSituation === 'pk') {
          return ['4v5', '3v5', '3v4', '5v6'].includes(shot.parsedSituation)
        }

        return true
      })
      .filter(shot => shot.normalizedX > 25) // Only offensive zone
  }

  const awayAttackingShots = useMemo(() =>
    processShots(awayShots),
    [awayShots, selectedSituation]
  )

  const homeAttackingShots = useMemo(() =>
    processShots(homeShots),
    [homeShots, selectedSituation]
  )

  // Generate dynamic title based on shot distribution
  const dynamicTitle = useMemo(() => {
    if (title) return title

    const awayCount = awayAttackingShots.length
    const homeCount = homeAttackingShots.length
    const diff = Math.abs(awayCount - homeCount)
    const pctDiff = Math.max(awayCount, homeCount) / Math.min(awayCount, homeCount) - 1

    if (pctDiff > 0.25 && diff > 5) {
      const leader = awayCount > homeCount ? awayTeamAbbrev : homeTeamAbbrev
      return `${leader} dominated the shot attempt map`
    }

    return `Shot attempt map — ${awayTeamAbbrev} vs ${homeTeamAbbrev}`
  }, [awayAttackingShots, homeAttackingShots, awayTeamAbbrev, homeTeamAbbrev, title])

  useEffect(() => {
    if (!svgRef.current) return

    // Clear previous render
    d3.select(svgRef.current).selectAll('*').remove()

    // SVG dimensions
    const width = 800
    const height = 340
    const centerX = width / 2

    // NHL rink dimensions: 200ft x 85ft
    // Map to SVG: x from -100 to 100, y from -42.5 to 42.5
    const xScale = d3.scaleLinear().domain([-100, 100]).range([0, width])
    const yScale = d3.scaleLinear().domain([-42.5, 42.5]).range([0, height])

    const svg = d3.select(svgRef.current)
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')

    // Rink background
    svg.append('rect')
      .attr('width', width)
      .attr('height', height)
      .attr('fill', 'var(--color-bg-elevated)')
      .attr('opacity', 0.4)

    // Helper to draw rink markings
    const drawCircle = (cx: number, cy: number, r: number) => {
      svg.append('circle')
        .attr('cx', xScale(cx))
        .attr('cy', yScale(cy))
        .attr('r', yScale(cy + r) - yScale(cy))
        .attr('fill', 'none')
        .attr('stroke', 'var(--color-border)')
        .attr('stroke-opacity', 0.6)
        .attr('stroke-width', 1)
    }

    // Outer rink boundary with rounded corners
    const rinkPath = `
      M ${xScale(-100) + 28} ${yScale(-42.5)}
      L ${xScale(100) - 28} ${yScale(-42.5)}
      Q ${xScale(100)} ${yScale(-42.5)} ${xScale(100)} ${yScale(-42.5) + 28}
      L ${xScale(100)} ${yScale(42.5) - 28}
      Q ${xScale(100)} ${yScale(42.5)} ${xScale(100) - 28} ${yScale(42.5)}
      L ${xScale(-100) + 28} ${yScale(42.5)}
      Q ${xScale(-100)} ${yScale(42.5)} ${xScale(-100)} ${yScale(42.5) - 28}
      L ${xScale(-100)} ${yScale(-42.5) + 28}
      Q ${xScale(-100)} ${yScale(-42.5)} ${xScale(-100) + 28} ${yScale(-42.5)}
      Z
    `
    svg.append('path')
      .attr('d', rinkPath)
      .attr('fill', 'none')
      .attr('stroke', 'var(--color-border)')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 1)

    // Center line
    svg.append('line')
      .attr('x1', xScale(0))
      .attr('y1', yScale(-42.5))
      .attr('x2', xScale(0))
      .attr('y2', yScale(42.5))
      .attr('stroke', 'var(--color-border)')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 1)

    // Blue lines
    svg.append('line')
      .attr('x1', xScale(25))
      .attr('y1', yScale(-42.5))
      .attr('x2', xScale(25))
      .attr('y2', yScale(42.5))
      .attr('stroke', 'var(--color-border)')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 1)

    svg.append('line')
      .attr('x1', xScale(-25))
      .attr('y1', yScale(-42.5))
      .attr('x2', xScale(-25))
      .attr('y2', yScale(42.5))
      .attr('stroke', 'var(--color-border)')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 1)

    // Center ice circle
    drawCircle(0, 0, 15)

    // Face-off circles
    drawCircle(69, 22, 15)
    drawCircle(69, -22, 15)
    drawCircle(-69, 22, 15)
    drawCircle(-69, -22, 15)

    // Goal creases (simplified as semi-circles)
    const drawCrease = (xPos: number) => {
      const creaseData = [
        [xPos, 0],
        [xPos - 4, 2],
        [xPos - 4, -2],
        [xPos, 0]
      ]
      svg.append('path')
        .attr('d', d3.line()
          .x(d => xScale(d[0]))
          .y(d => yScale(d[1]))(creaseData as [number, number][]) || '')
        .attr('fill', 'none')
        .attr('stroke', 'var(--color-border)')
        .attr('stroke-opacity', 0.6)
        .attr('stroke-width', 1.5)
    }
    drawCrease(89)
    drawCrease(-89)

    // Goal lines
    svg.append('line')
      .attr('x1', xScale(89))
      .attr('y1', yScale(-3))
      .attr('x2', xScale(89))
      .attr('y2', yScale(3))
      .attr('stroke', 'var(--color-border)')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 2)

    svg.append('line')
      .attr('x1', xScale(-89))
      .attr('y1', yScale(-3))
      .attr('x2', xScale(-89))
      .attr('y2', yScale(3))
      .attr('stroke', 'var(--color-border)')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 2)

    // ========================================
    // AWAY TEAM HEXBINS (left half, attacking right)
    // ========================================
    if (awayAttackingShots.length > 0) {
      const awayHexbin = hexbin()
        .x(d => {
          // Map offensive zone [25, 100] to left half [centerX, 0]
          // x=89 (near goal) -> near centerX, x=25 (blue line) -> near 0
          const shot = d as any
          return xScale(100 - shot.normalizedX)
        })
        .y(d => yScale((d as any).normalizedY))
        .radius(14)

      const awayBins = awayHexbin(awayAttackingShots as any)
      const awayMaxDensity = d3.max(awayBins, d => d.length) || 1

      const awayColorScale = d3.scaleLinear<string>()
        .domain([1, awayMaxDensity])
        .range([`${awayTeamColor}33`, awayTeamColor])

      svg.append('g')
        .selectAll('path')
        .data(awayBins)
        .enter()
        .append('path')
        .attr('d', awayHexbin.hexagon())
        .attr('transform', d => `translate(${d.x},${d.y})`)
        .attr('fill', d => awayColorScale(d.length))
        .attr('stroke', 'none')
    }

    // ========================================
    // HOME TEAM HEXBINS (right half, attacking left)
    // ========================================
    if (homeAttackingShots.length > 0) {
      const homeHexbin = hexbin()
        .x(d => {
          // Map offensive zone [25, 100] to right half [centerX, width]
          // x=89 (near goal) -> near centerX, x=25 (blue line) -> near width
          const shot = d as any
          return xScale(-100 + shot.normalizedX)
        })
        .y(d => yScale((d as any).normalizedY))
        .radius(14)

      const homeBins = homeHexbin(homeAttackingShots as any)
      const homeMaxDensity = d3.max(homeBins, d => d.length) || 1

      const homeColorScale = d3.scaleLinear<string>()
        .domain([1, homeMaxDensity])
        .range([`${homeTeamColor}33`, homeTeamColor])

      svg.append('g')
        .selectAll('path')
        .data(homeBins)
        .enter()
        .append('path')
        .attr('d', homeHexbin.hexagon())
        .attr('transform', d => `translate(${d.x},${d.y})`)
        .attr('fill', d => homeColorScale(d.length))
        .attr('stroke', 'none')
    }

    // ========================================
    // GOAL MARKERS (on top)
    // ========================================
    // Away goals (left half)
    awayAttackingShots
      .filter(shot => shot.outcome === 'goal')
      .forEach(shot => {
        svg.append('circle')
          .attr('cx', xScale(100 - shot.normalizedX))
          .attr('cy', yScale(shot.normalizedY))
          .attr('r', 5)
          .attr('fill', 'white')
          .attr('stroke', awayTeamColor)
          .attr('stroke-width', 2)
      })

    // Home goals (right half)
    homeAttackingShots
      .filter(shot => shot.outcome === 'goal')
      .forEach(shot => {
        svg.append('circle')
          .attr('cx', xScale(-100 + shot.normalizedX))
          .attr('cy', yScale(shot.normalizedY))
          .attr('r', 5)
          .attr('fill', 'white')
          .attr('stroke', homeTeamColor)
          .attr('stroke-width', 2)
      })

    // ========================================
    // TEAM LABELS
    // ========================================
    // Away team label (left zone)
    svg.append('text')
      .attr('x', xScale(62.5))
      .attr('y', yScale(35))
      .attr('text-anchor', 'middle')
      .attr('font-size', 'var(--text-sm)')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-weight', 500)
      .attr('fill', 'var(--color-text-secondary)')
      .text(awayTeamAbbrev)

    svg.append('text')
      .attr('x', xScale(62.5))
      .attr('y', yScale(35) + 14)
      .attr('text-anchor', 'middle')
      .attr('font-size', 'var(--text-xs)')
      .attr('fill', 'var(--color-text-muted)')
      .text(`${awayAttackingShots.length} attempts`)

    // Home team label (right zone)
    svg.append('text')
      .attr('x', xScale(-62.5))
      .attr('y', yScale(35))
      .attr('text-anchor', 'middle')
      .attr('font-size', 'var(--text-sm)')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-weight', 500)
      .attr('fill', 'var(--color-text-secondary)')
      .text(homeTeamAbbrev)

    svg.append('text')
      .attr('x', xScale(-62.5))
      .attr('y', yScale(35) + 14)
      .attr('text-anchor', 'middle')
      .attr('font-size', 'var(--text-xs)')
      .attr('fill', 'var(--color-text-muted)')
      .text(`${homeAttackingShots.length} attempts`)

  }, [awayAttackingShots, homeAttackingShots, awayTeamColor, homeTeamColor, awayTeamAbbrev, homeTeamAbbrev])

  return (
    <div className="shot-map">
      {/* Title */}
      <h3 className="shot-map__title">{dynamicTitle}</h3>

      {/* Situation Toggle */}
      <div className="shot-map__controls">
        <div className="shot-map__toggle">
          <button
            className={`shot-map__toggle-option ${selectedSituation === 'all' ? 'shot-map__toggle-option--active' : ''}`}
            onClick={() => setSelectedSituation('all')}
          >
            All
          </button>
          <button
            className={`shot-map__toggle-option ${selectedSituation === '5v5' ? 'shot-map__toggle-option--active' : ''}`}
            onClick={() => setSelectedSituation('5v5')}
          >
            5v5
          </button>
          <button
            className={`shot-map__toggle-option ${selectedSituation === 'pp' ? 'shot-map__toggle-option--active' : ''}`}
            onClick={() => setSelectedSituation('pp')}
          >
            PP
          </button>
          <button
            className={`shot-map__toggle-option ${selectedSituation === 'pk' ? 'shot-map__toggle-option--active' : ''}`}
            onClick={() => setSelectedSituation('pk')}
          >
            PK
          </button>
        </div>
      </div>

      {/* SVG Rink */}
      <div className="shot-map__rink">
        <svg ref={svgRef} />
      </div>

      {/* Legend */}
      <div className="shot-map__legend">
        <div className="shot-map__legend-item">
          <div className="shot-map__legend-hex-group">
            <svg width="24" height="24">
              <path
                d="M12,2 L20,7 L20,17 L12,22 L4,17 L4,7 Z"
                fill={`${awayTeamColor}33`}
              />
            </svg>
            <span className="shot-map__legend-label">Low</span>
          </div>
          <div className="shot-map__legend-hex-group">
            <svg width="24" height="24">
              <path
                d="M12,2 L20,7 L20,17 L12,22 L4,17 L4,7 Z"
                fill={awayTeamColor}
              />
            </svg>
            <span className="shot-map__legend-label">High</span>
          </div>
        </div>
        <div className="shot-map__legend-item">
          <svg width="24" height="24">
            <circle cx="12" cy="12" r="5" fill="white" stroke={awayTeamColor} strokeWidth="2" />
          </svg>
          <span className="shot-map__legend-label">Goals</span>
        </div>
      </div>
    </div>
  )
}

export default ShotMap
