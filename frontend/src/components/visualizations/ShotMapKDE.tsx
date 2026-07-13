/**
 * ShotMapKDE (Blueprint V8) — one standard rink, both teams. Attempts are folded to their attacking
 * end (away attacks LEFT x<0, home RIGHT x>0) by mirroring on |x|, since the shot feed has no period
 * to normalize by. A heat-ramp KDE per side is clipped to the rink outline (zero density past the
 * boards); goals (shot_type='goal') overlay as danger dots with a surface halo. Captions are
 * attempts-only (the feed's SOG field is unreliable — F5); sides are labelled by attacking direction.
 */
import { useState, useEffect, useMemo } from 'react'
import * as d3 from 'd3'
import ChartPanel from '../common/ChartPanel'
import SkeletonLoader from '../common/SkeletonLoader'
import GoalPopup, { type GoalInfo, buildGoalInfoMap } from '../games/GoalPopup'
import { getGameShots, getGameGoals } from '../../api/games'
import type { ShotAttempt, GoalDetail } from '../../api/types'
import './ShotMapKDE.css'

interface ShotMapKDEProps {
  gameId: number
  homeTeamAbbrev: string
  awayTeamAbbrev: string
  /** Pole ink (§0): home passes --line-blue, away passes --line-red. Not team identity. */
  homeTeamColor: string
  awayTeamColor: string
  situation: string
  /** One generated caption line (§6). */
  caption?: string
}

// Rink in feet: x ∈ [-100, 100], y ∈ [-42.5, 42.5]. SVG works in a [0,200] × [0,85] pixel box.
const RX = 28              // corner radius (§V8a)
const toPx = (x: number, y: number): [number, number] => [x + 100, 42.5 - y]

interface NShot { x: number; y: number; goal: boolean; src: ShotAttempt; team: string }

/** Fold a shot to one attacking end: |x|, mirroring y when the x sign flips; away attacks left. */
function normalize(s: ShotAttempt, attackRight: boolean, team: string): NShot {
  let nx = Math.abs(s.x)
  const ny = s.x < 0 ? -s.y : s.y
  if (!attackRight) nx = -nx
  return { x: nx, y: ny, goal: s.shot_type === 'goal', src: s, team }
}

// Pole heat ramp (§6): a single pole ink ramped from a faint tint to full saturation. The percentage
// number is the only digit that varies, so d3's string interpolation walks it cleanly.
function poleRamp(pole: string): string[] {
  return [
    `color-mix(in srgb, ${pole} 14%, var(--color-bg-surface))`,
    `color-mix(in srgb, ${pole} 36%, var(--color-bg-surface))`,
    `color-mix(in srgb, ${pole} 58%, var(--color-bg-surface))`,
    `color-mix(in srgb, ${pole} 80%, var(--color-bg-surface))`,
    pole,
  ]
}

function densityPaths(shots: NShot[], pole: string): { d: string; fill: string; opacity: number }[] {
  const pts = shots.map((s) => toPx(s.x, s.y))
  if (pts.length < 3) return []
  const density = d3.contourDensity<[number, number]>()
    .x((d) => d[0]).y((d) => d[1])
    .size([200, 85]).cellSize(2).bandwidth(6).thresholds(12)(pts)
  const max = d3.max(density, (c) => c.value) || 1
  const heat = d3.scaleLinear<string>().domain([0, 0.25, 0.5, 0.75, 1]).range(poleRamp(pole)).clamp(true)
  const geo = d3.geoPath()
  return density.map((c) => {
    const t = c.value / max
    return { d: geo(c) ?? '', fill: heat(t), opacity: Math.min(0.85, t * 0.85) }
  })
}

