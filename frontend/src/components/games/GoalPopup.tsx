/**
 * GoalPopup (Blueprint items 1 & 5) — the one goal-detail popup, shown on clicking a goal dot in the
 * timeline OR the shot map. Scorer avatar + name, team, time, strength, assists, and score-after.
 * Fixed-positioned at the click, then clamped to stay fully in the viewport. Closes on scrim/Esc.
 */
import { useLayoutEffect, useRef, useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import PlayerAvatar from '../common/PlayerAvatar'
import type { GoalDetail } from '../../api/types'
import './GoalPopup.css'

export interface GoalInfo {
  scorerId?: number | null
  scorerName?: string | null
  teamAbbrev?: string | null
  periodLabel: string
  timeInPeriod?: string | null
  assists?: string[]
  strength?: string | null
  scoreAfter?: string | null
}

/** The single source of GoalInfo — the goals feed with a running away-home score — keyed by
 * scorer + clock so any surface (timeline, shot map) shows the SAME assists and score-after. */
export function buildGoalInfoMap(goals: GoalDetail[], homeAbbrev: string): Map<string, GoalInfo> {
  const map = new Map<string, GoalInfo>()
  let away = 0, home = 0
  for (const g of [...goals].sort((a, b) => a.game_time_seconds - b.game_time_seconds)) {
    if (g.team_abbrev === homeAbbrev) home++; else away++
    const key = `${g.scorer_id}:${g.time_in_period}`
    map.set(key, {
      scorerId: g.scorer_id, scorerName: g.scorer_name, teamAbbrev: g.team_abbrev,
      periodLabel: g.period != null ? (g.period > 3 ? 'OT' : `P${g.period}`) : '',
      timeInPeriod: g.time_in_period, assists: g.assists, strength: g.strength, scoreAfter: `${away}-${home}`,
    })
  }
  return map
}

const MARGIN = 8

export default function GoalPopup({ goal, anchor, onClose }: { goal: GoalInfo; anchor: { x: number; y: number }; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ left: anchor.x, top: anchor.y })

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    // prefer above-right of the click; clamp both axes into the viewport
    let left = anchor.x + 12
    let top = anchor.y - r.height - 12
    if (left + r.width > window.innerWidth - MARGIN) left = anchor.x - r.width - 12
    if (left < MARGIN) left = MARGIN
    if (top < MARGIN) top = anchor.y + 16
    if (top + r.height > window.innerHeight - MARGIN) top = window.innerHeight - r.height - MARGIN
    setPos({ left, top })
  }, [anchor.x, anchor.y])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return createPortal(
    <div className="goal-popup__scrim" onClick={onClose}>
      <div ref={ref} className="goal-popup" style={{ left: pos.left, top: pos.top }} onClick={(e) => e.stopPropagation()} role="dialog">
        <div className="goal-popup__head">
          {goal.scorerId != null && <PlayerAvatar id={goal.scorerId} name={goal.scorerName} team={goal.teamAbbrev ?? undefined} size={40} />}
          <div className="goal-popup__id">
            <span className="goal-popup__name">{goal.scorerName ?? 'Goal'}</span>
            <span className="goal-popup__meta mono">
              {goal.teamAbbrev ?? ''} · {goal.periodLabel}{goal.timeInPeriod ? ` ${goal.timeInPeriod}` : ''}
              {goal.strength && goal.strength !== 'EV' ? ` · ${goal.strength}` : ''}
            </span>
          </div>
          {goal.scoreAfter && <span className="goal-popup__score mono">{goal.scoreAfter}</span>}
        </div>
        {goal.assists && goal.assists.length > 0 && (
          <div className="goal-popup__assists">Assists: {goal.assists.join(', ')}</div>
        )}
      </div>
    </div>,
    document.body,
  )
}
