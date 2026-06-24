/**
 * Streak Doctor card (Phase 3.3): a team's last-N run decomposed into goal-scale components.
 * Presentational + embeddable (takes a StreakCard) so the Home page (Phase 6) can render
 * active cards standalone. Shows the verdict (depth 1), a diverging decomposition bar
 * (reuses ComponentStackBar), a sustainability gauge, and an expandable numbers table.
 */
import { useState } from 'react'
import { ChevronDown, Snowflake, Flame, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import ComponentStackBar, { StackSegment } from './ComponentStackBar'
import { StreakCard } from '../../api/types'
import './StreakDoctorCard.css'

export type StreakDoctorVariant = 'full' | 'strip'

interface StreakDoctorCardProps {
  card: StreakCard
  variant?: StreakDoctorVariant   // default 'full' (existing behavior unchanged)
  href?: string                   // strip-only: trailing "see trends ->" link
  className?: string
}

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

/** The dominant driver: the largest-magnitude component aligned with the run's direction. */
function dominantDriver(card: StreakCard) {
  const sign = Math.sign(card.total_deviation) || 1
  const aligned = card.components.filter((c) => Math.sign(c.value) === sign)
  const pool = aligned.length ? aligned : card.components
  return pool.length ? pool.reduce((b, c) => (Math.abs(c.value) > Math.abs(b.value) ? c : b), pool[0]) : null
}

/** Condensed one-line strip for the Overview hero: cold/hot tag + the SAME verdict + driver figure. */
function StreakStrip({ card, href, className }: { card: StreakCard; href?: string; className?: string }) {
  const cold = card.total_deviation < 0
  const driver = dominantDriver(card)
  const unit = driver?.key === 'goaltending' ? 'GSAx' : 'goals'   // matches the full card's depth-3 driver row
  return (
    <div className={`streak-strip streak-strip--${cold ? 'cold' : 'hot'}${className ? ' ' + className : ''}`}>
      <span className="streak-strip__tag">
        {cold ? <Snowflake size={15} /> : <Flame size={15} />}{cold ? 'Cold streak.' : 'Hot streak.'}
      </span>
      <span className="streak-strip__verdict">{card.verdict}</span>
      {driver && (
        <span className="streak-strip__driver">{driver.label} {driver.value >= 0 ? '+' : ''}{driver.value.toFixed(1)} {unit}</span>
      )}
      {href && <Link to={href} className="streak-strip__link">see trends <ArrowRight size={13} /></Link>}
    </div>
  )
}

export default function StreakDoctorCard({ card, variant = 'full', href, className }: StreakDoctorCardProps) {
  if (variant === 'strip') return <StreakStrip card={card} href={href} className={className} />
  return <StreakDoctorFull card={card} />
}

function StreakDoctorFull({ card }: { card: StreakCard }) {
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
