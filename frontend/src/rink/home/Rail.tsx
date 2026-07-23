import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getRatings, getOffseasonBoard,
  type RatingsPayload, type TeamRating, type OffseasonRow,
} from '../../api/rankings'
import { getSurplusRankings } from '../../api/assets'
import type { TradeableAsset } from '../../api/types'
import { getTeamColor, getTeamName } from '../../utils/teams'
import { fmtSigned, fmtStamp, fmtDollars } from '../pages/ratingsFormat'
import './rail.css'

const TOOLS = [
  { to: '/tools/trade-ledger', name: 'Trade Ledger' },
  { to: '/tools/draft-value', name: 'Draft Value' },
  { to: '/tools/lineup-lab', name: 'Lineup Lab' },
  { to: '/tools/contract-grader', name: 'Contract Grader' },
]

// Seasonal switch (§3.1 amended): offseason when the ratings data is more than 30
// days stale (no games recently), in-season otherwise. Deterministic, derived
// from the data — no config flag.
const OFFSEASON_DAYS = 30
function isOffseason(dataThrough: string | null): boolean {
  if (!dataThrough) return false
  const dt = new Date(dataThrough + 'T00:00:00').getTime()
  return (Date.now() - dt) / 86_400_000 > OFFSEASON_DAYS
}
// Dev-only override to capture either mode (?rail=inseason | ?rail=offseason).
function devForcedMode(): 'in-season' | 'offseason' | null {
  if (!import.meta.env.DEV) return null
  const v = new URLSearchParams(window.location.search).get('rail')
  return v === 'inseason' ? 'in-season' : v === 'offseason' ? 'offseason' : null
}

const teamName = (t: { team_abbrev: string | null }) => getTeamName(t.team_abbrev ?? '') || t.team_abbrev

/** IN-SEASON: deterministic LUCK WATCH from luckiest/unluckiest teams. */
function luckWatch(teams: TeamRating[]) {
  const withLuck = teams.filter((t) => t.luck != null) as (TeamRating & { luck: number })[]
  if (!withLuck.length) return null
  const lucky = withLuck.reduce((a, b) => (b.luck > a.luck ? b : a))
  const unlucky = withLuck.reduce((a, b) => (b.luck < a.luck ? b : a))
  return (
    <>
      <span className="ahead">{teamName(lucky)}</span> has banked{' '}
      <span className="ahead">{lucky.luck.toFixed(1)}</span> more points than it deserved — the league’s
      biggest cushion. <span className="behind">{teamName(unlucky)}</span> sits{' '}
      <span className="behind">{Math.abs(unlucky.luck).toFixed(1)}</span> short, the steepest shortfall.
    </>
  )
}

/** OFFSEASON: deterministic CONTRACT WATCH from the best/worst surplus deals. */
function contractWatch(best?: TradeableAsset, worst?: TradeableAsset) {
  if (!best && !worst) return null
  return (
    <>
      {best && <><span className="ahead">{best.label}</span>’s deal is the league’s best value at{' '}
        <span className="ahead">+{fmtDollars(best.surplus_dollars)}</span>. </>}
      {worst && <><span className="behind">{worst.label}</span>’s is the worst at{' '}
        <span className="behind">−{fmtDollars(Math.abs(worst.surplus_dollars ?? 0))}</span>.</>}
    </>
  )
}

/** A ratings-style mini-table card: rank · dot+abbrev · mono number. */
function MiniBoard({ header, rows, footer }: {
  header: string
  rows: { key: string | number; rank: number; abbr: string; value: number }[]
  footer?: { to: string; label: string }
}) {
  return (
    <div className="rt-railcard">
      <div className="rt-railcard__hd">{header}</div>
      {rows.map((r) => (
        <div className="rt-railrow" key={r.key}>
          <span className="rt-railrow__rk">{r.rank}</span>
          <span className="rt-railrow__tm">
            <span className="rt-railrow__dot" style={{ background: getTeamColor(r.abbr) }} />
            {r.abbr}
          </span>
          <span className="rt-railrow__rt">{fmtSigned(r.value)}</span>
        </div>
      ))}
      {footer && <Link className="rt-raillink" to={footer.to}>{footer.label}</Link>}
    </div>
  )
}

/** Home right rail — seasonal (§3.1 amended). Both modes read existing endpoints as-is. */
export default function Rail() {
  const [ratings, setRatings] = useState<RatingsPayload | null>(null)
  const [offseason, setOffseason] = useState<OffseasonRow[] | null>(null)
  const [contracts, setContracts] = useState<{ best?: TradeableAsset; worst?: TradeableAsset }>({})

  useEffect(() => { getRatings().then(setRatings).catch(() => {}) }, [])

  const mode: 'in-season' | 'offseason' | null =
    devForcedMode() ?? (ratings ? (isOffseason(ratings.data_through) ? 'offseason' : 'in-season') : null)

  useEffect(() => {
    if (mode !== 'offseason') return
    getOffseasonBoard().then(setOffseason).catch(() => {})
    Promise.all([getSurplusRankings('surplus', 5), getSurplusRankings('overpaid', 5)])
      .then(([b, w]) => setContracts({ best: b[0], worst: w[0] }))
      .catch(() => {})
  }, [mode])

  return (
    <aside className="rt-rail">
      {mode === 'offseason' ? (
        <MiniBoard
          header="Projected 2026-27"
          rows={(offseason ?? [])
            .slice()
            .sort((a, b) => b.projected_rating - a.projected_rating)
            .slice(0, 5)
            .map((t, i) => ({ key: t.team_id, rank: i + 1, abbr: t.team_abbrev ?? '', value: t.projected_rating }))}
        />
      ) : (
        <MiniBoard
          header={`Power Ratings${ratings?.data_through ? ` · ${fmtStamp(ratings.data_through)}` : ''}`}
          rows={(ratings?.teams ?? [])
            .slice(0, 5)
            .map((t) => ({ key: t.team_id, rank: t.rank, abbr: t.team_abbrev ?? '', value: t.rating }))}
          footer={{ to: '/ratings', label: 'Full ratings →' }}
        />
      )}

      <div className="rt-railcard">
        <div className="rt-railcard__hd">{mode === 'offseason' ? 'Contract Watch' : 'Luck Watch'}</div>
        <p className="rt-luckwatch">
          {mode === 'offseason'
            ? (offseason && (contracts.best || contracts.worst) ? contractWatch(contracts.best, contracts.worst) : '…')
            : (ratings ? luckWatch(ratings.teams) : '…')}
        </p>
        <Link className="rt-raillink" to={mode === 'offseason' ? '/ratings/players' : '/ratings'}>
          {mode === 'offseason' ? 'See the deals →' : 'See the gaps →'}
        </Link>
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
