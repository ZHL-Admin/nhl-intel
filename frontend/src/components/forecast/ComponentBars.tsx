import { Tooltip } from '../common'
import { fmtRating } from '../../utils/forecastFormat'

const DOMAIN = 0.8 // symmetric ± domain (goals/game), so all four rows are comparable

const ROWS: { key: string; label: string; tip: string }[] = [
  { key: 'play_5v5', label: '5v5 play', tip: 'Opponent-adjusted even-strength play-driving, goals/game.' },
  { key: 'finishing', label: 'Finishing', tip: '5v5 finishing luck — the least repeatable component; the projection shrinks it.' },
  { key: 'goaltending', label: 'Goaltending', tip: 'Even-strength goals saved above expected, per game.' },
  { key: 'special_teams', label: 'Special teams', tip: 'Non-5v5 goals above expected, per game.' },
]

/** §03 — each base-rating component as a bar diverging from a shared center zero. Status colors:
 * right of the line (green) is above average, left (red) is below. NOT the DESIGN diverging palette. */
export default function ComponentBars({ components }: { components: Record<string, number | null> }) {
  return (
    <div className="cbars">
      <p className="sec__subtitle">Right of the line is above average, left is below.</p>
      <div className="cbars__list">
        {ROWS.map(({ key, label, tip }) => {
          const v = components[key] ?? 0
          const half = Math.min(50, (Math.abs(v) / DOMAIN) * 50)
          const pos = v >= 0
          return (
            <div className="cbar" key={key}>
              <Tooltip content={tip}><span className="cbar__label">{label}</span></Tooltip>
              <span className="cbar__track">
                <span className="cbar__zero" />
                <span
                  className={`cbar__fill ${pos ? 'is-up' : 'is-down'}`}
                  style={pos ? { left: '50%', width: `${half}%` } : { right: '50%', width: `${half}%` }}
                />
              </span>
              <span className={`cbar__val mono ${pos ? 'is-up' : 'is-down'}`}>{fmtRating(v)}</span>
            </div>
          )
        })}
        <div className="cbar cbar--axis" aria-hidden>
          <span className="cbar__label" />
          <span className="cbar__axis">
            <span>{fmtRating(-DOMAIN)}</span><span>0</span><span>{fmtRating(DOMAIN)}</span>
          </span>
          <span className="cbar__val" />
        </div>
      </div>
    </div>
  )
}
