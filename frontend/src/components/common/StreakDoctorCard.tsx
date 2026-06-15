/**
 * Streak Doctor card (Phase 3.3): a team's last-N run decomposed into goal-scale components.
 * Presentational + embeddable (takes a StreakCard) so the Home page (Phase 6) can render
 * active cards standalone. Shows the verdict (depth 1), a diverging decomposition bar
 * (reuses ComponentStackBar), a sustainability gauge, and an expandable numbers table.
 */
import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import ComponentStackBar, { StackSegment } from './ComponentStackBar'
import { StreakCard } from '../../api/types'
import './StreakDoctorCard.css'

const COLORS: Record<string, string> = {
  shooting_luck: '#f59e0b',
  goaltending: '#a855f7',
  special_teams: '#06b6d4',
  schedule: '#64748b',
  play_change: '#22c55e',
}

function sustainabilityTone(s: number): string {
  if (s >= 60) return 'streak-gauge--good'
  if (s >= 35) return 'streak-gauge--mid'
  return 'streak-gauge--bad'
}

export default function StreakDoctorCard({ card }: { card: StreakCard }) {
  const [open, setOpen] = useState(false)
  const segments: StackSegment[] = card.components.map((c) => ({
    key: c.key, label: c.label, value: c.value, color: COLORS[c.key] ?? '#888',
  }))
  let posSum = 0, negSum = 0
  for (const c of card.components) (c.value >= 0 ? (posSum += c.value) : (negSum += c.value))
  const m = Math.max(0.5, posSum, Math.abs(negSum))
  const domain: [number, number] = [-m, m]

  return (
    <div className="streak-card">
      <div className="streak-card__top">
        <span className={`streak-card__badge streak-card__badge--${card.run_word}`}>
          {card.window_games}-game {card.run_word}
        </span>
        {card.is_notable && <span className="streak-card__notable">Notable</span>}
      </div>

      <p className="streak-card__verdict">{card.verdict}</p>

      <ComponentStackBar segments={segments} total={card.total_deviation} domain={domain} height={26} />
      <div className="streak-card__legend">
        {card.components.map((c) => (
          <span key={c.key} className="streak-card__legend-item">
            <span className="streak-card__swatch" style={{ background: COLORS[c.key] ?? '#888' }} />
            {c.label}
          </span>
        ))}
      </div>

      <div className="streak-card__gauge-row">
        <span className="streak-card__gauge-label">Sustainability</span>
        <span className="streak-card__gauge-track">
          <span className={`streak-card__gauge-fill ${sustainabilityTone(card.sustainability)}`}
                style={{ width: `${card.sustainability}%` }} />
        </span>
        <span className="streak-card__gauge-val">{card.sustainability}/100</span>
      </div>

      <button className="streak-card__toggle" onClick={() => setOpen(!open)}>
        <ChevronDown size={14} className={open ? 'streak-card__chev streak-card__chev--open' : 'streak-card__chev'} />
        {open ? 'Hide' : 'Show'} the numbers
      </button>
      {open && (
        <table className="streak-card__table">
          <thead>
            <tr><th>Component</th><th>Goals</th><th>Share of run</th></tr>
          </thead>
          <tbody>
            {card.components.map((c) => (
              <tr key={c.key}>
                <td>{c.label}</td>
                <td className="streak-card__num">{(c.value >= 0 ? '+' : '') + c.value.toFixed(1)}</td>
                <td className="streak-card__num">{Math.round(c.share * 100)}%</td>
              </tr>
            ))}
            <tr className="streak-card__total-row">
              <td>Total deviation</td>
              <td className="streak-card__num">{(card.total_deviation >= 0 ? '+' : '') + card.total_deviation.toFixed(1)}</td>
              <td className="streak-card__num">{card.games} GP</td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  )
}
