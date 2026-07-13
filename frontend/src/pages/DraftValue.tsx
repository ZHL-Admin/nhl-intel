/**
 * Draft Value v2 (doc 16) — the TOOL page: a live pick lookup (figures + mini curve) and the
 * steals-and-busts board. The research (headline curve, bust-rate table, methodology) moved to the
 * Writing essay "What a draft pick is really worth"; this page cross-links to it but carries no
 * research content. Every value is realized 7-year-window pWAR — a wide-band estimate before 2021.
 */
import { Fragment, useEffect, useMemo, useState } from 'react'
import { usePageTitle } from '../hooks/usePageTitle'
import { Link, useSearchParams } from 'react-router-dom'
import { Copy, ArrowRight, ChevronLeft, ChevronRight } from 'lucide-react'
import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  ReferenceDot, Label,
} from 'recharts'
import {
  PageLayout, PageCard, Panel, Tabs, Tooltip, Select, PlayerAvatar, SkeletonLoader,
} from '../components/common'
import type { SelectOption } from '../components/common'
import {
  getPickValueCurve, getDraftBoard, PickValueCurveRow, DraftBoardRow,
} from '../api/draft'
import { getPlayerContract } from '../api/assets'
import './DraftValue.css'

const ESSAY_TO = '/learn/writing/what-a-draft-pick-is-really-worth'
const TRADE_TO = '/studio/trades/build'
const ROUND_SIZE = 32
const STEP_MAX = 224
const pct0 = (v: number) => `${Math.round(v * 100)}%`
const roundOf = (pick: number) => Math.max(1, Math.ceil(pick / ROUND_SIZE))
const signed = (v: number, dp = 1) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(dp)}`

// ---------------------------------------------------------------- curve helpers
/** Nearest curve row to an arbitrary pick (the stepper runs 1–224; the served curve stops earlier). */
function nearestRow(curve: PickValueCurveRow[], pick: number): PickValueCurveRow {
  let best = curve[0]
  let bd = Infinity
  for (const r of curve) {
    const d = Math.abs(r.overall_pick - pick)
    if (d < bd) { bd = d; best = r }
  }
  return best
}
const evAt = (curve: PickValueCurveRow[], pick: number) => nearestRow(curve, pick).ev_mean_smooth

/** Inverse lookup: the slot whose expected value most nearly matches a realized value. */
function inversePick(curve: PickValueCurveRow[], realized: number): number {
  let best = curve[0].overall_pick
  let bd = Infinity
  for (const r of curve) {
    const d = Math.abs(r.ev_mean_smooth - realized)
    if (d < bd) { bd = d; best = r.overall_pick }
  }
  return best
}

/** Equivalence solver: the pair of later slots (a<b) whose expected values sum closest to `target`. */
function equivalentPair(curve: PickValueCurveRow[], pick: number, target: number): [number, number] | null {
  const pool = curve.filter((r) => r.overall_pick > pick && r.ev_mean_smooth > 0.05)
  if (pool.length < 2) return null
  let best: [number, number] | null = null
  let bd = Infinity
  for (let i = 0; i < pool.length; i++) {
    for (let j = i + 1; j < pool.length; j++) {
      const d = Math.abs(pool[i].ev_mean_smooth + pool[j].ev_mean_smooth - target)
      if (d < bd) { bd = d; best = [pool[i].overall_pick, pool[j].overall_pick] }
    }
  }
  // Only surface the line when the pair is a genuine match (within ~0.35 WAR of the slot's value).
  return best && bd <= 0.35 ? best : null
}

/** Verdict-sentence phrase for a realized-into-slot inverse lookup. */
function slotPhrase(n: number): string {
  if (n <= 3) return 'a top-three pick'
  if (n <= 5) return 'a top-five pick'
  if (n <= 10) return 'a top-ten pick'
  if (n <= ROUND_SIZE) return 'a first-round pick'
  if (n <= ROUND_SIZE * 2) return 'a second-round pick'
  if (n <= ROUND_SIZE * 4) return 'a mid-round pick'
  return `pick #${n}`
}

// ---------------------------------------------------------------- mini curve
function selectedDotLabel(row: PickValueCurveRow) {
  return ({ viewBox }: any) => {
    if (!viewBox) return null
    const x = (viewBox.x ?? 0)
    const y = (viewBox.y ?? 0)
    const left = row.overall_pick > 40 // late picks sit near the right edge — flip the label inward
    return (
      <text x={x + (left ? -8 : 8)} y={y - 8} textAnchor={left ? 'end' : 'start'}
        style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fill: 'var(--line-blue)', fontWeight: 600 }}>
        {row.ev_mean_smooth.toFixed(1)} WAR
      </text>
    )
  }
}

