import { Fragment, ReactNode } from 'react'
import { Tooltip } from '../common'
import { RosterForecastRow } from '../../api/types'
import { getTeamLogoUrl, getTeamName } from '../../utils/teams'
import {
  fmtPoints, fmtPointsDelta, fmtWar, fmtRank, tierForRank, isQuiet,
} from '../../utils/forecastFormat'

export type OffseasonSortKey = 'rank' | 'points' | 'from_moves' | 'moves' | 'war'
export type SortDir = 'asc' | 'desc'

/** Default sort direction for a column when it is first selected (07 v3 players-board rule). */
export const DEFAULT_DIR: Record<OffseasonSortKey, SortDir> = {
  rank: 'asc', points: 'desc', from_moves: 'desc', moves: 'desc', war: 'desc',
}

const ACCESS: Record<OffseasonSortKey, (r: RosterForecastRow) => number> = {
  rank: (r) => r.projected_rank ?? 99,
  points: (r) => r.projected_points ?? r.projected_rating,
  from_moves: (r) => r.points_delta ?? r.delta,
  moves: (r) => r.n_moves,
  war: (r) => r.net_delta_war,
}

/** Sign class for a signed, colored value; near-zero stays secondary. */
const signClass = (v: number, eps = 0.5) => (Math.abs(v) < eps ? 'is-flat' : v > 0 ? 'is-up' : 'is-down')

/** Last-season rank color follows the team-rank rule (contender blue / rebuild caution / middle muted). */
const rankTierClass = (rank: number | null | undefined) => {
  const t = tierForRank(rank)
  return t === 'Contender' ? 'is-good' : t === 'Rebuild' ? 'is-warn' : 'is-mid'
}

function SortHead({ label, col, sortKey, sortDir, onSort, num, tip, className }: {
  label: string; col: OffseasonSortKey; sortKey: OffseasonSortKey; sortDir: SortDir
  onSort: (k: OffseasonSortKey) => void; num?: boolean; tip?: string; className?: string
}) {
  const active = sortKey === col
  const inner = (
    <button type="button" className={`olt__sort${active ? ' is-active' : ''}`} onClick={() => onSort(col)}
      aria-label={`Sort by ${label}`}>
      {label}
      {active && <span className="olt__arrow" aria-hidden>{sortDir === 'asc' ? '▲' : '▼'}</span>}
    </button>
  )
  return (
    <th className={`${num ? 'num' : ''}${className ? ` ${className}` : ''}`}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      {tip ? <span className="olt__th-tip"><Tooltip content={tip}>{inner}</Tooltip></span> : inner}
    </th>
  )
}

/**
 * §1 — the offseason league table (07 v3 players-board rules): sortable columns, emphasis follows the
 * sort, all 32 rows with a 16-row cap and Show all. Each team row expands one dossier at a time; the
 * expanded row carries the blue left edge (aria-selected) and mounts the dossier full width beneath it.
 */
