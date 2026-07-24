import { useEffect, useMemo, useState } from 'react'
import Shell from '../shell/Shell'
import { getValueRankings } from '../../api/rankings'
import { getTalentRankings } from '../../api/assets'
import type { ValueRankingRow, TradeableAsset } from '../../api/types'
import { getTeamName, getTeamLogoUrl, getPlayerHeadshotUrl } from '../../utils/teams'
import { fmtDollars, fmtStamp } from './ratingsFormat'
import './ratings.css'

/**
 * Player Ratings (§3.4 sibling, /ratings/players). Ranked by WAR (the RAPM-based
 * GAR/WAR leaderboard, /rankings/value) — NOT contract surplus. Merges
 * /rankings/talent by player_id for age + value + surplus as secondary columns.
 * Both dormant endpoints are read as-is; no backend changes.
 */
type Pos = 'ALL' | 'F' | 'D'
type SortKey = 'rank' | 'name' | 'team' | 'pos' | 'age' | 'war' | 'value' | 'surplus'

interface PRow {
  player_id: number
  name: string
  abbr: string
  pos: string
  age: number | null
  war: number
  value: number | null
  surplus: number | null
  rank: number
}

const COLS: { key: SortKey; label: string; cls?: string; tip: string }[] = [
  { key: 'rank', label: 'Rk', cls: 'rk', tip: 'Rank by WAR.' },
  { key: 'name', label: 'Player', cls: 'team', tip: 'Sort by player name.' },
  { key: 'team', label: 'Team', cls: 'team', tip: 'Sort by team.' },
  { key: 'pos', label: 'Pos', cls: 'lft', tip: 'Primary position.' },
  { key: 'age', label: 'Age', tip: 'Age this season.' },
  { key: 'war', label: 'WAR', tip: 'Wins Above Replacement — total on-ice value in wins from the RAPM-based GAR model (reliability-shrunk). The ranking metric.' },
  { key: 'value', label: 'Value', tip: 'Projected on-ice value in dollars (the talent axis). Secondary; not the ranking.' },
  { key: 'surplus', label: 'Surplus', tip: 'Contract surplus — projected value minus cap cost. Orange positive, blue negative. Secondary; not the ranking.' },
]

const parseAge = (s?: string | null) => { const m = (s ?? '').match(/(\d+)\s*y/); return m ? Number(m[1]) : null }
const posToken = (p?: string | null) => (p ?? '').split(/[ ·/]/)[0].toUpperCase()
const isD = (p?: string | null) => posToken(p).includes('D')