function MiniCurve({ curve, selected }: { curve: PickValueCurveRow[]; selected: PickValueCurveRow }) {
  const boundaryPick = [...curve].reverse().find((r) => r.n >= 30)?.overall_pick
    ?? curve[curve.length - 1]?.overall_pick ?? 217
  const data = curve.map((r) => ({
    overall_pick: r.overall_pick,
    bandLo: r.p10_smooth,
    bandSpan: Math.max(0, r.p90_smooth - r.p10_smooth),
    evFit: r.overall_pick <= boundaryPick ? r.ev_mean_smooth : null,
    evExtrap: r.overall_pick >= boundaryPick ? r.ev_mean_smooth : null,
  }))
  const yMax = Math.ceil(Math.max(...curve.map((r) => r.p90_smooth)))
  const tick = { fontSize: 10, fill: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={data} margin={{ top: 16, right: 16, bottom: 14, left: 2 }}>
        <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" />
        {/* log x so the steep top of the draft gets the room it deserves */}
        <XAxis dataKey="overall_pick" type="number" scale="log" domain={[1, 217]} allowDataOverflow
          stroke="var(--color-border)" tick={tick} height={22}
          ticks={[1, 2, 5, 10, 31, 62, 124, 217]} tickFormatter={(v: number) => `${v}`} />
        <YAxis domain={[0, yMax]} stroke="var(--color-border)" width={26} tick={tick}
          tickFormatter={(v: number) => `${v}`} />
        {/* middle-80% band (uncertainty is a data element; kept faint) */}
        <Area dataKey="bandLo" stackId="b" stroke="none" fill="transparent" isAnimationActive={false} />
        <Area dataKey="bandSpan" stackId="b" stroke="none" fill="var(--color-data-1)" fillOpacity={0.12} isAnimationActive={false} />
        {/* fitted region solid; sparse-sample tail dashed (solid = observed, dashed = projected) */}
        <Line type="monotone" dataKey="evFit" stroke="var(--line-blue)" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="evExtrap" stroke="var(--line-blue)" strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls={false} isAnimationActive={false} />
        <ReferenceDot x={selected.overall_pick} y={selected.ev_mean_smooth} r={5}
          fill="var(--line-blue)" stroke="var(--color-bg-surface)" strokeWidth={2}>
          <Label content={selectedDotLabel(selected)} />
        </ReferenceDot>
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ---------------------------------------------------------------- pick lookup
function Figure({ label, value, tip }: { label: string; value: string; tip?: string }) {
  return (
    <div className="dv-fig">
      <div className="dv-fig__label">{tip ? <Tooltip content={tip}>{label}</Tooltip> : label}</div>
      <div className="dv-fig__value mono">{value}</div>
    </div>
  )
}

function PickLookup({ curve }: { curve: PickValueCurveRow[] }) {
  const [params, setParams] = useSearchParams()
  const pick = Math.min(STEP_MAX, Math.max(1, Number(params.get('pick')) || 14))
  const setPick = (p: number) => {
    const next = new URLSearchParams(params)
    next.set('pick', String(Math.min(STEP_MAX, Math.max(1, p))))
    setParams(next, { replace: true })
  }
  const row = nearestRow(curve, pick)
  const round = roundOf(pick)
  const target = row.ev_mean_smooth
  const pair = equivalentPair(curve, pick, target)
  const nextMarker = Math.min(STEP_MAX, round * ROUND_SIZE + 1)
  const dropCost = target - evAt(curve, nextMarker)

  return (
    <Panel className="dv-lookup">
      <div className="dv-lookup__grid">
        <div className="dv-lookup__left">
          {/* stepper */}
          <div className="dv-stepper">
            <button className="dv-stepper__btn" onClick={() => setPick(pick - 1)} disabled={pick <= 1} aria-label="Previous pick">
              <ChevronLeft size={16} />
            </button>
            <div className="dv-stepper__label">
              <span className="dv-stepper__pick mono">Pick #{pick}</span>
              <span className="dv-stepper__round">Round {round}</span>
            </div>
            <button className="dv-stepper__btn" onClick={() => setPick(pick + 1)} disabled={pick >= STEP_MAX} aria-label="Next pick">
              <ChevronRight size={16} />
            </button>
          </div>

          {/* figures — judged-figures anatomy */}
          <div className="dv-figs">
            <Figure label="Expected WAR" value={`${target.toFixed(1)}`}
              tip="Seven-year realized value expected at this slot — a LOESS-smoothed fit across draft history, extrapolated in the sparse late-pick tail." />
            <Figure label="Middle 80%" value={`${row.p10_smooth.toFixed(1)} to ${row.p90_smooth.toFixed(1)}`} />
            <Figure label="Never plays" value={pct0(row.share_never_nhl)} />
            <Figure label="Becomes a regular" value={pct0(row.share_regular)} />
          </div>

          {/* equivalence lines (two max, template fallbacks) */}
          <div className="dv-equiv">
            {pair
              ? <p className="dv-equiv__line">Worth about <span className="mono">#{pair[0]}</span> and <span className="mono">#{pair[1]}</span> combined.</p>
              : <p className="dv-equiv__line">Worth about <span className="mono">{target.toFixed(1)}</span> WAR at this slot.</p>}
            {nextMarker > pick && (
              <p className="dv-equiv__line">The drop to <span className="mono">#{nextMarker}</span> costs <span className="mono dv-neg">{signed(-Math.abs(dropCost))}</span> WAR.</p>
            )}
          </div>

          <p className="dv-lookup__foot">
            This curve prices every draft-pick asset in the <Link to={TRADE_TO}>Trade Builder</Link>.
          </p>
        </div>

        <div className="dv-lookup__chart">
          <MiniCurve curve={curve} selected={row} />
        </div>
      </div>
    </Panel>
  )
}

// ---------------------------------------------------------------- board
/** 64px diverging micro-band on a fixed ±20 domain with a center tick. Blue above slot, red below. */
function VsBand({ value }: { value: number }) {
  const dom = 20
  const clamped = Math.max(-dom, Math.min(dom, value))
  const half = (clamped / dom) * 50 // −50…50, percent from center
  const pos = value >= 0
  return (
    <span className="dv-vsband" aria-hidden>
      <span className="dv-vsband__tick" />
      <span className={`dv-vsband__fill ${pos ? 'is-pos' : 'is-neg'}`}
        style={{ left: pos ? '50%' : `${50 + half}%`, width: `${Math.abs(half)}%` }} />
    </span>
  )
}

/** Slot expectation vs realized on one shared scale, in the expanded row. */
function PairedBand({ expected, realized }: { expected: number; realized: number }) {
  const max = Math.max(expected, realized, 1)
  const w = (v: number) => `${(Math.max(0, v) / max) * 100}%`
  return (
    <div className="dv-paired">
      <div className="dv-paired__row">
        <span className="dv-paired__key">Slot exp.</span>
        <span className="dv-paired__track"><span className="dv-paired__bar is-exp" style={{ width: w(expected) }} /></span>
        <span className="dv-paired__val mono">{expected.toFixed(1)}</span>
      </div>
      <div className="dv-paired__row">
        <span className="dv-paired__key">Realized</span>
        <span className="dv-paired__track"><span className="dv-paired__bar is-real" style={{ width: w(realized) }} /></span>
        <span className="dv-paired__val mono">{realized.toFixed(1)}</span>
      </div>
    </div>
  )
}

function ExpandedRow({ row, curve }: { row: DraftBoardRow; curve: PickValueCurveRow[] }) {
  const invPick = inversePick(curve, row.realized_value)
  const beat = row.value_above_slot >= 0
  const verdict = beat
    ? `Went #${row.overall_pick} in ${row.draft_year}; produced like ${slotPhrase(invPick)}.`
    : `Went #${row.overall_pick} in ${row.draft_year}; produced like ${slotPhrase(invPick)} — below its slot.`
  const isGoalie = row.pos_group === 'G'
  const [hasDeal, setHasDeal] = useState<boolean | null>(null)

  useEffect(() => {
    let active = true
    if (!row.resolved_player_id) { setHasDeal(false); return }
    getPlayerContract(row.resolved_player_id)
      .then((c) => { if (active) setHasDeal(!!(c?.cap_hit && c?.remaining_years && c.contract_status !== 'rfa_projected')) })
      .catch(() => { if (active) setHasDeal(false) })
    return () => { active = false }
  }, [row.resolved_player_id])

  return (
    <div className="dv-expand">
      <p className="dv-expand__verdict">
        {verdict}
        {isGoalie && <span className="dv-expand__caveat"> Goalie value is cruder.</span>}
      </p>
      <div className="dv-expand__figrow">
        <div className="dv-expand__inv">
          <span className="dv-expand__inv-label">Performed like pick</span>
          <span className="dv-expand__inv-value mono">#{invPick}</span>
        </div>
        <PairedBand expected={row.expected_mean} realized={row.realized_value} />
      </div>
      <div className="dv-expand__actions">
        {row.resolved_player_id && (
          <Link to={`/players/${row.resolved_player_id}`} className="dv-action dv-action--primary">
            Player profile <ArrowRight size={14} />
          </Link>
        )}
        {hasDeal && row.resolved_player_id && (
          <Link to={`/studio/contracts?player=${row.resolved_player_id}&name=${encodeURIComponent(row.full_name ?? '')}`}
            className="dv-action">
            Grade his deal <ArrowRight size={14} />
          </Link>
        )}
      </div>
    </div>
  )
}

const POS_TABS = [
  { value: 'all', label: 'All' }, { value: 'F', label: 'F' },
  { value: 'D', label: 'D' }, { value: 'G', label: 'G' },
]
const VIEW_TABS = [
  { value: 'steals', label: 'Steals' }, { value: 'busts', label: 'Busts' }, { value: 'all', label: 'All' },
]

function Board({ curve }: { curve: PickValueCurveRow[] }) {
  const [params, setParams] = useSearchParams()
  const view = (params.get('view') as 'steals' | 'busts' | 'all') || 'steals'
  const cls = params.get('cls') || 'all'
  const pos = params.get('pos') || 'all'
  const team = params.get('team') || 'all'
  const q = params.get('q') || ''
  const setParam = (k: string, v: string, def: string) => {
    const next = new URLSearchParams(params)
    if (v === def) next.delete(k); else next.set(k, v)
    setParams(next, { replace: true })
  }

  // The board endpoint only serves the two tails (steals/busts) by pos; fetch both wide and filter
  // class/team/search client-side. TODO(data): server-side class/team/search + a true "all" slice.
  const [steals, setSteals] = useState<DraftBoardRow[] | null>(null)
  const [busts, setBusts] = useState<DraftBoardRow[] | null>(null)
  const [shown, setShown] = useState(25)
  const [open, setOpen] = useState<string | null>(null)
  const [dir, setDir] = useState<'asc' | 'desc'>('desc')

  useEffect(() => {
    Promise.all([getDraftBoard('steals', undefined, 250), getDraftBoard('busts', undefined, 250)])
      .then(([s, b]) => { setSteals(s); setBusts(b) })
      .catch(() => { setSteals([]); setBusts([]) })
  }, [])

  // Busts default to ascending emphasis; steals/all descending. Reset on view change.
  useEffect(() => { setDir(view === 'busts' ? 'asc' : 'desc'); setShown(25); setOpen(null) }, [view])
  useEffect(() => { setShown(25); setOpen(null) }, [cls, pos, team, q])

  const teamOptions = useMemo<SelectOption[]>(() => {
    const set = new Set<string>()
    for (const r of [...(steals ?? []), ...(busts ?? [])]) if (r.draft_team_abbrev) set.add(r.draft_team_abbrev)
    return [{ value: 'all', label: 'All teams' }, ...[...set].sort().map((t) => ({ value: t, label: t }))]
  }, [steals, busts])

  const classOptions = useMemo<SelectOption[]>(() => {
    const years: SelectOption[] = []
    for (let y = 2010; y <= 2018; y++) years.push({ value: String(y), label: `Class of ${y}` })
    return [{ value: 'all', label: 'Classes 2010–2018' }, ...years]
  }, [])

  const rows = useMemo(() => {
    let base: DraftBoardRow[]
    if (view === 'steals') base = steals ?? []
    else if (view === 'busts') base = busts ?? []
    else {
      const seen = new Set<string>()
      base = [...(steals ?? []), ...(busts ?? [])].filter((r) => {
        const k = `${r.overall_pick}-${r.draft_year}`
        if (seen.has(k)) return false
        seen.add(k); return true
      })
    }
    const filtered = base.filter((r) =>
      (pos === 'all' || r.pos_group === pos) &&
      (cls === 'all' || String(r.draft_year) === cls) &&
      (team === 'all' || r.draft_team_abbrev === team) &&
      (!q || (r.full_name ?? '').toLowerCase().includes(q.toLowerCase())))
    return [...filtered].sort((a, b) =>
      dir === 'asc' ? a.value_above_slot - b.value_above_slot : b.value_above_slot - a.value_above_slot)
  }, [view, steals, busts, pos, cls, team, q, dir])

  const loading = steals === null || busts === null
  const visible = rows.slice(0, shown)

  return (
    <section className="dv-boardwrap">
      <div className="dv-boardhead">
        <Tabs options={VIEW_TABS} value={view} onChange={(v) => setParam('view', v, 'steals')} />
      </div>
      <div className="dv-filters">
        <Tabs options={POS_TABS} value={pos} onChange={(v) => setParam('pos', v, 'all')} />
        <Select value={cls} options={classOptions} onChange={(v) => setParam('cls', v, 'all')} ariaLabel="Draft class" />
        <Select value={team} options={teamOptions} onChange={(v) => setParam('team', v, 'all')} ariaLabel="Drafting team" />
        <input className="dv-search" type="search" placeholder="Search player" value={q}
          onChange={(e) => setParam('q', e.target.value, '')} aria-label="Search player" />
      </div>

      {loading ? (
        <SkeletonLoader height={400} />
      ) : (
        <table className="dv-table dv-board">
          <thead>
            <tr>
              <th>Player</th>
              <th className="num">Pick</th>
              <th className="num">Realized</th>
              <th className="num dv-slotcol">
                <Tooltip content="Expected 7-year WAR for this draft slot, from the fitted curve.">Slot exp.</Tooltip>
              </th>
              <th className="num dv-vscol">
                <button className="dv-sortbtn" onClick={() => setDir((d) => (d === 'asc' ? 'desc' : 'asc'))}>
                  vs slot {dir === 'asc' ? '▲' : '▼'}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr><td colSpan={5} className="dv-empty">No picks match these filters.</td></tr>
            )}
            {visible.map((r) => {
              const key = `${r.overall_pick}-${r.draft_year}`
              const isOpen = open === key
              const beat = r.value_above_slot >= 0
              return (
                <Fragment key={key}>
                  <tr className={`dv-board__row${isOpen ? ' dv-board__row--open' : ''}`}
                    onClick={() => setOpen(isOpen ? null : key)} tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(isOpen ? null : key) } }}>
                    <td className="dv-board__player">
                      {r.resolved_player_id
                        ? <PlayerAvatar id={r.resolved_player_id} team={r.draft_team_abbrev ?? undefined} name={r.full_name ?? ''} size={28} />
                        : <span className="dv-board__noavatar" aria-hidden />}
                      <div className="dv-board__name">
                        <span>{r.full_name ?? '—'}</span>
                        <span className="dv-board__meta">{r.draft_year} · {r.draft_team_abbrev ?? ''} · {r.pos_group ?? ''}</span>
                      </div>
                    </td>
                    <td className="num mono">#{r.overall_pick}</td>
                    <td className="num mono">{r.realized_value.toFixed(1)}</td>
                    <td className="num mono dv-muted dv-slotcol">{r.expected_mean.toFixed(1)}</td>
                    <td className="num dv-vscol">
                      <div className="dv-vscell">
                        <span className={`mono ${beat ? 'dv-pos' : 'dv-neg'}`}>{signed(r.value_above_slot)}</span>
                        <VsBand value={r.value_above_slot} />
                      </div>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="dv-board__xrow">
                      <td colSpan={5}><ExpandedRow row={r} curve={curve} /></td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      )}

      {!loading && rows.length > shown && (
        <button className="dv-showmore" onClick={() => setShown((s) => s + 25)}>Show more</button>
      )}
    </section>
  )
}

// ---------------------------------------------------------------- page
export default function DraftValue() {
  usePageTitle('Draft value')
  const [curve, setCurve] = useState<PickValueCurveRow[] | null>(null)

  useEffect(() => { getPickValueCurve().then(setCurve).catch(() => setCurve([])) }, [])

  const copyLink = () => { navigator.clipboard?.writeText(window.location.href).catch(() => {}) }

  return (
    <PageLayout>
      <div className="dv">
        <PageCard
          eyebrow="Studio"
          title="Draft value"
          subtitle="What a pick is worth, and who beat their slot."
          controls={
            <div className="dv-toolbar">
              <Link to={ESSAY_TO} className="dv-toolbar__link">Read the research <ArrowRight size={14} /></Link>
              <button type="button" className="dv-toolbar__btn" onClick={copyLink}><Copy size={14} /> Copy link</button>
            </div>
          }
        >
          <section className="dv-section">
            {curve && curve.length ? <PickLookup curve={curve} /> : <SkeletonLoader height={340} />}
          </section>

          <div className="page-divider" />

          <section className="dv-section">
            <h2 className="dv-section__title">Steals and busts</h2>
            <p className="dv-section__sub">
              Evaluable picks (classes 2010–2018) ranked by how far their realized value beat or trailed
              the expectation for their slot.
            </p>
            {curve && curve.length ? <Board curve={curve} /> : <SkeletonLoader height={400} />}
          </section>
        </PageCard>
      </div>
    </PageLayout>
  )
}
