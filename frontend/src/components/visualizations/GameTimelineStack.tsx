import { useEffect, useMemo, useState } from 'react'
import { getGameXGWorm, getGamePressure, getGameGoals, getGameWinProb } from '../../api/games'
import { XGWormPoint, PressurePoint, GoalDetail, WinProbPoint } from '../../api/types'
import './GameTimelineStack.css'

interface Props {
  gameId: number
  homeTeamId: number
  awayTeamId: number
  homeAbbrev: string
  awayAbbrev: string
  homeColor: string
  awayColor: string
}

// Fixed internal coordinate system; the SVG scales to its container via viewBox.
const W = 900
const PAD_L = 16
const PAD_R = 16
const PLOT_W = W - PAD_L - PAD_R
const RAIL_H = 38
const LANE_H = 96
const LANE_GAP = 10
const AXIS_H = 22

const LANE1_TOP = RAIL_H
const LANE2_TOP = LANE1_TOP + LANE_H + LANE_GAP
const LANE3_TOP = LANE2_TOP + LANE_H + LANE_GAP
const H = LANE3_TOP + LANE_H + AXIS_H

const fmtClock = (s: number) => {
  const period = s < 3600 ? Math.floor(s / 1200) + 1 : 4
  const inPeriod = s < 3600 ? s - (period - 1) * 1200 : s - 3600
  const mm = String(Math.floor(inPeriod / 60)).padStart(2, '0')
  const ss = String(inPeriod % 60).padStart(2, '0')
  return `P${period} ${mm}:${ss}`
}