export default function ShotMapKDE({ gameId, homeTeamAbbrev, awayTeamAbbrev, homeTeamColor, awayTeamColor, caption }: ShotMapKDEProps) {
  const [shots, setShots] = useState<{ home: ShotAttempt[]; away: ShotAttempt[] } | null>(null)
  const [goals, setGoals] = useState<GoalDetail[]>([])

  useEffect(() => {
    let active = true
    getGameShots(gameId).then((d) => {
      if (active) setShots({ home: (d as unknown as { home_shots: ShotAttempt[] }).home_shots ?? [], away: (d as unknown as { away_shots: ShotAttempt[] }).away_shots ?? [] })
    }).catch(() => active && setShots({ home: [], away: [] }))
    getGameGoals(gameId).then((d) => active && setGoals(d)).catch(() => {})
    return () => { active = false }
  }, [gameId])

  // Same goal data as the timeline (running score + assists), keyed by scorer + clock (item 1).
  const goalMap = useMemo(() => buildGoalInfoMap(goals, homeTeamAbbrev), [goals, homeTeamAbbrev])

  const [popup, setPopup] = useState<{ goal: GoalInfo; anchor: { x: number; y: number } } | null>(null)

  const model = useMemo(() => {
    if (!shots) return null
    const homeN = shots.home.map((s) => normalize(s, true, homeTeamAbbrev))
    const awayN = shots.away.map((s) => normalize(s, false, awayTeamAbbrev))
    const outside = [...homeN, ...awayN].filter((p) => Math.abs(p.x) > 100 || Math.abs(p.y) > 42.5).length
    // Sanity smoke test (§V8f): attempts outside the rink after normalization should be ~0.
    // eslint-disable-next-line no-console
    console.log(`[shot-map] outside-rink after normalize: ${outside} / ${homeN.length + awayN.length}`)
    return {
      // Pole heat (§0/§6): home end reads blue, away end reads red — team ink is retired here.
      homePaths: densityPaths(homeN, homeTeamColor),
      awayPaths: densityPaths(awayN, awayTeamColor),
      goals: [...homeN, ...awayN].filter((s) => s.goal),
      awayN, homeN, outside,
    }
  }, [shots, homeTeamAbbrev, awayTeamAbbrev, homeTeamColor, awayTeamColor])

  if (!shots) return <div className="shot-map-kde"><SkeletonLoader height={340} /></div>
  if (!model || (model.awayN.length + model.homeN.length) === 0) return null

  const crease = (goalX: number, dir: 1 | -1) => {
    // 6ft crease semicircle at the goal line, opening toward centre ice
    const [cx, cy] = toPx(goalX, 0)
    const r = 6
    return `M ${cx} ${cy - r} A ${r} ${r} 0 0 ${dir === 1 ? 0 : 1} ${cx} ${cy + r}`
  }

  return (
    <>
    <ChartPanel title="Where the chances came from" subtitle="Shot-attempt density, folded to each team's attacking end · goals marked" expandable={false} autoHeight>
      <div className="shot-map-kde">
        <svg viewBox="0 0 200 85" className="shot-map-kde__svg" role="img"
          aria-label="Shot-attempt density map, away team attacking left, home team attacking right, with goals marked">
          <defs>
            <clipPath id={`rink-clip-${gameId}`}>
              <rect x="0" y="0" width="200" height="85" rx={RX} ry={RX} />
            </clipPath>
          </defs>

          {/* boards */}
          <rect x="0.5" y="0.5" width="199" height="84" rx={RX} ry={RX} className="rink__boards" />

          {/* density, clipped to the rink (§V8c) */}
          <g clipPath={`url(#rink-clip-${gameId})`}>
            {model.awayPaths.map((p, i) => <path key={`a${i}`} d={p.d} fill={p.fill} fillOpacity={p.opacity} />)}
            {model.homePaths.map((p, i) => <path key={`h${i}`} d={p.d} fill={p.fill} fillOpacity={p.opacity} />)}
          </g>

          {/* markings */}
          <line x1="100" y1="0" x2="100" y2="85" className="rink__center" />
          <line x1="75" y1="0" x2="75" y2="85" className="rink__blue" />
          <line x1="125" y1="0" x2="125" y2="85" className="rink__blue" />
          <line x1="11" y1="4" x2="11" y2="81" className="rink__goal" />
          <line x1="189" y1="4" x2="189" y2="81" className="rink__goal" />
          <path d={crease(-89, 1)} className="rink__crease" />
          <path d={crease(89, -1)} className="rink__crease" />
          {[[69, 22], [69, -22], [-69, 22], [-69, -22], [20, 22], [20, -22], [-20, 22], [-20, -22]].map(([x, y], i) => {
            const [cx, cy] = toPx(x, y)
            return <circle key={i} cx={cx} cy={cy} r={1.1} className="rink__faceoff" />
          })}
          <circle cx="100" cy="42.5" r="1.3" className="rink__faceoff" />

          {/* goals — click for detail (item 5) */}
          {model.goals.map((g, i) => {
            const [cx, cy] = toPx(g.x, g.y)
            return (
              <circle
                key={`g${i}`} cx={cx} cy={cy} r={2.2}
                fill={g.team === homeTeamAbbrev ? homeTeamColor : awayTeamColor}
                stroke="var(--color-bg-surface)" strokeWidth={0.9}
                style={{ cursor: 'pointer' }}
                onClick={(e) => setPopup({
                  anchor: { x: e.clientX, y: e.clientY },
                  goal: goalMap.get(`${g.src.scorer_id}:${g.src.time_in_period}`) ?? {
                    scorerId: g.src.scorer_id, scorerName: g.src.scorer_name, teamAbbrev: g.team,
                    periodLabel: g.src.period != null ? `P${g.src.period}` : '',
                    timeInPeriod: g.src.time_in_period,
                    assists: [g.src.assist1_name, g.src.assist2_name].filter(Boolean) as string[],
                  },
                })}
              >
                <title>{g.src.scorer_name ?? 'Goal'}</title>
              </circle>
            )
          })}
        </svg>

        <div className="shot-map-kde__labels">
          <span className="shot-map-kde__label">{awayTeamAbbrev} · {model.awayN.length} attempts <em>(attacking left)</em></span>
          <span className="shot-map-kde__label shot-map-kde__label--home">{homeTeamAbbrev} · {model.homeN.length} attempts <em>(attacking right)</em></span>
        </div>
        {caption && <p className="shot-map-kde__caption">{caption}</p>}
      </div>
    </ChartPanel>
    {popup && <GoalPopup goal={popup.goal} anchor={popup.anchor} onClose={() => setPopup(null)} />}
    </>
  )
}
