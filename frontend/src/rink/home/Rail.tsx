import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getRatings, getOffseasonBoard,
  type RatingsPayload, type TeamRating, type OffseasonRow,
} from '../../api/rankings'
import { getSurplusRankings } from '../../api/assets'
import type { TradeableAsset } from '../../api/types'
import { getTeamName } from '../../utils/teams'
import { fmtSigned, fmtStamp, fmtDollars } from '../pages/ratingsFormat'
import './rail.css'

const TOOLS = [
  { to: '/tools/trade-ledger', name: 'Trade Ledger' },
  { to: '/tools/draft-value', name: 'Draft Pick Value' },
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
// "Jun 17, 2026" -> "Jun 17" for the compact rail header stamp.
const shortStamp = (iso: string) => fmtStamp(iso).replace(/,.*$/, '')

/** IN-SEASON: deterministic LUCK WATCH from luckiest/unluckiest teams. */
function luckWatch(teams: TeamRating[]) {
  const withLuck = teams.filter((t) => t.luck != null) as (TeamRating & { luck: number })[]
  if (!withLuck.length) return null
  const lucky = withLuck.reduce((a, b) => (b.luck > a.luck ? b : a))
  const unlucky = withLuck.reduce((a, b) => (b.luck < a.luck ? b : a))
  return (
    <>
      {teamName(lucky)} sits <span className="ahead">{Math.round(lucky.luck)} points above</span> its
      deserved record. {teamName(unlucky)} is <span className="behind">{Math.round(Math.abs(unlucky.luck))} below</span>.
    </>
  )
}

/** OFFSEASON: deterministic CONTRACT WATCH from the best/worst surplus deals. */
function contractWatch(best?: TradeableAsset, worst?: TradeableAsset) {
  if (!best && !worst) return null
  return (
    <>
      {best && <>{best.label}’s deal is the league’s best value at{' '}
        <span className="ahead">+{fmtDollars(best.surplus_dollars)}</span>. </>}
      {worst && <>{worst.label}’s is the worst at{' '}
        <span className="behind">−{fmtDollars(Math.abs(worst.surplus_dollars ?? 0))}</span>.</>}
    </>
  )
}

/** A ratings-style mini-board card: colored top rule, rank · bold abbrev · ink value. */
function MiniBoard({ header, rule, rows, footer }: {
  header: string
  rule: 'orange' | 'blue' | 'ink'
  rows: { key: string | number; rank: number; abbr: string; value: number }[]
  footer?: { to: string; label: string }
}) {
  return (
    <div className={`rt-railcard rt-railcard--${rule}`}>
      <div className="rt-railcard__hd">{header}</div>
      {rows.map((r) => (
        <div className="rt-railrow" key={r.key}>
          <span className="rt-railrow__rk">{r.rank}</span>
          <span className="rt-railrow__tm">{r.abbr}</span>
          <span className="rt-railrow__rt">{fmtSigned(r.value)}</span>
        </div>
      ))}
      {footer && <Link className="rt-raillink" to={footer.to}>{footer.label}</Link>}
    </div>
  )
}

/** Loading / unavailable state for an API-backed card — never an empty shell. */
function NoteCard({ rule, header, phase }: {
  rule: 'orange' | 'blue' | 'ink'
  header: string
  phase: 'loading' | 'error'
}) {
  return (
    <div className={`rt-railcard rt-railcard--${rule}`}>
      <div className="rt-railcard__hd">{header}</div>
      <p className="rt-railnote">{phase === 'error' ? 'Ratings unavailable right now.' : 'Loading…'}</p>
    </div>
  )
}

/** Home right rail — seasonal (§3.1 amended). Both modes read existing endpoints as-is. */
export default function Rail() {
  const [ratings, setRatings] = useState<RatingsPayload | null>(null)
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading')
  const [offseason, setOffseason] = useState<OffseasonRow[] | null>(null)
  const [contracts, setContracts] = useState<{ best?: TradeableAsset; worst?: TradeableAsset }>({})

  useEffect(() => {
    getRatings().then((r) => { setRatings(r); setStatus('ok') }).catch(() => setStatus('error'))
  }, [])

  // Phase drives the two API-backed cards. A forced dev mode wins; otherwise the
  // seasonal switch needs a successful /ratings fetch — until it resolves (or if
  // it fails) we show an explicit loading / unavailable card, never an empty
  // in-season shell. (The toolkit card is static and always renders.)
  const forced = devForcedMode()
  const phase: 'loading' | 'error' | 'in-season' | 'offseason' =
    forced ?? (
      status === 'error' ? 'error'
        : status === 'loading' || !ratings ? 'loading'
          : isOffseason(ratings.data_through) ? 'offseason' : 'in-season'
    )

  useEffect(() => {
    if (phase !== 'offseason') return
    getOffseasonBoard().then(setOffseason).catch(() => {})
    Promise.all([getSurplusRankings('surplus', 5), getSurplusRankings('overpaid', 5)])
      .then(([b, w]) => setContracts({ best: b[0], worst: w[0] }))
      .catch(() => {})
  }, [phase])

  return (
    <aside className="rt-rail">
      {phase === 'offseason' ? (
        <MiniBoard
          header="Projected 2026-27"
          rule="orange"
          rows={(offseason ?? [])
            .slice()
            .sort((a, b) => b.projected_rating - a.projected_rating)
            .slice(0, 5)
            .map((t, i) => ({ key: t.team_id, rank: i + 1, abbr: t.team_abbrev ?? '', value: t.projected_rating }))}
        />
      ) : phase === 'in-season' && ratings ? (
        <MiniBoard
          header={`Power Ratings${ratings.data_through ? ` · ${shortStamp(ratings.data_through)}` : ''}`}
          rule="orange"
          rows={ratings.teams.slice(0, 5)
            .map((t) => ({ key: t.team_id, rank: t.rank, abbr: t.team_abbrev ?? '', value: t.rating }))}
          footer={{ to: '/ratings', label: 'Full ratings →' }}
        />
      ) : (
        <NoteCard rule="orange" header="Power Ratings" phase={phase as 'loading' | 'error'} />
      )}

      {phase === 'in-season' && ratings ? (
        <div className="rt-railcard rt-railcard--blue">
          <div className="rt-railcard__hd">Luck Watch</div>
          <p className="rt-luckwatch">{luckWatch(ratings.teams)}</p>
          <Link className="rt-raillink" to="/ratings">The re-simulated standings →</Link>
        </div>
      ) : phase === 'offseason' ? (
        <div className="rt-railcard rt-railcard--blue">
          <div className="rt-railcard__hd">Contract Watch</div>
          <p className="rt-luckwatch">
            {contracts.best || contracts.worst ? contractWatch(contracts.best, contracts.worst) : '…'}
          </p>
          <Link className="rt-raillink" to="/ratings/players">See the deals →</Link>
        </div>
      ) : (
        <NoteCard rule="blue" header="Luck Watch" phase={phase as 'loading' | 'error'} />
      )}

      <div className="rt-railcard rt-railcard--ink">
        <div className="rt-railcard__hd">From the Toolkit</div>
        <div className="rt-toolkit">
          {TOOLS.map((t) => (
            <Link key={t.to} to={t.to}>{t.name} <span className="arw" aria-hidden>→</span></Link>
          ))}
        </div>
      </div>
    </aside>
  )
}
