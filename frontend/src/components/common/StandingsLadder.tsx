/**
 * StandingsLadder — compact ranked standings rows for a division (or any ranked team list).
 *
 * Shared/reusable: the Team Overview header passes its division slice; the Teams index / standings
 * page can pass a full conference or league. Renders rank · logo · abbrev · points · optional GP,
 * highlights the current team, draws a divider after the playoff cut, and shows an optional
 * context line. Purely presentational — the caller supplies sorted rows and the context copy.
 */
import { Link } from 'react-router-dom'
import './StandingsLadder.css'

export interface StandingsLadderTeam {
  teamId?: number | null
  abbrev: string
  logoUrl: string
  rank: number
  points: number
  gamesPlayed?: number
  isCurrent: boolean
}

interface StandingsLadderProps {
  division: string
  teams: StandingsLadderTeam[]
  /** Draw a thin playoff-cut divider after this rank (e.g. 3 = top three make the division). */
  playoffCutAfterRank?: number
  /** One muted line under the ladder, e.g. "6th in Atlantic, 5 points back of a playoff spot". */
  contextLine?: string
  /** Show the division label above the rows (default true; hide for a bare ladder). */
  showHeader?: boolean
  size?: 'sm' | 'md'
}

export default function StandingsLadder({
  division,
  teams,
  playoffCutAfterRank,
  contextLine,
  showHeader = true,
  size = 'md',
}: StandingsLadderProps) {
  if (!teams.length) return null
  const rows = [...teams].sort((a, b) => a.rank - b.rank)

  return (
    <div className={`standings-ladder standings-ladder--${size}`}>
      {showHeader && <div className="standings-ladder__head">{division}</div>}
      <ol className="standings-ladder__list">
        {rows.map((t) => {
          const showCut =
            playoffCutAfterRank != null && t.rank === playoffCutAfterRank
          const inner = (
            <>
              <span className="standings-ladder__rank mono">{t.rank}</span>
              <img className="standings-ladder__logo" src={t.logoUrl} alt="" loading="lazy" />
              <span className="standings-ladder__abbrev">{t.abbrev}</span>
              <span className="standings-ladder__pts mono">{t.points}</span>
              {t.gamesPlayed != null && (
                <span className="standings-ladder__gp mono">{t.gamesPlayed} GP</span>
              )}
            </>
          )
          return (
            <li
              key={t.abbrev}
              className={`standings-ladder__item${t.isCurrent ? ' is-current' : ''}${
                showCut ? ' is-cut' : ''
              }`}
            >
              {t.teamId != null && !t.isCurrent ? (
                <Link to={`/teams/${t.teamId}`} className="standings-ladder__row">
                  {inner}
                </Link>
              ) : (
                <div className="standings-ladder__row">{inner}</div>
              )}
            </li>
          )
        })}
      </ol>
      {contextLine && <p className="standings-ladder__context">{contextLine}</p>}
    </div>
  )
}
