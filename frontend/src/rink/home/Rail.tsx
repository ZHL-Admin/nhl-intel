import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRatings, type RatingsPayload, type TeamRating } from '../../api/rankings'
import { getTeamColor, getTeamName } from '../../utils/teams'
import { fmtSigned, fmtStamp } from '../pages/ratingsFormat'
import './rail.css'

const TOOLS = [
  { to: '/tools/trade-ledger', name: 'Trade Ledger' },
  { to: '/tools/draft-value', name: 'Draft Value' },
  { to: '/tools/lineup-lab', name: 'Lineup Lab' },
  { to: '/tools/contract-grader', name: 'Contract Grader' },
]

/**
 * Deterministic LUCK WATCH sentence (NOT generated prose) — a fixed template
 * filled from the luckiest/unluckiest teams in the deserved-standings data.
 */
function luckWatch(teams: TeamRating[]) {
  const withLuck = teams.filter((t) => t.luck != null) as (TeamRating & { luck: number })[]
  if (withLuck.length === 0) return null
  const lucky = withLuck.reduce((a, b) => (b.luck > a.luck ? b : a))
  const unlucky = withLuck.reduce((a, b) => (b.luck < a.luck ? b : a))
  const name = (t: TeamRating) => getTeamName(t.team_abbrev ?? '') || t.team_abbrev
  return (
    <>
      <span className="ahead">{name(lucky)}</span> has banked{' '}
      <span className="ahead">{lucky.luck.toFixed(1)}</span> more points than it deserved — the league’s
      biggest cushion. <span className="behind">{name(unlucky)}</span> sits{' '}
      <span className="behind">{Math.abs(unlucky.luck).toFixed(1)}</span> short, the steepest shortfall.
    </>
  )
}

/** Home right rail: Power Ratings snapshot · Luck Watch · From the Toolkit. */
export default function Rail() {
  const [data, setData] = useState<RatingsPayload | null>(null)
  useEffect(() => { getRatings().then(setData).catch(() => {}) }, [])

  return (
    <aside className="rt-rail">
      <div className="rt-railcard">
        <div className="rt-railcard__hd">
          Power Ratings{data?.data_through ? ` · ${fmtStamp(data.data_through)}` : ''}
        </div>
        {data?.teams.slice(0, 5).map((t) => (
          <div className="rt-railrow" key={t.team_id}>
            <span className="rt-railrow__rk">{t.rank}</span>
            <span className="rt-railrow__tm">
              <span className="rt-railrow__dot" style={{ background: getTeamColor(t.team_abbrev ?? '') }} />
              {t.team_abbrev}
            </span>
            <span className="rt-railrow__rt">{fmtSigned(t.rating)}</span>
          </div>
        ))}
        <Link className="rt-raillink" to="/ratings">Full ratings →</Link>
      </div>

      <div className="rt-railcard">
        <div className="rt-railcard__hd">Luck Watch</div>
        <p className="rt-luckwatch">
          {data ? luckWatch(data.teams) : '…'}
        </p>
        <Link className="rt-raillink" to="/ratings">See the gaps →</Link>
      </div>

      <div className="rt-railcard">
        <div className="rt-railcard__hd">From the Toolkit</div>
        <div className="rt-toolkit">
          {TOOLS.map((t) => (
            <Link key={t.to} to={t.to}>{t.name} <span aria-hidden>→</span></Link>
          ))}
        </div>
      </div>
    </aside>
  )
}
