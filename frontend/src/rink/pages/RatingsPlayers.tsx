import { useEffect, useMemo, useState } from 'react'
import Shell from '../shell/Shell'
import { getTalentRankings, getSurplusRankings } from '../../api/assets'
import type { TradeableAsset } from '../../api/types'
import { getTeamColor, getTeamName } from '../../utils/teams'
import { fmtDollars, fmtStamp } from './ratingsFormat'
import './ratings.css'

/**
 * Player Ratings (§3.4 sibling, /ratings/players). Same editorial treatment as
 * the team table. Columns: RK, PLAYER, TEAM (dot), POS, VALUE, CONTRACT SURPLUS.
 *
 * HARD CONSTRAINT (owner): backed ENTIRELY by the existing dormant endpoints
 * /rankings/talent (VALUE, and the value-ordered base) + /rankings/surplus
 * (CONTRACT SURPLUS), read exactly as they respond today. No backend changes;
 * any unsupported column would be cut, not patched. (Every column is supported.)
 */
type Pos = 'ALL' | 'F' | 'D'
// pos_or_slot is a composite the endpoint returns as-is, e.g. "LW · 26y · RFA"
// or "RD/LD · 21y". Parse the leading position token to classify F / D / G.
const posToken = (p?: string | null) => (p ?? '').split(/[ ·/]/)[0].toUpperCase()
const isG = (p?: string | null) => posToken(p) === 'G'
const isD = (p?: string | null) => posToken(p).includes('D')
const isF = (p?: string | null) => posToken(p) !== '' && !isD(p) && !isG(p)

export default function RatingsPlayers() {
  const [talent, setTalent] = useState<TradeableAsset[] | null>(null)
  const [surplusMap, setSurplusMap] = useState<Record<string, number | null>>({})
  const [pos, setPos] = useState<Pos>('ALL')
  const [error, setError] = useState(false)

  useEffect(() => {
    document.title = 'Player Ratings · Rink Theory'
    Promise.all([getTalentRankings('player', 100), getSurplusRankings('surplus', 100)])
      .then(([t, s]) => {
        setTalent(t)
        const m: Record<string, number | null> = {}
        for (const a of s) m[a.asset_id] = a.surplus_dollars ?? null
        setSurplusMap(m)
      })
      .catch(() => setError(true))
  }, [])

  const rows = useMemo(() => {
    if (!talent) return []
    const filtered = talent.filter((a) =>
      pos === 'ALL' ? true : pos === 'F' ? isF(a.pos_or_slot) : isD(a.pos_or_slot))
    return filtered.map((a) => ({
      ...a,
      // surplus from the /surplus response; fall back to the (unmodified) surplus
      // field the talent row already carries when a player isn't in that top list.
      surplus: surplusMap[a.asset_id] ?? a.surplus_dollars ?? null,
    }))
  }, [talent, surplusMap, pos])

  return (
    <Shell>
      <h1 className="rt-pagetitle">Player Ratings</h1>
      <p className="rt-stamp">Updated nightly · Data through {fmtStamp(new Date().toISOString().slice(0, 10))}</p>
      <p className="rt-intro">
        Skaters by projected on-ice value, with the contract surplus each one returns against his cap hit.
        Value ranks the player; surplus ranks the deal.
      </p>

      <div className="rt-posfilter">
        {(['ALL', 'F', 'D'] as Pos[]).map((p) => (
          <button key={p} className={pos === p ? 'is-active' : undefined} onClick={() => setPos(p)}>
            {p === 'ALL' ? 'All' : p === 'F' ? 'Forwards' : 'Defense'}
          </button>
        ))}
      </div>

      {error && <p className="rt-intro">Player ratings are unavailable right now.</p>}

      {talent && (
        <div className="rt-tablewrap">
        <table className="rt-rttable">
          <thead>
            <tr>
              <th className="rk">Rk</th>
              <th className="team">Player</th>
              <th className="team">Team</th>
              <th>Pos</th>
              <th>Value</th>
              <th>Contract Surplus</th>
              <th className="pad" />
            </tr>
          </thead>
          <tbody>
            {rows.map((a, i) => {
              const abbr = a.org_team ?? ''
              const surplusClass = a.surplus == null ? '' : a.surplus >= 0 ? 'ahead' : 'behind'
              return (
                <tr key={a.asset_id}>
                  <td className="rk">{i + 1}</td>
                  <td className="team"><span className="rt-team__name">{a.label}</span></td>
                  <td className="team">
                    <span className="rt-team">
                      <span className="rt-team__dot" style={{ background: getTeamColor(abbr) }} />
                      <span className="rt-team__name">{getTeamName(abbr) || abbr || '—'}</span>
                    </span>
                  </td>
                  <td className="comp">{a.pos_or_slot ?? '—'}</td>
                  <td className="rating">{fmtDollars(a.value_dollars)}</td>
                  <td className={`luck ${surplusClass}`}>
                    {a.surplus == null ? '—' : (a.surplus >= 0 ? '+' : '−') + fmtDollars(Math.abs(a.surplus))}
                  </td>
                  <td className="pad" />
                </tr>
              )
            })}
          </tbody>
        </table>
        </div>
      )}
      <p className="rt-tablenote">
        Value = projected on-ice dollars. Surplus = value minus cap cost; orange positive, blue negative.
        Source: /rankings/talent + /rankings/surplus, read as-is.
      </p>
    </Shell>
  )
}
