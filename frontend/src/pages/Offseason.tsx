import { useEffect, useMemo, useState } from 'react'
import { PageLayout, PageHeader, Select, SkeletonLoader, Tooltip } from '../components/common'
import { getOffseasonBoard, getTeamOffseason } from '../api/offseason'
import { RosterForecastRow, OffseasonTeamDetail, RosterMove } from '../api/types'
import { getTeamName } from '../utils/teams'
import './Offseason.css'

const fmt = (v: number | null | undefined, d = 2) => (v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(d))
const abbrev = (r: RosterForecastRow) => r.team_abbrev || String(r.team_id)

/** A signed value with its band, rendered as a centered bar so overlapping bands read at a glance. */
function BandBar({ value, low, high, domain, tint }: {
  value: number; low: number; high: number; domain: [number, number]; tint: string
}) {
  const [lo, hi] = domain
  const span = hi - lo || 1
  const pct = (v: number) => Math.max(0, Math.min(100, ((v - lo) / span) * 100))
  const zero = pct(0)
  return (
    <span className="osb">
      <span className="osb__axis" style={{ left: `${zero}%` }} />
      <span className="osb__band" style={{ left: `${pct(low)}%`, width: `${Math.max(0.5, pct(high) - pct(low))}%`, background: tint }} />
      <span className="osb__mark" style={{ left: `${pct(value)}%` }} />
    </span>
  )
}

function Metric({ label, tip, children }: { label: string; tip: string; children: React.ReactNode }) {
  return (
    <span className="os-metric">
      <Tooltip content={tip}><span className="os-metric__label">{label}</span></Tooltip>
      <span className="os-metric__val mono">{children}</span>
    </span>
  )
}

/** Before/after rating components, each a labeled bar with the projected-rating band whisker. */
function ComponentsReadout({ d }: { d: OffseasonTeamDetail }) {
  const c = d.base_components
  const rows: [string, number | null | undefined, string][] = [
    ['5v5 play', c.play_5v5, 'Opponent-adjusted even-strength play-driving (goals/game).'],
    ['Finishing', c.finishing, '5v5 finishing luck — the least repeatable component; the projection shrinks it.'],
    ['Goaltending', c.goaltending, 'Even-strength goals saved above expected per game.'],
    ['Special teams', c.special_teams, 'Non-5v5 goals above expected per game.'],
  ]
  const mag = Math.max(0.4, ...rows.map(([, v]) => Math.abs(v ?? 0)))
  return (
    <div className="os-components">
      <div className="os-components__head">Base rating, by component <span className="mono">{fmt(d.forecast.base_rating)}</span></div>
      {rows.map(([label, v, tip]) => (
        <div className="os-components__row" key={label}>
          <Tooltip content={tip}><span className="os-components__label">{label}</span></Tooltip>
          <span className="os-components__bar"><BandBar value={v ?? 0} low={v ?? 0} high={v ?? 0} domain={[-mag, mag]} tint="var(--color-accent-subtle)" /></span>
          <span className="os-components__v mono">{fmt(v)}</span>
        </div>
      ))}
    </div>
  )
}

function MoveLedger({ moves }: { moves: RosterMove[] }) {
  const drivers = useMemo(
    () => moves.filter((m) => m.move_type === 'arrival' || m.move_type === 'departure')
      .sort((a, b) => Math.abs(b.delta_contribution) - Math.abs(a.delta_contribution)),
    [moves])
  if (!drivers.length) return null
  const mag = Math.max(1, ...drivers.map((m) => Math.abs(m.projected_war) + m.war_sd))
  return (
    <div className="os-ledger">
      <div className="os-ledger__head">Move ledger <span className="os-ledger__sub">projected WAR, with band</span></div>
      {drivers.map((m, i) => {
        const tint = m.is_goalie ? 'var(--color-data-neutral)' : (m.move_type === 'arrival' ? 'var(--color-data-positive)' : 'var(--color-data-negative)')
        return (
          <div className={`os-move os-move--${m.move_type}`} key={`${m.player_id}-${i}`}>
            <span className="os-move__type">{m.move_type === 'arrival' ? 'IN' : 'OUT'}</span>
            <span className="os-move__name">{m.name || `#${m.player_id}`}{m.no_track_record && <span className="os-move__nt" title="No NHL track record — replacement level, wide band"> · no track record</span>}</span>
            <span className="os-move__pos mono">{m.position}</span>
            <span className="os-move__bar"><BandBar value={m.projected_war} low={m.projected_war - m.war_sd} high={m.projected_war + m.war_sd} domain={[-mag, mag]} tint={tint} /></span>
            <span className="os-move__val mono">{fmt(m.delta_contribution, 1)}</span>
          </div>
        )
      })}
    </div>
  )
}

