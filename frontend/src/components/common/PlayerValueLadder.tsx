/**
 * PlayerValueLadder — a compact ranked slice of players by TOTAL VALUE (WAR), the player-page
 * header counterpart to the Team page's StandingsLadder mini-standings slice.
 *
 * Purely presentational: the caller supplies a window of rows (already ranked + ordered exactly like
 * the Players index), a label, and the unit. The current player's row is tinted in the team color
 * (via --color-team-primary, set by the page); every other row links to that player's page.
 */
import { Link } from 'react-router-dom'
import './PlayerValueLadder.css'

export interface PlayerValueLadderRow {
  rank: number
  playerId: number
  name?: string | null
  value: number
  isCurrent: boolean
}

interface PlayerValueLadderProps {
  label: string
  rows: PlayerValueLadderRow[]
  size?: 'sm' | 'md'
}

const fmt = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}`

export default function PlayerValueLadder({ label, rows, size = 'md' }: PlayerValueLadderProps) {
  if (!rows.length) return null
  const ordered = [...rows].sort((a, b) => a.rank - b.rank)
  return (
    <div className={`value-ladder value-ladder--${size}`}>
      <ol className="value-ladder__list">
        {ordered.map((r) => {
          const inner = (
            <>
              <span className="value-ladder__rank mono">{r.rank}</span>
              <span className="value-ladder__name">{r.name ?? r.playerId}</span>
              <span className="value-ladder__val mono">{fmt(r.value)}</span>
            </>
          )
          return (
            <li key={r.playerId} className={`value-ladder__item${r.isCurrent ? ' is-current' : ''}`}>
              {r.isCurrent ? (
                <div className="value-ladder__row">{inner}</div>
              ) : (
                <Link to={`/players/${r.playerId}`} className="value-ladder__row">{inner}</Link>
              )}
            </li>
          )
        })}
      </ol>
      <p className="value-ladder__foot">{label}</p>
    </div>
  )
}