export default function OffseasonLeagueTable({
  rows, sortKey, sortDir, onSort, expandedTeamId, onToggle, showAll, onShowAll, dossier,
}: {
  rows: RosterForecastRow[]
  sortKey: OffseasonSortKey
  sortDir: SortDir
  onSort: (k: OffseasonSortKey) => void
  expandedTeamId: number | null
  onToggle: (teamId: number) => void
  showAll: boolean
  onShowAll: () => void
  /** Render prop for the expanded team's dossier (page owns the detail fetch). */
  dossier: (row: RosterForecastRow) => ReactNode
}) {
  const sorted = [...rows].sort((a, b) => {
    const d = ACCESS[sortKey](a) - ACCESS[sortKey](b)
    return sortDir === 'asc' ? d : -d
  })
  const visible = showAll ? sorted : sorted.slice(0, 16)
  const hidden = sorted.length - visible.length

  const em = (col: OffseasonSortKey) => (sortKey === col ? ' is-sorted' : '')

  return (
    <div className="olt">
      <table className="gamesheet olt__table">
        <thead>
          <tr>
            <th className="num olt__rankh" aria-hidden>#</th>
            <th>Team</th>
            <SortHead label="Proj points" col="points" sortKey={sortKey} sortDir={sortDir} onSort={onSort} num
              tip="Projected next-season standings points over 82 games — a calibrated transform of the team rating, carried with its 80% band." />
            <SortHead label="From moves" col="from_moves" sortKey={sortKey} sortDir={sortDir} onSort={onSort} num
              tip="Standings-points shift from this offseason's moves alone, vs last season's roster." />
            <SortHead label="Moves" col="moves" sortKey={sortKey} sortDir={sortDir} onSort={onSort} num
              className="olt__hide-sm" tip="Lineup-relevant arrivals and departures logged (depth churn excluded)." />
            <SortHead label="Net WAR" col="war" sortKey={sortKey} sortDir={sortDir} onSort={onSort} num
              className="olt__hide-sm" tip="Sum of every logged move's projected-WAR effect." />
            <th className="num" aria-sort="none">
              <span className="olt__th-tip">
                <Tooltip content="Cap space after projected RFA awards and league-minimum fills.">
                  <span className="olt__nosort">Eff. space</span>
                </Tooltip>
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {visible.map((r) => {
            const open = expandedTeamId === r.team_id
            const quiet = isQuiet({ n_moves: r.n_moves, delta: r.delta, negligible: r.negligible })
            const fromMoves = r.points_delta ?? r.delta
            const usePoints = r.projected_points != null
            return (
              <Fragment key={r.team_id}>
                <tr aria-selected={open} className="olt__row"
                  role="button" tabIndex={0} onClick={() => onToggle(r.team_id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle(r.team_id) } }}>
                  <td className="num olt__rank">{fmtRank(r.projected_rank).replace('#', '')}</td>
                  <td>
                    <span className="olt__team">
                      <img className="olt__logo" src={getTeamLogoUrl(r.team_abbrev ?? '')} alt="" aria-hidden
                        onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
                      <span className="olt__idtext">
                        <span className="olt__name">
                          {getTeamName(r.team_abbrev ?? '')}
                          {quiet && <span className="olt__quiet">quiet</span>}
                        </span>
                        <span className="olt__meta">
                          <span className={rankTierClass(r.base_rank)}>{fmtRank(r.base_rank)}</span> last season
                        </span>
                      </span>
                    </span>
                  </td>
                  <td className={`num olt__points${em('points')}`}>
                    {usePoints ? fmtPoints(r.projected_points) : r.projected_rating.toFixed(2)}
                  </td>
                  <td className={`num${em('from_moves')} ${signClass(fromMoves)}`}>
                    {r.points_delta != null ? fmtPointsDelta(r.points_delta) : fmtWar(r.delta)}
                  </td>
                  <td className={`num olt__hide-sm${em('moves')}`}>{r.n_moves}</td>
                  <td className={`num olt__hide-sm${em('war')} ${signClass(r.net_delta_war, 0.05)}`}>{fmtWar(r.net_delta_war)}</td>
                  {/* TODO(data): effective space (cap space after projected RFA awards + min fills) not served
                      by /tools/offseason — column shows an em dash until the forecast row carries it. */}
                  <td className="num olt__space">—</td>
                </tr>
                {open && (
                  <tr className="olt__exp">
                    <td colSpan={7} className="olt__exp-cell">{dossier(r)}</td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>

      {hidden > 0 && (
        <button type="button" className="olt__showall" onClick={onShowAll}>Show all 32 teams ({hidden} more)</button>
      )}

      <div className="olt__captions">
        <p>Effective space is cap space after projected RFA awards and league-minimum fills.</p>
        <p>Updated daily as moves land. Tap a team to open its summer.</p>
      </div>
    </div>
  )
}