function ProjectedLineup({ d }: { d: OffseasonTeamDetail }) {
  const slots = d.projected_lineup
  if (!slots.length) return null
  return (
    <div className="os-lineup">
      <div className="os-lineup__head">Projected lineup <span className="os-ledger__sub">each slot's value + band</span></div>
      <div className="os-lineup__grid">
        {slots.map((s) => (
          <div className="os-lineup__slot" key={s.slot}>
            <span className="os-lineup__pos mono">{s.slot}</span>
            <span className="os-lineup__name">{s.name || `#${s.player_id}`}</span>
            <span className="os-lineup__war mono">{fmt(s.projected_war, 1)}<span className="os-lineup__sd"> ±{s.war_sd.toFixed(1)}</span></span>
          </div>
        ))}
      </div>
    </div>
  )
}

function TeamDetail({ teamId }: { teamId: number }) {
  const [d, setD] = useState<OffseasonTeamDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let on = true
    setD(null); setErr(null)
    getTeamOffseason(teamId).then((r) => on && setD(r)).catch(() => on && setErr('No forecast for this team.'))
    return () => { on = false }
  }, [teamId])

  if (err) return <p className="os-msg">{err}</p>
  if (!d) return <div className="os-detail"><SkeletonLoader height={120} /><SkeletonLoader height={200} /></div>
  const f = d.forecast
  return (
    <div className="os-detail">
      <div className={`os-verdict${f.negligible ? ' os-verdict--quiet' : ''}`}>
        <p className="os-verdict__line">{d.verdict}</p>
        <div className="os-verdict__nums">
          <Metric label="Projected" tip="Projected next-season rating (goals/game), with its band.">
            {fmt(f.projected_rating)}<span className="os-band"> [{fmt(f.band_low)}, {fmt(f.band_high)}]</span>
          </Metric>
          <Metric label="Change" tip="Projected change from last season's rating, from the moves made.">{fmt(f.delta)}</Metric>
          <Metric label="Rank" tip="Projected league rank (1 = best by projected rating).">
            {f.base_rank ?? '—'} → {f.projected_rank ?? '—'}
          </Metric>
          <Metric label="Moves" tip="Lineup-relevant arrivals + departures (depth churn excluded).">{f.n_moves}</Metric>
        </div>
      </div>
      {d.reasons.length > 0 && (
        <ul className="os-reasons">{d.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
      )}
      {d.style_note && <p className="os-style">{d.style_note}</p>}
      <div className="os-cols">
        <ComponentsReadout d={d} />
        <MoveLedger moves={d.moves} />
      </div>
      <ProjectedLineup d={d} />
      <p className="os-limits">{d.limitations}</p>
    </div>
  )
}

export default function Offseason() {
  const [board, setBoard] = useState<RosterForecastRow[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [selected, setSelected] = useState<number | null>(null)

  useEffect(() => {
    getOffseasonBoard()
      .then((rows) => { setBoard(rows); if (rows.length) setSelected(rows[0].team_id) })
      .catch(() => setErr('The offseason forecast is not available yet.'))
  }, [])

  const domain = useMemo<[number, number]>(() => {
    if (!board?.length) return [-1, 1]
    const m = Math.max(0.5, ...board.map((r) => Math.max(Math.abs(r.band_low), Math.abs(r.band_high))))
    return [-m, m]
  }, [board])

  const teamOptions = useMemo(
    () => (board ?? []).map((r) => ({ value: String(r.team_id), label: `${abbrev(r)} — ${getTeamName(abbrev(r))}` })),
    [board])

  return (
    <PageLayout>
      <div className="offseason">
        <PageHeader title="Offseason Forecast"
          subtitle="How good each team projects next season from the moves it has made — with honest uncertainty.">
          {board && (
            <div className="offseason__toolbar">
              <span className="offseason__pick-lbl">Team</span>
              <Select ariaLabel="Team" value={String(selected ?? '')} options={teamOptions}
                onChange={(v) => setSelected(Number(v))} />
            </div>
          )}
        </PageHeader>

        {err && <p className="os-msg">{err}</p>}
        {!board && !err && <SkeletonLoader height={320} />}

        {board && (
          <div className="offseason__body">
            <section className="os-board">
              <div className="os-board__head">
                <span>Team</span>
                <span className="os-board__rate">Projected rating &amp; band</span>
                <span className="os-board__rank">Rank</span>
              </div>
              {board.map((r) => (
                <button key={r.team_id} className={`os-board__row${selected === r.team_id ? ' os-board__row--on' : ''}`}
                  onClick={() => setSelected(r.team_id)}>
                  <span className="os-board__team">
                    <span className="os-board__abbr mono">{abbrev(r)}</span>
                    {r.negligible && <span className="os-board__tag" title="No material moves yet">quiet</span>}
                  </span>
                  <span className="os-board__bar">
                    <BandBar value={r.projected_rating} low={r.band_low} high={r.band_high} domain={domain}
                      tint={r.delta >= 0 ? 'var(--color-data-positive)' : 'var(--color-data-negative)'} />
                  </span>
                  <span className="os-board__val mono">{fmt(r.projected_rating)} <span className="os-board__delta">({fmt(r.delta)})</span></span>
                  <span className="os-board__rank mono">{r.projected_rank ?? '—'}</span>
                </button>
              ))}
            </section>
            {selected != null && <TeamDetail teamId={selected} />}
          </div>
        )}
      </div>
    </PageLayout>
  )
}