export default function RatingsPlayers() {
  const [value, setValue] = useState<ValueRankingRow[] | null>(null)
  const [talent, setTalent] = useState<Record<number, TradeableAsset>>({})
  const [pos, setPos] = useState<Pos>('ALL')
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'war', dir: 'desc' })
  const [error, setError] = useState(false)

  useEffect(() => {
    document.title = 'Player Ratings · Rink Theory'
    Promise.all([getValueRankings('skaters', 'ALL', undefined, 100), getTalentRankings('player', 100)])
      .then(([v, t]) => {
        setValue(v)
        const m: Record<number, TradeableAsset> = {}
        for (const a of t) if (a.player_id != null) m[a.player_id] = a
        setTalent(m)
      })
      .catch(() => setError(true))
  }, [])

  // Merge + filter, keeping the endpoint's WAR order; assign the WAR rank here so
  // it stays stable when the display is re-sorted by another column.
  const ranked = useMemo<PRow[]>(() => {
    if (!value) return []
    return value
      .filter((v) => (pos === 'ALL' ? true : pos === 'F' ? !isD(v.position) : isD(v.position)))
      .map((v, i) => {
        const t = talent[v.player_id]
        return {
          player_id: v.player_id,
          name: v.player_name ?? '—',
          abbr: v.team_abbrev ?? '',
          pos: v.position ?? '—',
          age: parseAge(t?.pos_or_slot),
          war: v.assessed_war ?? v.war,
          value: t?.value_dollars ?? null,
          surplus: t?.surplus_dollars ?? null,
          rank: i + 1,
        }
      })
  }, [value, talent, pos])

  const rows = useMemo(() => {
    const r = [...ranked]
    const { key, dir } = sort
    const sign = dir === 'asc' ? 1 : -1
    r.sort((a, b) => {
      if (key === 'name' || key === 'team' || key === 'pos') {
        const av = key === 'team' ? getTeamName(a.abbr) || a.abbr : (a[key] as string)
        const bv = key === 'team' ? getTeamName(b.abbr) || b.abbr : (b[key] as string)
        return sign * av.localeCompare(bv)
      }
      const av = (a[key] as number | null) ?? -Infinity
      const bv = (b[key] as number | null) ?? -Infinity
      return sign * (av - bv)
    })
    return r
  }, [ranked, sort])

  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: key === 'name' || key === 'team' || key === 'pos' || key === 'rank' ? 'asc' : 'desc' }))

  return (
    <Shell>
      <h1 className="rt-pagetitle">Player Ratings</h1>
      <p className="rt-stamp">Updated nightly · Data through {fmtStamp(new Date().toISOString().slice(0, 10))}</p>
      <p className="rt-intro">
        Skaters ranked by WAR — total on-ice value in wins, from the RAPM-based value model. Projected
        dollar value and contract surplus are shown alongside, but the ranking is talent, not the deal.
      </p>

      <div className="rt-posfilter">
        {(['ALL', 'F', 'D'] as Pos[]).map((p) => (
          <button key={p} className={pos === p ? 'is-active' : undefined} onClick={() => setPos(p)}>
            {p === 'ALL' ? 'All' : p === 'F' ? 'Forwards' : 'Defense'}
          </button>
        ))}
      </div>

      {error && <p className="rt-intro">Player ratings are unavailable right now.</p>}

      {value && (
        <div className="rt-tablewrap">
          <table className="rt-rttable">
            <thead>
              <tr>
                {COLS.map((c) => (
                  <th key={c.key} className={c.cls} title={c.tip} onClick={() => onSort(c.key)}
                      aria-sort={sort.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
                    {c.label}
                    {sort.key === c.key && <span className="rt-rt__arrow" aria-hidden>{sort.dir === 'asc' ? '▲' : '▼'}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const surplusClass = r.surplus == null ? '' : r.surplus >= 0 ? 'ahead' : 'behind'
                return (
                  <tr key={r.player_id}>
                    <td className="rk">{r.rank}</td>
                    <td className="team">
                      <span className="rt-player">
                        <img className="rt-player__mug" src={getPlayerHeadshotUrl(r.player_id, r.abbr)} alt="" loading="lazy" />
                        <span className="rt-team__name">{r.name}</span>
                      </span>
                    </td>
                    <td className="team">
                      <span className="rt-team">
                        <img className="rt-team__logo" src={getTeamLogoUrl(r.abbr)} alt="" loading="lazy" />
                        <span className="rt-team__name">{getTeamName(r.abbr) || r.abbr || '—'}</span>
                      </span>
                    </td>
                    <td className="lft">{r.pos}</td>
                    <td className="comp">{r.age ?? '—'}</td>
                    <td className="rating">{r.war.toFixed(1)}</td>
                    <td className="comp">{fmtDollars(r.value)}</td>
                    <td className={`luck ${surplusClass}`}>
                      {r.surplus == null ? '—' : (r.surplus >= 0 ? '+' : '−') + fmtDollars(Math.abs(r.surplus))}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="rt-tablenote">
        Click any column to sort; hover a header for what it measures. Ranked by WAR; value and surplus
        are shown from /rankings/talent + /rankings/surplus, read as-is.
      </p>
    </Shell>
  )
}
