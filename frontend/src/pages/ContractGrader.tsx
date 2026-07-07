import { useState, useEffect, useCallback, useMemo } from 'react'
import { usePageTitle } from '../hooks/usePageTitle'
import { Link } from 'react-router-dom'
import { Info, ChevronDown, FileSignature, ArrowRight } from 'lucide-react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  Tooltip as RTooltip, ReferenceLine, ReferenceArea, Label,
} from 'recharts'
import {
  PageLayout, PageCard, PlayerPicker, PlayerAvatar, Tabs, ChartPanel, Tooltip,
  SkeletonLoader, ComponentStackBar, ShareActions,
} from '../components/common'
import { useChartPanelHeight } from '../components/common/ChartPanel'
import type { StackSegment } from '../components/common'
import type {
  PlayerSearchResult, PlayerContract, ContractGrade, TradeableAsset,
} from '../api/types'
import { getPlayerContract, gradeContract, getSurplusRankings } from '../api/assets'
import { searchPlayers } from '../api/tools'
import './ContractGrader.css'

/* One dollar-formatting standard everywhere: $X.XXM (two decimals). Percentages: one decimal (3.6). */
const fmtM = (d: number) => `$${(d / 1e6).toFixed(2)}M`
const fmtMsign = (d: number) => `${d >= 0 ? '+' : '−'}$${Math.abs(d / 1e6).toFixed(2)}M`
const pct1 = (v: number) => `${(v * 100).toFixed(1)}%`
const war1 = (v: number) => v.toFixed(1)
const startYear = (season: string) => parseInt(season.slice(0, 4), 10)
const seasonStr = (y: number) => `${y}-${String(y + 1).slice(2)}`

const GRADE_TONE: Record<string, 'positive' | 'neutral' | 'caution'> = {
  A: 'positive', B: 'positive', C: 'neutral', D: 'caution', F: 'caution',
}

/** Verdict-kicker date stamp, e.g. "JUL 6" (browser-local; the share card echoes it). */
const shareStamp = () => new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()
/** Map a grade's confidence word to the VerdictCard confidence tone. */
const confTone = (word?: string): 'high' | 'medium' | 'low' =>
  word === 'high' ? 'high' : word === 'proxy' || word === 'low' ? 'low' : 'medium'

/** Everything the result panel shows derives from one grade response (the shown deal). */
function derive(g: ContractGrade) {
  // break-even fair AAV over the term comes from the backend now (zeros PV surplus); fall back if absent.
  const breakEven = g.fair_aav_breakeven ?? (g.cost_dollars > 0 ? (g.value_dollars * g.cap_hit) / g.cost_dollars : g.fair_aav)
  const fairNow = g.fair_aav_now ?? g.fair_aav
  const deltaVsFair = g.cap_hit - breakEven                 // >0 = over fair (cost exceeds break-even)
  const pctOverFair = breakEven > 0 ? deltaVsFair / breakEven : 0
  const ratio = g.cost_dollars > 0 ? g.total_discounted_surplus / g.cost_dollars : 0  // = the verdict's %
  const bandHalf = Math.round((g.surplus_high - g.surplus_low) / 2)
  const capShareNow = g.cap_share_schedule.length ? g.cap_share_schedule[0].actual_share : 0
  return { breakEven, fairNow, deltaVsFair, pctOverFair, ratio, bandHalf, capShareNow }
}

/** A stat unit (label · mono value · optional sub · optional delta chip). tier sets the visual weight:
 * 'primary' = the two numbers that matter most (larger); 'secondary' = supporting figures (smaller). */
function Stat({ label, value, sub, delta, deltaTone, tip, tier = 'secondary' }: {
  label: string; value: string; sub?: string; delta?: string
  deltaTone?: 'positive' | 'caution' | 'neutral'; tip?: string; tier?: 'primary' | 'secondary'
}) {
  return (
    <div className={`cg-stat cg-stat--${tier}`}>
      <div className="cg-stat__head">
        <span className="cg-stat__label">{label}</span>
        {tip && <Tooltip content={tip}><Info size={13} className="cg-stat__info" /></Tooltip>}
      </div>
      <div className="cg-stat__container">
        <div className="cg-stat__value mono">{value}</div>
        {delta && <span className={`cg-stat__delta cg-stat__delta--${deltaTone ?? 'neutral'} mono`}>{delta}</span>}
        {sub && <div className="cg-stat__sub">{sub}</div>}
      </div>
    </div>
  )
}