export default function GameTimelineStack({ gameId, homeTeamId, homeAbbrev, awayAbbrev, homeColor, awayColor }: Props) {
  const [worm, setWorm] = useState<XGWormPoint[]>([])
  const [pressure, setPressure] = useState<PressurePoint[]>([])
  const [goals, setGoals] = useState<GoalDetail[]>([])
  const [wpSeries, setWpSeries] = useState<WinProbPoint[]>([])
  const [hoverT, setHoverT] = useState<number | null>(null)

  useEffect(() => {
    let active = true
    getGameXGWorm(gameId).then(d => { if (active) setWorm(d) }).catch(() => {})
    getGamePressure(gameId).then(d => { if (active) setPressure(d) }).catch(() => {})
    getGameGoals(gameId).then(d => { if (active) setGoals(d) }).catch(() => {})
    getGameWinProb(gameId).then(d => { if (active) setWpSeries(d.series) }).catch(() => {})
    return () => { active = false }
  }, [gameId])

  const end = useMemo(() => {
    const lastPressure = pressure.length ? pressure[pressure.length - 1].game_time_seconds : 0
    const lastGoal = goals.length ? Math.max(...goals.map(g => g.game_time_seconds)) : 0
    const lastWp = wpSeries.length ? wpSeries[wpSeries.length - 1].elapsed_seconds : 0
    return Math.max(3600, lastPressure, lastGoal, lastWp)
  }, [pressure, goals, wpSeries])

  // Server-side win probability (Phase 2.4) replaces the old client-side Skellam toy.
  const wp = useMemo(
    () => wpSeries.map(p => ({ t: p.elapsed_seconds, homeWp: p.home_wp, leverage: p.leverage })),
    [wpSeries],
  )

  const xS = (t: number) => PAD_L + (t / end) * PLOT_W

  // Lane 1 — win probability (0..1 mapped top..bottom)
  const wpY = (p: number) => LANE1_TOP + (1 - p) * LANE_H
  const wpPath = wp.map((d, i) => `${i ? 'L' : 'M'} ${xS(d.t)} ${wpY(d.homeWp)}`).join(' ')
  const finalWp = wp.length ? wp[wp.length - 1].homeWp : 0.5
  const wpFavHome = finalWp >= 0.5
  const wpLabelTeam = wpFavHome ? homeAbbrev : awayAbbrev
  const wpLabelPct = Math.round((wpFavHome ? finalWp : 1 - finalWp) * 100)
  const wpLineColor = wpFavHome ? homeColor : awayColor

  // Lane 2 — cumulative xG differential (home positive, centred on "Even")
  const lane2Center = LANE2_TOP + LANE_H / 2
  const wormMaxAbs = Math.max(0.5, ...worm.map(d => Math.abs(d.cumulative_xg_diff)))
  const wormY = (v: number) => lane2Center - (v / wormMaxAbs) * (LANE_H / 2) * 0.88
  const wormPath = worm.map((d, i) => `${i ? 'L' : 'M'} ${xS(d.game_time_seconds)} ${wormY(d.cumulative_xg_diff)}`).join(' ')
  const finalWorm = worm.length ? worm[worm.length - 1].cumulative_xg_diff : 0

  // Lane 3 — shot pressure per 60 (home up, away down, mirrored areas)
  const lane3Center = LANE3_TOP + LANE_H / 2
  const maxRate = Math.max(1, ...pressure.map(p => Math.max(p.home_rate, p.away_rate)))
  const presUp = (r: number) => lane3Center - (r / maxRate) * (LANE_H / 2) * 0.92
  const presDn = (r: number) => lane3Center + (r / maxRate) * (LANE_H / 2) * 0.92
  const homeArea = pressure.length
    ? `M ${xS(pressure[0].game_time_seconds)} ${lane3Center} ` +
      pressure.map(p => `L ${xS(p.game_time_seconds)} ${presUp(p.home_rate)}`).join(' ') +
      ` L ${xS(pressure[pressure.length - 1].game_time_seconds)} ${lane3Center} Z`
    : ''
  const awayArea = pressure.length
    ? `M ${xS(pressure[0].game_time_seconds)} ${lane3Center} ` +
      pressure.map(p => `L ${xS(p.game_time_seconds)} ${presDn(p.away_rate)}`).join(' ') +
      ` L ${xS(pressure[pressure.length - 1].game_time_seconds)} ${lane3Center} Z`
    : ''

  // Goal rail with running score
  let hs = 0
  let as = 0
  const railGoals = [...goals].sort((a, b) => a.game_time_seconds - b.game_time_seconds).map(g => {
    if (g.team_id === homeTeamId) hs++; else as++
    return { ...g, label: `${as}-${hs}`, isHome: g.team_id === homeTeamId, x: xS(g.game_time_seconds) }
  })

  const periodTicks = [600, 1800, 3000].filter(t => t < end)
  const periodLines = [1200, 2400].filter(t => t < end)

  const handleMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const vbX = ((e.clientX - rect.left) / rect.width) * W
    const t = Math.max(0, Math.min(end, ((vbX - PAD_L) / PLOT_W) * end))
    setHoverT(t)
  }

  const nearest = <T extends { game_time_seconds: number }>(arr: T[], t: number): T | null => {
    if (!arr.length) return null
    let best = arr[0]
    for (const d of arr) if (Math.abs(d.game_time_seconds - t) < Math.abs(best.game_time_seconds - t)) best = d
    return best
  }

  const hoverX = hoverT != null ? xS(hoverT) : null
  const hWp = hoverT != null && wp.length ? wp.reduce((b, d) => Math.abs(d.t - hoverT) < Math.abs(b.t - hoverT) ? d : b) : null
  const hWorm = hoverT != null ? nearest(worm, hoverT) : null
  const hPres = hoverT != null ? nearest(pressure, hoverT) : null

  if (!worm.length && !pressure.length && !goals.length) {
    return <div style={{ height: 260 }} />
  }

  const laneLabel = (top: number, text: string) => (
    <text x={PAD_L + 4} y={top + 14} fontSize={12} fontWeight={600} fill="var(--color-text-secondary)">{text}</text>
  )

  return (
    <div className="timeline-stack">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', height: 'auto', display: 'block' }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverT(null)}
      >
        {/* period divider lines through all lanes */}
        {periodLines.map(t => (
          <line key={`pl-${t}`} x1={xS(t)} y1={RAIL_H} x2={xS(t)} y2={LANE3_TOP + LANE_H} stroke="var(--color-border-subtle)" strokeWidth={1} />
        ))}

        {/* dashed goal guide lines dropping through every lane */}
        {railGoals.map((g, i) => (
          <line key={`gl-${i}`} x1={g.x} y1={RAIL_H} x2={g.x} y2={LANE3_TOP + LANE_H}
            stroke={g.isHome ? homeColor : awayColor} strokeOpacity={0.35} strokeWidth={1} strokeDasharray="3 3" />
        ))}

        {/* goal rail */}
        <line x1={PAD_L} y1={RAIL_H - 12} x2={W - PAD_R} y2={RAIL_H - 12} stroke="var(--color-border)" strokeWidth={1} />
        {railGoals.map((g, i) => (
          <g key={`gd-${i}`}>
            <text x={g.x} y={RAIL_H - 20} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--color-text-muted)">{g.label}</text>
            <circle cx={g.x} cy={RAIL_H - 12} r={4.5} fill={g.isHome ? homeColor : awayColor} stroke="var(--color-bg-surface)" strokeWidth={1.5} />
          </g>
        ))}

        {/* Lane 1: win probability */}
        <line x1={PAD_L} y1={wpY(0.5)} x2={W - PAD_R} y2={wpY(0.5)} stroke="var(--color-border)" strokeWidth={1} strokeDasharray="2 3" />
        <text x={PAD_L + 4} y={wpY(0.5) - 4} fontSize={10} fill="var(--color-text-muted)">50%</text>
        <path d={wpPath} fill="none" stroke={wpLineColor} strokeWidth={2} strokeLinejoin="round" />
        {laneLabel(LANE1_TOP, 'Win probability')}
        {wp.length > 0 && (
          <text x={W - PAD_R - 2} y={wpY(finalWp) - 6} textAnchor="end" fontSize={11} fontWeight={700} fill={wpLineColor}>{wpLabelTeam} {wpLabelPct}%</text>
        )}

        {/* Lane 2: cumulative xG differential */}
        <line x1={PAD_L} y1={lane2Center} x2={W - PAD_R} y2={lane2Center} stroke="var(--color-border)" strokeWidth={1} />
        <text x={PAD_L + 4} y={lane2Center - 4} fontSize={10} fill="var(--color-text-muted)">Even</text>
        <path d={wormPath} fill="none" stroke="var(--color-text-secondary)" strokeWidth={2} strokeLinejoin="round" />
        {laneLabel(LANE2_TOP, 'Cumulative xG differential')}
        {worm.length > 0 && (
          <text x={W - PAD_R - 2} y={wormY(finalWorm) - 6} textAnchor="end" fontSize={11} fontWeight={700} fill={finalWorm >= 0 ? homeColor : awayColor}>
            {(finalWorm >= 0 ? homeAbbrev : awayAbbrev)} +{Math.abs(finalWorm).toFixed(2)}
          </text>
        )}

        {/* Lane 3: shot pressure */}
        <path d={homeArea} fill={homeColor} fillOpacity={0.30} />
        <path d={awayArea} fill={awayColor} fillOpacity={0.30} />
        <line x1={PAD_L} y1={lane3Center} x2={W - PAD_R} y2={lane3Center} stroke="var(--color-border)" strokeWidth={1} />
        {laneLabel(LANE3_TOP, 'Shot pressure, per 60')}

        {/* period axis labels */}
        {periodTicks.map((t, i) => (
          <text key={`pt-${t}`} x={xS(t)} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--color-text-muted)">P{i + 1}</text>
        ))}

        {/* shared crosshair */}
        {hoverX != null && (
          <line x1={hoverX} y1={RAIL_H} x2={hoverX} y2={LANE3_TOP + LANE_H} stroke="var(--color-text-primary)" strokeWidth={1} strokeOpacity={0.5} />
        )}
        {hoverX != null && hWp && <circle cx={hoverX} cy={wpY(hWp.homeWp)} r={3} fill={wpLineColor} />}
        {hoverX != null && hWorm && <circle cx={hoverX} cy={wormY(hWorm.cumulative_xg_diff)} r={3} fill="var(--color-text-secondary)" />}
      </svg>

      {/* hover readout */}
      <div className="timeline-stack__readout">
        {hoverT != null && hWp ? (
          <>
            <span className="timeline-stack__readout-time">{fmtClock(Math.round(hoverT))}</span>
            <span><strong style={{ color: wpFavHome ? homeColor : awayColor }}>{Math.round((hWp.homeWp >= 0.5 ? hWp.homeWp : 1 - hWp.homeWp) * 100)}%</strong> {hWp.homeWp >= 0.5 ? homeAbbrev : awayAbbrev} win</span>
            {hWp.leverage != null && <span>leverage <strong>{(hWp.leverage * 100).toFixed(0)}</strong></span>}
            {hWorm && <span>xG diff <strong>{hWorm.cumulative_xg_diff >= 0 ? '+' : ''}{hWorm.cumulative_xg_diff.toFixed(2)}</strong></span>}
            {hPres && <span>pressure <strong style={{ color: homeColor }}>{hPres.home_rate.toFixed(0)}</strong> / <strong style={{ color: awayColor }}>{hPres.away_rate.toFixed(0)}</strong></span>}
          </>
        ) : (
          <span className="timeline-stack__hint">Hover any minute to read all three lanes</span>
        )}
      </div>
    </div>
  )
}
