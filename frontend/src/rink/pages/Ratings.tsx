import { useEffect, useMemo, useState } from 'react'
import Shell from '../shell/Shell'
import { getRatings, type RatingsPayload, type TeamRating } from '../../api/rankings'
import { getTeamName, getTeamLogoUrl } from '../../utils/teams'
import { fmtSigned, fmtLuck, fmtStamp } from './ratingsFormat'
import './ratings.css'

type SortKey = 'rank' | 'team' | 'rating' | 'comp_5v5' | 'comp_finishing' | 'comp_goaltending' | 'comp_special_teams' | 'luck'

// Column defs: sort key, label, cell class, and a hover tooltip explaining the
// metric + how it's measured (component definitions from compute_ratings).
const COLS: { key: SortKey; label: string; cls?: string; tip: string }[] = [
  { key: 'rank', label: 'Rk', cls: 'rk', tip: 'Rank by overall rating.' },
  { key: 'team', label: 'Team', cls: 'team', tip: 'Sort teams alphabetically.' },
  { key: 'rating', label: 'Rating', tip: 'Overall rating — the sum of the four component contributions, on a goals-per-game scale. Higher is better.' },
  { key: 'comp_5v5', label: '5v5 Play', tip: '5-on-5 play: score- and opponent-adjusted 5v5 goal differential per game (the underlying process).' },
  { key: 'comp_finishing', label: 'Finishing', tip: 'Finishing: 5v5 goals scored above expected per game, shrunk by shot volume (shooting talent).' },
  { key: 'comp_goaltending', label: 'Goalie', tip: 'Goaltending: even-strength goals saved above expected per game (save talent).' },
  { key: 'comp_special_teams', label: 'Spec. Teams', tip: 'Special teams: power-play plus penalty-kill goals above expected per game.' },
  { key: 'luck', label: 'Luck', tip: 'Luck: actual standings points minus deserved (re-simulated) points. Orange = results ahead of the play, blue = behind.' },
]

/**
 * Power Ratings (§3.4) — the site's KenPom table. One table, all 32 teams,
 * backed by GET /ratings. Sortable columns, team logos, metric tooltips.
 */
export default function Ratings() {
  const [data, setData] = useState<RatingsPayload | null>(null)
  const [error, setError] = useState(false)
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'rank', dir: 'asc' })

  useEffect(() => {
    document.title = 'Power Ratings · Rink Theory'
    getRatings().then(setData).catch(() => setError(true))
  }, [])

  const rows = useMemo(() => {
    if (!data) return []
    const teams = [...data.teams]
    const { key, dir } = sort
    const sign = dir === 'asc' ? 1 : -1
    teams.sort((a, b) => {
      if (key === 'team') {
        return sign * (getTeamName(a.team_abbrev ?? '') || '').localeCompare(getTeamName(b.team_abbrev ?? '') || '')
      }
      const av = (a[key as keyof TeamRating] as number | null) ?? -Infinity
      const bv = (b[key as keyof TeamRating] as number | null) ?? -Infinity
      return sign * (av - bv)
    })
    return teams
  }, [data, sort])

  // New numeric column → default high-first; team → A→Z; toggle on repeat click.
  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'team' || key === 'rank' ? 'asc' : 'desc' }))

  return (
    <Shell>
      <h1 className="rt-pagetitle">Power Ratings</h1>
      <p className="rt-stamp">
        Updated nightly · {data?.data_through ? `Data through ${fmtStamp(data.data_through)}` : '…'}
      </p>
      <p className="rt-intro">
        One number per team, built from how each club actually plays rather than how its results have
        bounced. The last column is the gap between the real standings and a re-simulated season.
      </p>

      {error && <p className="rt-intro">Ratings are unavailable right now.</p>}

      {data && (
        <div className="rt-tablewrap">
          <table className="rt-rttable">
            <thead>
              <tr>
                {COLS.map((c) => (
                  <th
                    key={c.key}
                    className={c.cls}
                    title={c.tip}
                    onClick={() => onSort(c.key)}
                    aria-sort={sort.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    {c.label}
                    {sort.key === c.key && <span className="rt-rt__arrow" aria-hidden>{sort.dir === 'asc' ? '▲' : '▼'}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => {
                const abbr = t.team_abbrev ?? ''
                const luckClass = t.luck == null ? '' : t.luck >= 0 ? 'ahead' : 'behind'
                return (
                  <tr key={t.team_id}>
                    <td className="rk">{t.rank}</td>
                    <td className="team">
                      <span className="rt-team">
                        <img className="rt-team__logo" src={getTeamLogoUrl(abbr)} alt="" loading="lazy" />
                        <span className="rt-team__name">{getTeamName(abbr) || abbr}</span>
                      </span>
                    </td>
                    <td className="rating">{fmtSigned(t.rating)}</td>
                    <td className="comp">{fmtSigned(t.comp_5v5)}</td>
                    <td className="comp">{fmtSigned(t.comp_finishing)}</td>
                    <td className="comp">{fmtSigned(t.comp_goaltending)}</td>
                    <td className="comp">{fmtSigned(t.comp_special_teams)}</td>
                    <td className={`luck ${luckClass}`}>{fmtLuck(t.luck)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="rt-tablenote">
        Click any column to sort; hover a header for what it measures. Luck in points vs the deserved
        record — orange = results ahead of the play, blue = behind.
      </p>
    </Shell>
  )
}