/** De-defaulted per-year tooltip: age, projected WAR, fair value, cap hit, that year's surplus. */
function ChartTip({ active, payload, unit }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const f = (v: number) => unit === '$' ? `$${v.toFixed(2)}M` : `${v.toFixed(1)}%`
  return (
    <div className="cg-charttip">
      <div className="cg-charttip__season">{d.season}{d.age != null ? ` · age ${d.age}` : ''}{d.war != null ? ` · ${war1(d.war)} WAR` : ''}</div>
      <div className="cg-charttip__row"><span>Worth (fair)</span><span className="mono">{f(d.fair)}</span></div>
      <div className="cg-charttip__row"><span>Cap hit</span><span className="mono">{f(d.paid)}</span></div>
      <div className={`cg-charttip__row cg-charttip__row--${d.fair >= d.paid ? 'pos' : 'neg'}`}>
        <span>Surplus</span><span className="mono">{unit === '$' ? fmtMsign((d.fair - d.paid) * 1e6) : `${d.fair - d.paid >= 0 ? '+' : '−'}${Math.abs(d.fair - d.paid).toFixed(1)}pp`}</span>
      </div>
    </div>
  )
}

function PaidVsWorthChart({ g, unit, ghostAAV }: { g: ContractGrade; unit: '$' | '%'; ghostAAV?: number | null }) {
  const height = useChartPanelHeight()
  // value-band ratio (PV) scaled onto the per-year fair line as a faint confidence ribbon
  const loR = g.value_dollars_low && g.value_dollars ? g.value_dollars_low / g.value_dollars : 1
  const hiR = g.value_dollars_high && g.value_dollars ? g.value_dollars_high / g.value_dollars : 1
  const data = g.cap_share_schedule.map((y) => {
    const paid = unit === '$' ? (y.actual_share * y.cap) / 1e6 : y.actual_share * 100
    const fair = unit === '$' ? (y.expected_share * y.cap) / 1e6 : y.expected_share * 100
    return {
      season: y.season, age: y.age ?? null, war: y.projected_war ?? null,
      paid, fair,
      bandLo: fair * loR, bandSpan: fair * (hiR - loR),
      base: Math.min(paid, fair),
      surplus: Math.max(0, fair - paid),
      deficit: Math.max(0, paid - fair),
    }
  })
  const ghost = ghostAAV != null ? (unit === '$' ? ghostAAV / 1e6 : (ghostAAV / (g.cap_share_schedule[0]?.cap ?? 1)) * 100) : null
  const vals = data.flatMap((r) => [r.paid, r.fair, r.bandLo, r.bandLo + r.bandSpan]).concat(ghost != null ? [ghost] : [])
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = Math.max((hi - lo) * 0.18, hi * 0.04)
  const domain: [number, number] = [Math.max(0, lo - pad), hi + pad]
  const axisFmt = (v: number) => unit === '$' ? `$${v.toFixed(0)}M` : `${v.toFixed(0)}%`
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 12, right: 56, bottom: 4, left: 4 }}>
        <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" />
        {/* §S5: the contract window shades in --crease, spanning exactly the entered term. */}
        {data.length > 0 && (
          <ReferenceArea x1={data[0].season} x2={data[data.length - 1].season}
            fill="var(--crease)" fillOpacity={1} stroke="none" ifOverflow="extendDomain" />
        )}
        <XAxis dataKey="season" stroke="var(--color-border)"
          tick={(props: any) => {
            const row = data[props.index]
            return (
              <g transform={`translate(${props.x},${props.y})`}>
                <text dy={12} textAnchor="middle" fontSize={11} fill="var(--color-text-secondary)">{props.payload.value}</text>
                {row?.age != null && <text dy={25} textAnchor="middle" fontSize={9} fill="var(--color-text-muted)">age {row.age}</text>}
              </g>
            )
          }} height={40} />
        <YAxis domain={domain} allowDataOverflow stroke="var(--color-border)"
          tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} tickFormatter={axisFmt} width={48} />
        <RTooltip content={<ChartTip unit={unit} />} />
        {/* confidence ribbon (faint) on the fair-value line */}
        <Area dataKey="bandLo" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} />
        <Area dataKey="bandSpan" stackId="band" stroke="none" fill="var(--color-text-muted)" fillOpacity={0.10} isAnimationActive={false} />
        {/* worth-vs-paid gap shading */}
        <Area dataKey="base" stackId="g" stroke="none" fill="transparent" isAnimationActive={false} />
        <Area dataKey="surplus" stackId="g" stroke="none" fill="var(--color-data-positive)" fillOpacity={0.18} animationDuration={400} />
        <Area dataKey="deficit" stackId="g" stroke="none" fill="var(--color-data-negative)" fillOpacity={0.18} animationDuration={400} />
        {ghost != null && (
          <ReferenceLine y={ghost} stroke="var(--color-text-muted)" strokeDasharray="3 3" strokeWidth={1}>
            <Label value="actual deal" position="insideBottomLeft" fill="var(--color-text-muted)" style={{ fontSize: 10 }} />
          </ReferenceLine>
        )}
        {/* §S5: the AAV as a flat 1px "cap hit" reference line, labeled in Newsreader italic. */}
        <ReferenceLine y={data.reduce((s, r) => s + r.paid, 0) / (data.length || 1)}
          stroke="var(--color-text-primary)" strokeWidth={1}>
          <Label value="cap hit" position="right" dy={12}
            fill="var(--color-text-secondary)"
            style={{ fontSize: 13, fontStyle: 'italic', fontFamily: 'var(--font-display)' }} />
        </ReferenceLine>
        {/* §S5: red "now" tick at the first (today) season. */}
        {data.length > 0 && (
          <ReferenceLine x={data[0].season} stroke="var(--line-red)" strokeWidth={1}>
            <Label value="now" position="insideTopLeft" fill="var(--line-red)"
              style={{ fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase' }} />
          </ReferenceLine>
        )}
        {/* §S5: projected value line is dashed (solid=observed / dashed=projected). */}
        <Line type="monotone" dataKey="fair" stroke="var(--color-data-positive)" strokeWidth={2}
          strokeDasharray="5 4" dot={false} animationDuration={400}>
          <Label value="worth" position="right" dy={-3} fill="var(--color-data-positive)" style={{ fontSize: 11, fontWeight: 600 }} />
        </Line>
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function DetailTable({ g }: { g: ContractGrade }) {
  return (
    <table className="cg-table">
      <thead>
        <tr>
          <th>Season</th><th className="num">Age</th><th className="num">Proj WAR</th>
          <th className="num">Worth $</th><th className="num">Cap hit $</th>
          <th className="num">Surplus $</th><th className="num">Cumulative</th>
        </tr>
      </thead>
      <tbody>
        {g.cap_share_schedule.map((y) => {
          const worth = y.fair_value_dollars ?? y.expected_share * y.cap
          const paid = y.cap_hit_dollars ?? y.actual_share * y.cap
          const surp = y.surplus_dollars ?? (worth - paid)
          const cum = y.cumulative_surplus_dollars ?? null
          return (
            <tr key={y.season}>
              <td>{y.season}</td>
              <td className="num mono">{y.age ?? '—'}</td>
              <td className="num mono">{y.projected_war != null ? war1(y.projected_war) : '—'}</td>
              <td className="num mono">{fmtM(worth)}</td>
              <td className="num mono">{fmtM(paid)}</td>
              <td className={`num mono ${surp >= 0 ? 'is-pos' : 'is-neg'}`}>{fmtMsign(surp)}</td>
              <td className={`num mono ${(cum ?? 0) >= 0 ? 'is-pos' : 'is-neg'}`}>{cum != null ? fmtMsign(cum) : '—'}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/** Layer 3a — how the value was built: blended WAR + windows, caliber, market position, cap-growth split. */
function DerivationPanel({ g }: { g: ContractGrade }) {
  const windows = g.war_windows ?? []
  const splitTotal = g.total_discounted_surplus
  const playerVal = g.player_value_surplus ?? (splitTotal - (g.cap_growth_surplus ?? 0))
  const capGrowth = g.cap_growth_surplus ?? 0
  const segs: StackSegment[] = [
    { key: 'player', label: 'Player value', value: playerVal, color: 'var(--color-data-1)' },
    { key: 'capgrowth', label: 'Cap growth', value: capGrowth, color: 'var(--color-data-neutral)' },
  ]
  const maxAbs = Math.max(Math.abs(playerVal), Math.abs(capGrowth), Math.abs(splitTotal), 1)
  return (
    <div className="cg-derive">
      <div className="cg-derive__grid">
        <div className="cg-derive__cell">
          <span className="cg-derive__k">Blended WAR</span>
          <span className="cg-derive__v mono">{g.blended_war != null ? war1(g.blended_war) : war1(g.war_now)}</span>
          <span className="cg-derive__note">
            recency + games weighted{g.shrink_factor != null ? ` · ${pct1(g.shrink_factor)} sample credibility` : ''}
          </span>
        </div>
        <div className="cg-derive__cell">
          <span className="cg-derive__k">Caliber (role + production)</span>
          <span className="cg-derive__v mono">{g.caliber_pct != null ? `${Math.round(g.caliber_pct * 100)}th pctl` : '—'}</span>
          <span className="cg-derive__note">priced at the {g.value_basis === 'caliber-floor' ? 'going rate for his caliber (floor)' : 'value of his own production'}</span>
        </div>
        <div className="cg-derive__cell">
          <span className="cg-derive__k">Aging over the term</span>
          <span className="cg-derive__v mono">
            {g.cap_share_schedule[0]?.projected_war != null
              ? `${war1(g.cap_share_schedule[0].projected_war)} → ${war1(g.cap_share_schedule[g.cap_share_schedule.length - 1].projected_war ?? 0)} WAR`
              : '—'}
          </span>
          <span className="cg-derive__note">projected production, first to last season</span>
        </div>
      </div>
      <div className="cg-derive__windows">
        <span className="cg-derive__k">Production windows feeding the blend</span>
        <div className="cg-derive__chips">
          {windows.map((w) => (
            <span key={w.season_window} className="cg-derive__chip mono">
              {w.season_window.length > 7 ? w.season_window : w.season_window}
              <b>{war1(w.war)}</b><i>{w.games}g</i>
            </span>
          ))}
        </div>
      </div>
      <div className="cg-derive__split">
        <span className="cg-derive__k">
          Surplus = player value + cap-growth bonus
          <Tooltip content="Part of the surplus is the player out-producing his cap hit; part is a flat cap hit shrinking as a share of a rising cap. Both are real value to the team; shown separately so a long deal ranking well is explained.">
            <Info size={12} className="cg-stat__info" />
          </Tooltip>
        </span>
        <ComponentStackBar segments={segs} total={splitTotal} domain={[-maxAbs, maxAbs]}
          formatValue={(v) => fmtMsign(v)} />
      </div>
    </div>
  )
}

/** Layer 3b — the real signed deals nearest this player by caliber + position. */
function Comparables({ g }: { g: ContractGrade }) {
  const comps = g.comparables ?? []
  if (!comps.length) return null
  return (
    <ul className="cg-comps">
      {comps.map((c) => (
        <li key={c.player_id} className="cg-comps__row">
          <Link to={`/players/${c.player_id}`} className="cg-comps__name">{c.name}</Link>
          <span className="cg-comps__deal mono">{fmtM(c.aav)} × {c.term}y</span>
          {c.grade ? <span className={`cg-list__grade cg-grade--${c.grade}`}>{c.grade}</span> : <span />}
        </li>
      ))}
    </ul>
  )
}

export default function ContractGrader() {
  usePageTitle('Contracts')
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null)
  const [contract, setContract] = useState<PlayerContract | null>(null)
  const [actualGrade, setActualGrade] = useState<ContractGrade | null>(null)
  const [hypoGrade, setHypoGrade] = useState<ContractGrade | null>(null)
  const [mode, setMode] = useState<'actual' | 'hypothetical'>('actual')
  const [capM, setCapM] = useState(5)
  const [term, setTerm] = useState(4)
  const [unit, setUnit] = useState<'$' | '%'>('$')
  const [loading, setLoading] = useState(false)
  const [showAnalysis, setShowAnalysis] = useState(false)   // single evidence expander, collapsed by default
  const [view, setView] = useState<'grade' | 'leaderboards'>('grade')   // page-level surface
  const [best, setBest] = useState<TradeableAsset[]>([])
  const [worst, setWorst] = useState<TradeableAsset[]>([])

  useEffect(() => {
    getSurplusRankings('surplus', 10).then(setBest).catch(() => {})
    getSurplusRankings('overpaid', 10).then(setWorst).catch(() => {})
  }, [])

  const onSelect = useCallback((p: PlayerSearchResult) => {
    setPlayer(p); setContract(null); setActualGrade(null); setHypoGrade(null); setLoading(true)
    getPlayerContract(p.player_id)
      .then(async (c) => {
        setContract(c)
        const projected = c.contract_status === 'rfa_projected'
        if (c.cap_hit && c.remaining_years) {
          setCapM(Math.round((c.cap_hit / 1e6) * 4) / 4)
          setTerm(Math.min(8, Math.max(1, c.remaining_years)))
          if (projected) {
            setMode('hypothetical')                            // RFA: editable hypothetical, not a set deal
          } else {
            setMode('actual')
            const ag = await gradeContract(p.player_id, c.cap_hit, Math.min(8, c.remaining_years))
            setActualGrade(ag)
          }
        } else {
          setMode('hypothetical')
        }
      })
      .catch(() => setMode('hypothetical'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    let active = true
    searchPlayers('McDavid', 1).then((r) => { if (active && r.length) onSelect(r[0]) }).catch(() => {})
    return () => { active = false }
  }, [onSelect])

  // Live grade for the hypothetical builder (debounced).
  useEffect(() => {
    if (!player) return
    const h = setTimeout(() => {
      gradeContract(player.player_id, Math.round(capM * 1e6), term).then(setHypoGrade).catch(() => {})
    }, 300)
    return () => clearTimeout(h)
  }, [player, capM, term])

  const isProjected = contract?.contract_status === 'rfa_projected'
  const hasActual = !!contract?.cap_hit && !!contract.remaining_years && !isProjected
  const effectiveMode = hasActual ? mode : 'hypothetical'
  const grade = effectiveMode === 'actual' ? actualGrade : hypoGrade
  const d = useMemo(() => (grade ? derive(grade) : null), [grade])
  const sched = grade?.cap_share_schedule ?? []
  const lastWar = sched.length ? sched[sched.length - 1].projected_war : null
  const firstWar = sched.length ? sched[0].projected_war : null

  return (
    <PageLayout>
      <div className="cg-page">
        <PageCard
          eyebrow="Studio"
          title="Contract Grader"
          subtitle="Grade any deal against the aging curve and the market."
          controls={
            <Tabs
              options={[{ value: 'grade', label: 'Grade a contract' }, { value: 'leaderboards', label: 'Leaderboards' }]}
              value={view} onChange={(v) => setView(v as 'grade' | 'leaderboards')}
            />
          }
        >
        {view === 'grade' && (!player && !loading ? (
          <div className="cg-empty">
            <FileSignature size={28} />
            <p>Search a player to grade their contract — or build a hypothetical deal.</p>
            <div className="cg-empty__pick"><PlayerPicker onSelect={onSelect} placeholder="Search a player…" /></div>
          </div>
        ) : (
          <div className="cg-layout">
            {/* LEFT (4 cols, sticky) — the contract */}
            <aside className="cg-builder">
              <Tabs
                options={[
                  { value: 'actual', label: 'Grade actual deal', disabled: !hasActual },
                  { value: 'hypothetical', label: 'Build hypothetical' },
                ]}
                value={effectiveMode}
                onChange={(v) => setMode(v as 'actual' | 'hypothetical')}
              />

              <div className="cg-id">
                <PlayerPicker onSelect={onSelect} placeholder="Change player…" />
                {player && (
                  <div className="cg-id__block">
                    <PlayerAvatar id={player.player_id} team={player.team_abbrev} name={player.name ?? ''} size={48} />
                    <div className="cg-id__meta">
                      <div className="cg-id__name">{player.name}</div>
                      <div className="cg-id__ctx">{[player.position, player.team_abbrev].filter(Boolean).join(' · ')}</div>
                    </div>
                  </div>
                )}
                {grade && firstWar != null && (
                  <div className="cg-proj">
                    <div className="cg-proj__txt">
                      Projected <span className="cg-proj__war mono">{war1(firstWar)} WAR</span> now, aging to
                      {' '}<span className="mono">~{war1(lastWar ?? firstWar)}</span> by {seasonStr(startYear(grade.season) + grade.term_years - 1)}
                    </div>
                  </div>
                )}
                {hasActual ? (
                  <div className="cg-actual-chip">
                    Actual: <strong className="mono">{fmtM(contract!.cap_hit!)} × {contract!.remaining_years}y</strong>
                    {contract!.expiry_year ? `, expires ${contract!.expiry_year}` : ''}
                  </div>
                ) : isProjected && contract?.cap_hit ? (
                  <div className="cg-actual-chip cg-actual-chip--proj">
                    No signed deal — starting from his projected RFA value{' '}
                    <strong className="mono">{fmtM(contract.cap_hit)} × {contract.remaining_years}y</strong>. Adjust to grade a hypothetical.
                  </div>
                ) : player ? (
                  <div className="cg-actual-chip cg-actual-chip--none">No contract on file</div>
                ) : null}
              </div>

              {/* AAV */}
              <div className="cg-control">
                <label className="cg-control__label">Cap hit (AAV)</label>
                {effectiveMode === 'actual' && hasActual ? (
                  <div className="cg-aav mono cg-aav--locked">{fmtM(contract!.cap_hit!)}</div>
                ) : (
                  <>
                    <div className="cg-aav mono">{fmtM(Math.round(capM * 1e6))}</div>
                    <input type="range" min={0.75} max={20} step={0.25} value={capM}
                      onChange={(e) => setCapM(Number(e.target.value))} className="cg-slider" />
                  </>
                )}
                {d && grade && (
                  <div className="cg-control__sub mono">{pct1(d.capShareNow)} of cap</div>
                )}
              </div>

              {/* Term */}
              <div className="cg-control">
                <label className="cg-control__label">Term</label>
                <div className="cg-term">
                  <button onClick={() => setTerm((t) => Math.max(1, t - 1))}
                    disabled={effectiveMode === 'actual' || term <= 1}>−</button>
                  <span className="mono">{(effectiveMode === 'actual' && hasActual ? contract!.remaining_years! : term)} yrs</span>
                  <button onClick={() => setTerm((t) => Math.min(8, t + 1))}
                    disabled={effectiveMode === 'actual' || term >= 8}>+</button>
                </div>
                {grade && (
                  <div className="cg-control__sub mono">
                    {(() => {
                      const yrs = effectiveMode === 'actual' && hasActual ? contract!.remaining_years! : grade.term_years
                      const exp = effectiveMode === 'actual' && contract?.expiry_year ? contract.expiry_year : startYear(grade.season) + grade.term_years
                      const a0 = sched[0]?.age, a1 = sched[sched.length - 1]?.age
                      return `expires ${exp}${a0 != null && a1 != null ? ` · age ${a0}–${a1}` : ''} · ${yrs}y`
                    })()}
                  </div>
                )}
              </div>
            </aside>

            {/* RIGHT (8 cols) — three layers on the background */}
            <div className="cg-result">
              {loading || !grade || !d ? (
                <ResultSkeleton />
              ) : (
                <>
                  {/* Layer 1 — verdict banner */}
                  <div className={`cg-banner cg-banner--${GRADE_TONE[grade.grade]}`}>
                    <div className={`cg-medallion cg-medallion--${GRADE_TONE[grade.grade]}`}>{grade.grade}</div>
                    <div className="cg-banner__body">
                      <div className="cg-banner__kickrow">
                        <span className="cg-banner__kicker mono">CONTRACT GRADE · {shareStamp()}</span>
                        <ShareActions kicker={`CONTRACT GRADE · ${shareStamp()}`} verdict={grade.verdict}
                          confidence={{ tone: confTone(grade.confidence), word: grade.confidence,
                            phrase: grade.war_sd != null ? `±${war1(grade.war_sd)} WAR` : undefined }}
                          shareName={`contract-${player?.name?.replace(/\s+/g, '-').toLowerCase() ?? 'grade'}`} />
                      </div>
                      <div className="cg-banner__eyebrow">
                        {effectiveMode === 'actual' ? 'Actual contract' : 'Hypothetical contract'}
                        {effectiveMode === 'hypothetical' && actualGrade && (
                          <span className="cg-banner__vs"> · actual deal grades {actualGrade.grade}</span>
                        )}
                      </div>
                      <p className="cg-banner__headline">{grade.verdict}</p>
                      <p className={`cg-banner__surplus mono cg-${grade.total_discounted_surplus >= 0 ? 'pos' : 'neg'}`}>
                        Surplus (present value): {fmtMsign(grade.total_discounted_surplus)}
                        <span className="cg-banner__band"> ± {fmtM(d.bandHalf).replace('$', '$')}</span>
                        <span className="cg-banner__ratio"> ({grade.total_discounted_surplus >= 0 ? '+' : '−'}{Math.abs(Math.round(d.ratio * 100))}% vs cost)</span>
                      </p>
                      {effectiveMode === 'hypothetical' && actualGrade && (
                        <p className="cg-banner__delta mono">
                          vs the actual deal: {fmtMsign(grade.total_discounted_surplus - actualGrade.total_discounted_surplus)} surplus
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Layer 2a — stat cards: two PRIMARY (the numbers that matter), three secondary beneath */}
                  <div className="cg-stats">
                    <div className="cg-stats__primary">
                      <Stat tier="primary" label="Fair AAV (this term)" value={fmtM(d.breakEven)}
                        delta={`${fmtMsign(-d.deltaVsFair)} vs cap · ${pct1(Math.abs(d.pctOverFair))} ${d.deltaVsFair <= 0 ? 'under' : 'over'} fair`}
                        deltaTone={d.deltaVsFair <= 0 ? 'positive' : 'caution'}
                        tip="The flat AAV that breaks even on present-value surplus over this term — the most this deal should cost." />
                      <Stat tier="primary" label="Surplus (PV)" value={fmtMsign(grade.total_discounted_surplus)}
                        delta={`player ${fmtMsign(grade.player_value_surplus ?? 0)} · cap-growth ${fmtMsign(grade.cap_growth_surplus ?? 0)}`}
                        deltaTone={grade.total_discounted_surplus >= 0 ? 'positive' : 'caution'}
                        tip="Projected value minus cost, present-valued. Split into the player out-earning his cap hit vs the flat cap hit shrinking against a rising cap." />
                    </div>
                    <div className="cg-stats__secondary">
                      <Stat label="Cap hit" value={fmtM(grade.cap_hit)}
                        sub={`× ${grade.term_years} yrs · ${pct1(d.capShareNow)} of cap`}
                        tip="The annual cap charge over the term." />
                      <Stat label="Fair AAV (now)" value={fmtM(d.fairNow)}
                        sub="point-in-time, this season"
                        tip="What the market would pay for this production THIS season (year-0). Distinct from the term figure, which averages the aging path." />
                      <Stat label="Confidence" value={grade.confidence}
                        sub={grade.war_sd != null ? `±${war1(grade.war_sd)} WAR band` : undefined}
                        tip="Driven by projection sample (games), age, and role stability. ‘proxy’ = no current-season sample (floored near replacement)." />
                    </div>
                  </div>

                  {/* Layer 2b — hero chart */}
                  <div className="cg-chart-block">
                    <div className="cg-chart-units">
                      <Tabs options={[{ value: '$', label: '$' }, { value: '%', label: '% of cap' }]} value={unit} onChange={(v) => setUnit(v as '$' | '%')} />
                    </div>
                    <ChartPanel
                      expandable={false}
                      title={`Paid vs worth — ${d.deltaVsFair <= 0 ? 'value beats the cap hit' : 'the cap hit outruns the value'} across the term`}
                      subtitle="Projected fair value (with its confidence ribbon) vs the flat cap hit, by contract season"
                      footer={
                        <div className="cg-chart-foot">
                          <span className="cg-key"><span className="cg-key__sw cg-key__sw--worth" /> worth more than paid</span>
                          <span className="cg-key"><span className="cg-key__sw cg-key__sw--paid" /> paid more than worth</span>
                          {effectiveMode === 'hypothetical' && hasActual && (
                            <span className="cg-derived">A fair deal over this term ≈ {fmtM(d.breakEven)} × {grade.term_years}y</span>
                          )}
                        </div>
                      }
                    >
                      <PaidVsWorthChart g={grade} unit={unit}
                        ghostAAV={effectiveMode === 'hypothetical' && hasActual ? contract!.cap_hit! : null} />
                    </ChartPanel>
                  </div>

                  {/* Honest caveat tied to the grade (only for below-replacement bets) — stays visible. */}
                  {grade.grounded && (grade.blended_war ?? 0) < 0 && (
                    <p className="cg-bet-note">
                      Note: our models rate his recent production below replacement. The grade reflects that honestly —
                      a positive surplus here is the projection betting on growth (wide confidence band), not current value.
                    </p>
                  )}

                  {/* Layer 3 — all evidence behind ONE expander, collapsed by default */}
                  <div className="cg-detail">
                    <button className="cg-detail__toggle" onClick={() => setShowAnalysis((s) => !s)}>
                      <ChevronDown size={15} className={showAnalysis ? 'cg-detail__chev cg-detail__chev--open' : 'cg-detail__chev'} />
                      {showAnalysis ? 'Hide' : 'Show'} the analysis
                    </button>
                    {showAnalysis && (
                      <div className="cg-analysis">
                        <section className="cg-trans">
                          <h3 className="cg-trans__title">How the value was built</h3>
                          <DerivationPanel g={grade} />
                        </section>
                        {grade.comparables && grade.comparables.length > 0 && (
                          <section className="cg-trans">
                            <h3 className="cg-trans__title">Comparable deals
                              <span className="cg-trans__sub">the {grade.comparables.length} signed contracts nearest his caliber + position</span>
                            </h3>
                            <Comparables g={grade} />
                          </section>
                        )}
                        <section className="cg-trans">
                          <h3 className="cg-trans__title">Year by year</h3>
                          <DetailTable g={grade} />
                          <p className="cg-detail__note">
                            Grade = present-value surplus relative to cost: A ≥ +30%, B ≥ +12%, C within ±12%, D ≥ −30%, F below.
                            {' '}<Link className="cg-detail__link" to="/learn/archetypes">How this is graded <ArrowRight size={12} /></Link>
                          </p>
                        </section>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        ))}

        {/* Leaderboards — a sibling surface within the Contract tool (the grader is about ONE player) */}
        {view === 'leaderboards' && (
          <section className="cg-boards">
            <p className="cg-boards__intro">
              League-wide contract value — ranked on total present-value surplus over the remaining deal, with each
              deal’s per-year cap-share rate shown alongside.
            </p>
            <div className="cg-lists">
              <div className="cg-list-card">
                <h3 className="cg-list-card__title">Best value</h3>
                <p className="cg-list-card__sub">Most total surplus (present value) over the deal · per-year rate shown alongside</p>
                <ContractList rows={best} />
              </div>
              <div className="cg-list-card">
                <h3 className="cg-list-card__title">Most overpaid</h3>
                <p className="cg-list-card__sub">Most negative total surplus (present value) over the deal · per-year rate shown alongside</p>
                <ContractList rows={worst} />
              </div>
            </div>
          </section>
        )}
        </PageCard>
      </div>
    </PageLayout>
  )
}

function ResultSkeleton() {
  return (
    <>
      <SkeletonLoader height={128} />
      <div className="cg-stats">{[0, 1, 2, 3, 4].map((i) => <SkeletonLoader key={i} height={92} />)}</div>
      <SkeletonLoader height={320} />
      <SkeletonLoader height={140} />
    </>
  )
}

function ContractList({ rows }: { rows: TradeableAsset[] }) {
  return (
    <ol className="cg-list">
      {rows.map((a, i) => {
        // SORT KEY = cumulative PV $ surplus (magnitude); per-year rate is the secondary density read
        const surplus = a.surplus_dollars ?? 0
        const rate = a.surplus_capshare_per_year ?? 0
        const cg = a.cap_growth_surplus ?? 0
        const cgPct = surplus !== 0 && a.cap_growth_surplus != null ? Math.round((cg / surplus) * 100) : null
        const tip = `${fmtMsign(surplus)} cumulative PV surplus · ${(rate * 100).toFixed(1)}%/yr avg cap-share`
          + (cgPct != null ? ` (cap-growth ${fmtMsign(cg)}, ${cgPct}%)` : '')
        const inner = (
          <>
            <span className="cg-list__rank mono">{i + 1}</span>
            <span className="cg-list__id">
              <span className="cg-list__name">{a.label}</span>
              <span className="cg-list__meta mono">
                {a.cap_hit != null ? fmtM(a.cap_hit) : '—'}{a.remaining_years != null ? ` ×${a.remaining_years}y` : ''}
                {a.pos_or_slot ? ` · ${a.pos_or_slot}` : ''}
              </span>
            </span>
            <span className={`cg-list__total mono ${surplus >= 0 ? 'is-pos' : 'is-neg'}`} title={tip}>{fmtMsign(surplus)}</span>
            <span className="cg-list__rate mono" title={tip}>
              {rate >= 0 ? '+' : ''}{(rate * 100).toFixed(1)}%<span className="cg-list__rate-unit">/yr</span>
            </span>
            {a.grade
              ? <span className={`cg-list__grade cg-grade--${a.grade}`}>{a.grade}</span>
              : <span className="cg-list__grade" aria-hidden />}
          </>
        )
        return (
          <li key={a.asset_id} className="cg-list__item">
            {a.player_id
              ? <Link to={`/players/${a.player_id}`} className="cg-list__row">{inner}</Link>
              : <div className="cg-list__row">{inner}</div>}
          </li>
        )
      })}
    </ol>
  )
}
