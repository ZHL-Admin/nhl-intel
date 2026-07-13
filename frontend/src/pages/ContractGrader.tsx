import { useState, useEffect, useCallback, useMemo, Fragment } from 'react'
import { usePageTitle } from '../hooks/usePageTitle'
import { Link, useSearchParams } from 'react-router-dom'
import { Info, ChevronDown, ArrowRight } from 'lucide-react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  Tooltip as RTooltip, ReferenceLine, Label,
} from 'recharts'
import {
  PageLayout, PageCard, PlayerPicker, PlayerAvatar, Tabs, ChartPanel, Tooltip,
  SkeletonLoader, ComponentStackBar, ShareActions, Panel, DotChip,
} from '../components/common'
import { useChartPanelHeight } from '../components/common/ChartPanel'
import type { StackSegment, DotState } from '../components/common'
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

/** Valence per the grade-color amendment: A/B above (blue), C neutral, D/F below (red). No green. */
type Valence = 'pos' | 'neutral' | 'neg'
const GRADE_VALENCE: Record<string, Valence> = { A: 'pos', B: 'pos', C: 'neutral', D: 'neg', F: 'neg' }
/** The verdict's leading word, keyed to the grade (word-first framing, §1.2). */
const GRADE_WORD: Record<string, string> = {
  A: 'A steal.', B: 'A bargain.', C: 'Fair.', D: 'An overpay.', F: 'An albatross.',
}
const valOf = (n: number): Valence => (n > 0 ? 'pos' : n < 0 ? 'neg' : 'neutral')

/** Verdict-kicker date stamp, e.g. "JUL 6" (browser-local; the share card echoes it). */
const shareStamp = () => new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()
/** Confidence word → dot-chip certainty state (faceoff-dot language). */
const confState = (word?: string): DotState =>
  word === 'high' ? 'filled' : word === 'proxy' || word === 'low' ? 'projected' : 'leaning'
const confTone = (word?: string): 'high' | 'medium' | 'low' =>
  word === 'high' ? 'high' : word === 'proxy' || word === 'low' ? 'low' : 'medium'

/** Everything the result panel shows derives from one grade response (the shown deal). */
function derive(g: ContractGrade) {
  const breakEven = g.fair_aav_breakeven ?? (g.cost_dollars > 0 ? (g.value_dollars * g.cap_hit) / g.cost_dollars : g.fair_aav)
  const fairNow = g.fair_aav_now ?? g.fair_aav
  const deltaVsFair = g.cap_hit - breakEven                 // >0 = over fair (cost exceeds break-even)
  const pctOverFair = breakEven > 0 ? deltaVsFair / breakEven : 0
  const ratio = g.cost_dollars > 0 ? g.total_discounted_surplus / g.cost_dollars : 0  // = the verdict's %
  const bandHalf = Math.round((g.surplus_high - g.surplus_low) / 2)
  const capShareNow = g.cap_share_schedule.length ? g.cap_share_schedule[0].actual_share : 0
  const playerVal = g.player_value_surplus ?? (g.total_discounted_surplus - (g.cap_growth_surplus ?? 0))
  const capGrowth = g.cap_growth_surplus ?? 0
  const firstWar = g.cap_share_schedule[0]?.projected_war ?? null
  const lastWar = g.cap_share_schedule[g.cap_share_schedule.length - 1]?.projected_war ?? null
  const age0 = g.cap_share_schedule[0]?.age ?? null
  const ageN = g.cap_share_schedule[g.cap_share_schedule.length - 1]?.age ?? null
  return { breakEven, fairNow, deltaVsFair, pctOverFair, ratio, bandHalf, capShareNow, playerVal, capGrowth, firstWar, lastWar, age0, ageN }
}
type Derived = ReturnType<typeof derive>

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

/**
 * §1.4 — the paid-vs-worth chart, four marks only:
 *  · solid ink line   = the flat cap hit (the contractual fact)
 *  · dashed blue line = projected fair value, with its faint confidence ribbon
 *  · blue fill (8%) where fair exceeds cap, red fill where cap exceeds fair
 *  · NOW as a mono label on a neutral hairline
 * Season + age x labels are mono; the caption explains all four.
 */
function PaidVsWorthChart({ g, unit, mini = false }: { g: ContractGrade; unit: '$' | '%'; mini?: boolean }) {
  const panelH = useChartPanelHeight()
  const height = mini ? 220 : panelH
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
  const vals = data.flatMap((r) => [r.paid, r.fair, r.bandLo, r.bandLo + r.bandSpan])
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = Math.max((hi - lo) * 0.18, hi * 0.04)
  const domain: [number, number] = [Math.max(0, lo - pad), hi + pad]
  const axisFmt = (v: number) => unit === '$' ? `$${v.toFixed(0)}M` : `${v.toFixed(0)}%`
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 12, right: mini ? 12 : 56, bottom: 4, left: 4 }}>
        <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" />
        <XAxis dataKey="season" stroke="var(--color-border)"
          tick={(props: any) => {
            const row = data[props.index]
            return (
              <g transform={`translate(${props.x},${props.y})`}>
                <text dy={12} textAnchor="middle" fontSize={11} fontFamily="var(--font-mono)" fill="var(--color-text-secondary)">{props.payload.value}</text>
                {row?.age != null && <text dy={25} textAnchor="middle" fontSize={9} fontFamily="var(--font-mono)" fill="var(--color-text-muted)">age {row.age}</text>}
              </g>
            )
          }} height={mini ? 28 : 40} />
        <YAxis domain={domain} allowDataOverflow stroke="var(--color-border)"
          tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} tickFormatter={axisFmt} width={48} />
        <RTooltip content={<ChartTip unit={unit} />} />
        {/* confidence ribbon on the projected (dashed) fair line — pale crease blue (doc calls for #D9E4E9) */}
        <Area dataKey="bandLo" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} />
        <Area dataKey="bandSpan" stackId="band" stroke="none" fill="var(--crease)" fillOpacity={0.9} isAnimationActive={false} />
        {/* worth-vs-paid fills at 8% — blue where fair beats cap, red where cap beats fair */}
        <Area dataKey="base" stackId="g" stroke="none" fill="transparent" isAnimationActive={false} />
        <Area dataKey="surplus" stackId="g" stroke="none" fill="var(--color-data-positive)" fillOpacity={0.08} animationDuration={400} />
        <Area dataKey="deficit" stackId="g" stroke="none" fill="var(--color-data-negative)" fillOpacity={0.08} animationDuration={400} />
        {/* NOW — mono label on a neutral hairline at the first (this-season) column */}
        {data.length > 0 && (
          <ReferenceLine x={data[0].season} stroke="var(--color-border-strong)" strokeWidth={1}>
            {!mini && <Label value="NOW" position="insideTopLeft" fill="var(--color-text-muted)"
              style={{ fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }} />}
          </ReferenceLine>
        )}
        {/* solid ink line = the cap hit (contractual fact) */}
        <Line type="monotone" dataKey="paid" stroke="var(--color-text-primary)" strokeWidth={2} dot={false} animationDuration={400}>
          {!mini && <Label value="cap hit" position="right" dy={12} fill="var(--color-text-secondary)"
            style={{ fontSize: 13, fontStyle: 'italic', fontFamily: 'var(--font-display)' }} />}
        </Line>
        {/* dashed blue line = projected fair value */}
        <Line type="monotone" dataKey="fair" stroke="var(--color-data-positive)" strokeWidth={2}
          strokeDasharray="5 4" dot={false} animationDuration={400}>
          {!mini && <Label value="fair value" position="right" dy={-3} fill="var(--color-data-positive)"
            style={{ fontSize: 13, fontStyle: 'italic', fontFamily: 'var(--font-display)' }} />}
        </Line>
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** A judged figure in the figures row — no box, valence-colored value, tooltip term, caption. */
function Figure({ label, value, valence, caption, tip }: {
  label: string; value: string; valence?: Valence; caption?: string; tip?: string
}) {
  return (
    <div className="cg-figure">
      <div className="cg-figure__head">
        <span className="cg-figure__label">{label}</span>
        {tip && <Tooltip content={tip}><Info size={12} className="cg-figure__info" /></Tooltip>}
      </div>
      <div className={`cg-figure__value mono${valence ? ` cg-val--${valence}` : ''}`}>{value}</div>
      {caption && <div className="cg-figure__caption">{caption}</div>}
    </div>
  )
}

/** A single receipt line: valence dot + generated sentence (§1.2). */
function Receipt({ valence, children }: { valence: Valence; children: React.ReactNode }) {
  const color = valence === 'pos' ? 'var(--color-data-positive)'
    : valence === 'neg' ? 'var(--color-data-negative)' : 'var(--color-text-muted)'
  return (
    <div className="cg-receipt">
      <span className="cg-receipt__dot" style={{ background: color }} />
      <span className="cg-receipt__text">{children}</span>
    </div>
  )
}

/** §1.5c — the closest market comparables (served with the grade). Rows open that deal in the grader. */
function Comparables({ g, onOpen }: { g: ContractGrade; onOpen: (id: number, name: string) => void }) {
  const comps = (g.comparables ?? []).slice(0, 4)
  if (!comps.length) return null
  return (
    <table className="gamesheet gamesheet--dense cg-comps">
      <thead>
        <tr>
          <th>Comparable</th>
          <th className="num">Deal</th>
          <th className="num">Proj</th>
          <th className="num">Grade</th>
          <th className="num">Surplus</th>
        </tr>
      </thead>
      <tbody>
        {comps.map((c) => {
          const v = c.grade ? GRADE_VALENCE[c.grade] : undefined
          return (
            <tr key={c.player_id} onClick={() => onOpen(c.player_id, c.name)} className="cg-comps__row">
              <td>
                <span className="cg-comps__name">{c.name}</span>
                {/* TODO(data): comps carry pos · team · signed year + PV-restated surplus — not on ComparableContract. */}
              </td>
              <td className="num mono">{fmtM(c.aav)} × {c.term}y</td>
              <td className="num mono">{c.caliber != null ? `${Math.round(c.caliber * 100)}` : '—'}</td>
              <td className="num">{c.grade ? <span className={`cg-grade-inline cg-val--${v}`}>{c.grade}</span> : '—'}</td>
              <td className="num mono">—</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default function ContractGrader() {
  usePageTitle('Contracts')
  const [params, setParams] = useSearchParams()
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null)
  const [contract, setContract] = useState<PlayerContract | null>(null)
  const [actualGrade, setActualGrade] = useState<ContractGrade | null>(null)
  const [hypoGrade, setHypoGrade] = useState<ContractGrade | null>(null)
  const [mode, setMode] = useState<'actual' | 'hypothetical'>('actual')
  const [capM, setCapM] = useState(5)
  const [term, setTerm] = useState(4)
  const [unit, setUnit] = useState<'$' | '%'>('$')
  const [loading, setLoading] = useState(false)
  const [showWork, setShowWork] = useState(true)   // §1.5 default expanded

  // §2 — old "?view=leaderboards" 301s to the market lens.
  const rawView = params.get('view')
  const lens: 'grade' | 'market' = rawView === 'market' || rawView === 'leaderboards' ? 'market' : 'grade'
  const setLens = (v: 'grade' | 'market') => {
    const next = new URLSearchParams(params)
    if (v === 'grade') next.delete('view'); else next.set('view', 'market')
    setParams(next, { replace: true })
  }

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
            setMode('hypothetical')
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

  /** Deep-link / comp / market entry: load a player into the grader and switch to the grade lens. */
  const openInGrader = useCallback((id: number, name: string) => {
    setLens('grade')
    onSelect({ player_id: id, name })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onSelect])

  useEffect(() => {
    let active = true
    searchPlayers('McDavid', 1).then((r) => { if (active && r.length) onSelect(r[0]) }).catch(() => {})
    return () => { active = false }
  }, [onSelect])

  // Live grade for the hypothetical builder (debounced) — the grade updates as the numbers change.
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

  const posLabel = player?.position ?? grade?.position ?? null
  const teamLabel = player?.team_abbrev ?? contract?.contract_team ?? null

  return (
    <PageLayout>
      <div className="cg-page">
        <PageCard
          eyebrow="Studio"
          title="Contract grader"
          subtitle="Grade any deal against the aging curve and the market — the grade updates as you change the numbers."
          controls={
            <Tabs
              options={[{ value: 'grade', label: 'Grade a contract' }, { value: 'market', label: 'The market' }]}
              value={lens} onChange={(v) => setLens(v as 'grade' | 'market')}
            />
          }
        >
          {lens === 'grade' ? (
            <div className="cg-grade-layout">
              {/* §1.1 — the deal panel (left, 320px) */}
              <Panel className="cg-deal">
                <Tabs
                  options={[
                    { value: 'actual', label: 'Actual deal', disabled: !hasActual },
                    { value: 'hypothetical', label: 'Hypothetical' },
                  ]}
                  value={effectiveMode}
                  onChange={(v) => setMode(v as 'actual' | 'hypothetical')}
                />

                <div className="cg-deal__id">
                  {player && (
                    <>
                      <PlayerAvatar id={player.player_id} team={teamLabel ?? undefined} name={player.name ?? ''} size={44} />
                      <div className="cg-deal__meta">
                        <div className="cg-deal__name">{player.name}</div>
                        <div className="cg-deal__ctx">
                          {[posLabel, d?.age0 != null ? `age ${d.age0}` : null, teamLabel].filter(Boolean).join(' · ')}
                        </div>
                      </div>
                    </>
                  )}
                  <div className="cg-deal__change">
                    <PlayerPicker onSelect={onSelect} placeholder="Change ▾" />
                  </div>
                </div>

                {grade && d?.firstWar != null && (
                  <p className="cg-deal__proj">
                    Projected <span className="mono">{war1(d.firstWar)} WAR</span> now, aging to{' '}
                    <span className="mono">~{war1(d.lastWar ?? d.firstWar)}</span> by {seasonStr(startYear(grade.season) + grade.term_years - 1)}
                  </p>
                )}

                {/* AAV + % of cap */}
                <div className="cg-field">
                  <div className="cg-field__label">Cap hit (AAV)</div>
                  <div className="cg-field__row">
                    {effectiveMode === 'actual' && hasActual ? (
                      <div className="cg-field__value mono cg-field__value--locked">{fmtM(contract!.cap_hit!)}</div>
                    ) : (
                      <div className="cg-field__value mono">{fmtM(Math.round(capM * 1e6))}</div>
                    )}
                    {d && grade && <span className="cg-field__aside mono">{pct1(d.capShareNow)} of cap</span>}
                  </div>
                  {!(effectiveMode === 'actual' && hasActual) && (
                    <input type="range" min={0.75} max={20} step={0.25} value={capM}
                      onChange={(e) => setCapM(Number(e.target.value))} className="cg-slider" />
                  )}
                </div>

                {/* Term */}
                <div className="cg-field">
                  <div className="cg-field__label">Term</div>
                  <div className="cg-term">
                    <button onClick={() => setTerm((t) => Math.max(1, t - 1))}
                      disabled={effectiveMode === 'actual' || term <= 1} aria-label="Fewer years">−</button>
                    <span className="mono">{(effectiveMode === 'actual' && hasActual ? contract!.remaining_years! : term)} yrs</span>
                    <button onClick={() => setTerm((t) => Math.min(8, t + 1))}
                      disabled={effectiveMode === 'actual' || term >= 8} aria-label="More years">+</button>
                  </div>
                  {grade && (
                    <div className="cg-field__caption mono">
                      {(() => {
                        const exp = effectiveMode === 'actual' && contract?.expiry_year ? contract.expiry_year : startYear(grade.season) + grade.term_years
                        return `expires ${exp}${d?.age0 != null && d?.ageN != null ? ` · ages ${d.age0}–${d.ageN} across the term` : ''}`
                      })()}
                    </div>
                  )}
                </div>

                <p className="cg-deal__foot">
                  The grade updates as you change the numbers. There's no submit step.
                </p>
              </Panel>

              {/* the result */}
              <div className="cg-result">
                {loading || !grade || !d ? (
                  <ResultSkeleton />
                ) : (
                  <>
                    <Scoreboard grade={grade} d={d} effectiveMode={effectiveMode} playerName={player?.name} />
                    <FiguresRow grade={grade} d={d} />
                    <ChartBlock grade={grade} d={d} unit={unit} setUnit={setUnit} />
                    <TheWork grade={grade} d={d} posLabel={posLabel} show={showWork} setShow={setShowWork} onOpen={openInGrader} />
                  </>
                )}
              </div>
            </div>
          ) : (
            <Market onOpen={openInGrader} />
          )}
        </PageCard>
      </div>
    </PageLayout>
  )
}

/** §1.2 — the scoreboard (one Panel). */
function Scoreboard({ grade, d, effectiveMode, playerName }: {
  grade: ContractGrade; d: Derived; effectiveMode: 'actual' | 'hypothetical'; playerName?: string | null
}) {
  const v = GRADE_VALENCE[grade.grade] ?? 'neutral'
  const surplus = grade.total_discounted_surplus
  const pct = Math.abs(Math.round(d.pctOverFair * 100))
  const framing = d.deltaVsFair <= 0 ? `${pct}% under fair value` : `${pct}% over fair value`
  const dealWord = effectiveMode === 'actual' ? 'actual contract' : 'hypothetical'
  return (
    <Panel className="cg-scoreboard">
      <div className="cg-scoreboard__top">
        <span className="cg-scoreboard__eyebrow">THE GRADE · {shareStamp()} · {dealWord}</span>
        <div className="cg-scoreboard__meta">
          <DotChip label={`${grade.confidence} confidence`} state={confState(grade.confidence)}
            color={grade.confidence === 'high' ? 'var(--line-blue)' : 'var(--color-text-muted)'} />
          <Tooltip content="Grade = present-value surplus vs cost over the term. PV discounts each future season to today's dollars. Bands: A ≥ +30%, B ≥ +12%, C within ±12%, D ≥ −30%, F below.">
            <button className="cg-scoreboard__how" type="button">How we grade contracts</button>
          </Tooltip>
          <ShareActions kicker={`CONTRACT GRADE · ${shareStamp()}`} verdict={grade.verdict}
            confidence={{ tone: confTone(grade.confidence), word: grade.confidence,
              phrase: grade.war_sd != null ? `±${war1(grade.war_sd)} WAR` : undefined }}
            shareName={`contract-${playerName?.replace(/\s+/g, '-').toLowerCase() ?? 'grade'}`} />
        </div>
      </div>

      <div className="cg-scoreboard__verdict">
        <span className={`cg-grade-letter cg-val--${v}`}>{grade.grade}</span>
        <p className="cg-verdict-text">
          <b className={`cg-val--${v}`}>{GRADE_WORD[grade.grade] ?? grade.verdict}</b>{' '}
          At {framing}, it returns{' '}
          <span className={`mono cg-val--${valOf(surplus)}`}>{fmtMsign(surplus)}</span>{' '}
          in present-value surplus over the term.
        </p>
      </div>

      <div className="cg-scoreboard__hairline" />

      <div className="cg-receipts">
        <Receipt valence={valOf(d.playerVal)}>
          Player value {d.playerVal >= 0 ? 'out-earns' : 'trails'} the cap hit by <span className="mono">{fmtMsign(d.playerVal)}</span>
        </Receipt>
        <Receipt valence={valOf(d.capGrowth)}>
          Flat cap hit vs a rising cap adds <span className="mono">{fmtMsign(d.capGrowth)}</span>
        </Receipt>
        <Receipt valence="neutral">
          Projected <span className="mono">{d.firstWar != null ? war1(d.firstWar) : '—'}→{d.lastWar != null ? war1(d.lastWar) : '—'} WAR</span> across the term
        </Receipt>
        <Receipt valence={valOf(-d.deltaVsFair)}>
          Fair AAV this term ≈ <span className="mono">{fmtM(d.breakEven)}</span> ({fmtMsign(-d.deltaVsFair)} vs the cap hit)
        </Receipt>
        <div className="cg-receipts__caveat">
          <Receipt valence="neutral">
            Wide band: ±<span className="mono">{fmtM(d.bandHalf).replace('$', '$')}</span> at {grade.confidence} confidence — read the grade as a range.
          </Receipt>
        </div>
      </div>
    </Panel>
  )
}

/** §1.3 — figures row: four judged figures, no boxes. */
function FiguresRow({ grade, d }: { grade: ContractGrade; d: Derived }) {
  return (
    <div className="cg-figures">
      <Figure label="Surplus PV" value={fmtMsign(grade.total_discounted_surplus)} valence={valOf(grade.total_discounted_surplus)}
        caption={`± ${fmtM(d.bandHalf)} band · ${grade.total_discounted_surplus >= 0 ? '+' : '−'}${Math.abs(Math.round(d.ratio * 100))}% vs cost`}
        tip="Projected value minus cost, present-valued over the term." />
      <Figure label="Fair AAV this term" value={fmtM(d.breakEven)} valence={valOf(-d.deltaVsFair)}
        caption={`${fmtMsign(-d.deltaVsFair)} vs the cap hit`}
        tip="The flat AAV that breaks even on present-value surplus over this term." />
      <Figure label="Cap hit" value={fmtM(grade.cap_hit)}
        caption={`${grade.term_years} yrs · ${pct1(d.capShareNow)} of cap`} />
      <Figure label="Fair AAV today" value={fmtM(d.fairNow)}
        caption="point-in-time, this season"
        tip="What the market would pay for this production this season (year-0), distinct from the term figure." />
    </div>
  )
}

/** §1.4 — chart block with the $ / % text-tabs and the one caption line. */
function ChartBlock({ grade, d, unit, setUnit }: {
  grade: ContractGrade; d: Derived; unit: '$' | '%'; setUnit: (u: '$' | '%') => void
}) {
  return (
    <div className="cg-chart-block">
      <div className="cg-chart-units">
        <Tabs options={[{ value: '$', label: '$' }, { value: '%', label: '% of cap' }]} value={unit} onChange={(v) => setUnit(v as '$' | '%')} />
      </div>
      <ChartPanel
        expandable={false}
        title={`Paid vs worth — ${d.deltaVsFair <= 0 ? 'value beats the cap hit' : 'the cap hit outruns the value'} across the term`}
        subtitle="Projected fair value against the flat cap hit, by contract season"
        footer={
          <p className="cg-chart-caption">
            Solid ink is the cap hit; the dashed blue line is projected fair value with its confidence ribbon.
            Blue fill marks seasons worth more than paid, red where the cap hit outruns the value; NOW is this season.
          </p>
        }
      >
        <PaidVsWorthChart g={grade} unit={unit} />
      </ChartPanel>
    </div>
  )
}

/** §1.5 — the work (collapsible, default expanded). */
function TheWork({ grade, d, posLabel, show, setShow, onOpen }: {
  grade: ContractGrade; d: Derived; posLabel: string | null
  show: boolean; setShow: (v: boolean) => void; onOpen: (id: number, name: string) => void
}) {
  const segs: StackSegment[] = [
    { key: 'player', label: 'Player value', value: d.playerVal, color: 'var(--color-data-1)' },
    { key: 'capgrowth', label: 'Cap growth', value: d.capGrowth, color: 'var(--color-data-neutral)' },
  ]
  const maxAbs = Math.max(Math.abs(d.playerVal), Math.abs(d.capGrowth), Math.abs(grade.total_discounted_surplus), 1)
  const posName = posLabel === 'D' ? 'defensemen' : posLabel === 'G' ? 'goalies' : 'forwards'
  const slide = d.firstWar != null && d.lastWar != null ? d.firstWar - d.lastWar : null
  return (
    <div className="cg-work">
      <button className="cg-work__toggle" onClick={() => setShow(!show)}>
        <ChevronDown size={15} className={show ? 'cg-work__chev cg-work__chev--open' : 'cg-work__chev'} />
        The work
      </button>
      {show && (
        <div className="cg-work__body">
          {/* (a) where the surplus comes from */}
          <section className="cg-work__part">
            <h3 className="cg-work__title">Where the surplus comes from</h3>
            <ComponentStackBar segments={segs} total={grade.total_discounted_surplus} domain={[-maxAbs, maxAbs]}
              formatValue={(v) => fmtMsign(v)} />
            <p className="cg-work__note">
              Player value is the player out-producing his cap hit; cap growth is the flat cap hit shrinking as a
              share of a rising cap. Both are real value to the team.
            </p>
          </section>

          {/* (b) aging */}
          <section className="cg-work__part">
            <h3 className="cg-work__title">Aging</h3>
            <p className="cg-work__prose">
              The aging curve for {posName} bends down through the back half of this term.
              {d.firstWar != null && d.lastWar != null && (
                <> His projected production slides from <span className="mono">{war1(d.firstWar)}</span> to{' '}
                  <span className="mono">{war1(d.lastWar)} WAR</span>
                  {slide != null && slide > 0.05 ? `, a ${war1(slide)}-WAR drop across the deal.` : ' across the deal.'}</>
              )}
            </p>
          </section>

          {/* (c) closest market comparables */}
          {grade.comparables && grade.comparables.length > 0 && (
            <section className="cg-work__part">
              <h3 className="cg-work__title">Closest market comparables</h3>
              <Comparables g={grade} onOpen={onOpen} />
              <p className="cg-work__note">
                The nearest signed deals by projection, position, and age at signing. Open any row to grade that deal.
              </p>
            </section>
          )}
        </div>
      )}
    </div>
  )
}

function ResultSkeleton() {
  return (
    <>
      <SkeletonLoader height={196} />
      <div className="cg-figures">{[0, 1, 2, 3].map((i) => <SkeletonLoader key={i} height={72} />)}</div>
      <SkeletonLoader height={320} />
      <SkeletonLoader height={160} />
    </>
  )
}

/* ============================================================================
   §2 — The Market
   ========================================================================== */

type QuickView = 'all' | 'steals' | 'albatross' | 'expiring'
type SortKey = 'surplus' | 'aav' | 'yrs' | 'grade'

const posOf = (a: TradeableAsset): 'C' | 'W' | 'D' | 'G' | '?' => {
  const p = (a.pos_or_slot ?? '').toUpperCase()
  if (p.startsWith('G')) return 'G'
  if (p.startsWith('D')) return 'D'
  if (p === 'C') return 'C'
  if (p.includes('W') || p === 'LW' || p === 'RW' || p === 'F') return 'W'
  return '?'
}

/** A 64px micro-band on a fixed ±$10M domain with a center tick, dot colored by sign (§2.2). */
function MicroBand({ surplus }: { surplus: number }) {
  const dom = 10e6
  const clamped = Math.max(-dom, Math.min(dom, surplus))
  const pct = 50 + (clamped / dom) * 50
  const color = surplus >= 0 ? 'var(--color-data-positive)' : 'var(--color-data-negative)'
  return (
    <span className="cg-microband">
      <span className="cg-microband__center" />
      <span className="cg-microband__dot" style={{ left: `${pct}%`, background: color }} />
    </span>
  )
}

function Market({ onOpen }: { onOpen: (id: number, name: string) => void }) {
  const [rows, setRows] = useState<TradeableAsset[] | null>(null)
  const [quick, setQuick] = useState<QuickView>('all')
  const [pos, setPos] = useState<'all' | 'C' | 'W' | 'D' | 'G'>('all')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<SortKey>('surplus')
  const [limit, setLimit] = useState(25)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [expandedGrade, setExpandedGrade] = useState<ContractGrade | null>(null)

  useEffect(() => {
    // Baseline population: the surplus rankings from both ends form the active-contract board.
    Promise.all([getSurplusRankings('surplus', 150), getSurplusRankings('overpaid', 150)])
      .then(([best, worst]) => {
        const byId = new Map<string, TradeableAsset>()
        for (const a of [...best, ...worst]) if (a.player_id) byId.set(a.asset_id, a)
        setRows([...byId.values()])
      })
      .catch(() => setRows([]))
  }, [])

  const filtered = useMemo(() => {
    let r = (rows ?? []).filter((a) => (a.cap_hit ?? 0) >= 1e6)   // min $1M AAV
    if (quick === 'steals') r = r.filter((a) => a.grade === 'A')
    else if (quick === 'albatross') r = r.filter((a) => a.grade === 'D' || a.grade === 'F')
    else if (quick === 'expiring') r = []   // TODO(data): expiry_year isn't on TradeableAsset — no final-year filter served.
    if (pos !== 'all') r = r.filter((a) => posOf(a) === pos)
    if (q.trim()) r = r.filter((a) => a.label.toLowerCase().includes(q.trim().toLowerCase()))
    const dir = 1
    r = [...r].sort((a, b) => {
      if (sort === 'aav') return (b.cap_hit ?? 0) - (a.cap_hit ?? 0)
      if (sort === 'yrs') return (b.remaining_years ?? 0) - (a.remaining_years ?? 0)
      if (sort === 'grade') return (a.grade ?? 'Z').localeCompare(b.grade ?? 'Z')
      return ((b.surplus_dollars ?? 0) - (a.surplus_dollars ?? 0)) * dir
    })
    return r
  }, [rows, quick, pos, q, sort])

  const shown = filtered.slice(0, limit)

  const toggleRow = (a: TradeableAsset) => {
    if (expandedId === a.asset_id) { setExpandedId(null); setExpandedGrade(null); return }
    setExpandedId(a.asset_id); setExpandedGrade(null)
    if (a.player_id && a.cap_hit && a.remaining_years) {
      gradeContract(a.player_id, a.cap_hit, Math.min(8, a.remaining_years)).then(setExpandedGrade).catch(() => {})
    }
  }

  const arrow = (key: SortKey) => (sort === key ? ' ↓' : '')

  return (
    <div className="cg-market">
      <div className="cg-market__filters">
        <Tabs
          options={[
            { value: 'all', label: 'All contracts' }, { value: 'steals', label: 'Steals' },
            { value: 'albatross', label: 'Albatrosses' }, { value: 'expiring', label: 'Expiring 2026' },
          ]}
          value={quick} onChange={(v) => { setQuick(v as QuickView); setLimit(25) }}
        />
        <div className="cg-market__row2">
          <Tabs
            options={[
              { value: 'all', label: 'All' }, { value: 'C', label: 'C' }, { value: 'W', label: 'W' },
              { value: 'D', label: 'D' }, { value: 'G', label: 'G' },
            ]}
            value={pos} onChange={(v) => setPos(v as typeof pos)}
          />
          <input className="cg-market__search" placeholder="Search a player…" value={q}
            onChange={(e) => { setQ(e.target.value); setLimit(25) }} />
        </div>
      </div>

      {rows === null ? (
        <SkeletonLoader height={400} />
      ) : quick === 'expiring' ? (
        <p className="cg-market__empty">Contract expiry isn't served on the market board yet.</p>
      ) : (
        <>
          <table className="gamesheet cg-market__table">
            <thead>
              <tr>
                <th>Player</th>
                <th className="num cg-market__sortable" onClick={() => setSort('grade')}>Grade{arrow('grade')}</th>
                <th className="num cg-market__sortable" onClick={() => setSort('aav')}>AAV{arrow('aav')}</th>
                <th className="num cg-market__sortable" onClick={() => setSort('yrs')}>Yrs{arrow('yrs')}</th>
                <th className="num cg-market__hide-sm">Expires</th>
                <th className="num cg-market__hide-sm">Fair AAV</th>
                <th className="num cg-market__sortable" onClick={() => setSort('surplus')}>Surplus PV{arrow('surplus')}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((a) => {
                const active = sort
                const surplus = a.surplus_dollars ?? 0
                const gv = a.grade ? GRADE_VALENCE[a.grade] : undefined
                const isOpen = expandedId === a.asset_id
                return (
                  <Fragment key={a.asset_id}>
                    <tr onClick={() => toggleRow(a)}
                      aria-selected={isOpen} className="cg-market__tr">
                      <td>
                        <span className="cg-market__name">{a.label}</span>
                        <span className="cg-market__sub mono">{[posOf(a) !== '?' ? posOf(a) : null, a.org_team].filter(Boolean).join(' · ')}</span>
                      </td>
                      <td className="num">{a.grade ? <span className={`cg-grade-inline cg-val--${gv}`}>{a.grade}</span> : '—'}</td>
                      <td className={`num mono${active === 'aav' ? ' cg-market__active' : ''}`}>{a.cap_hit != null ? fmtM(a.cap_hit) : '—'}</td>
                      <td className={`num mono${active === 'yrs' ? ' cg-market__active' : ''}`}>{a.remaining_years ?? '—'}</td>
                      {/* TODO(data): Expires + Fair AAV per row aren't on TradeableAsset (no market endpoint). */}
                      <td className="num mono cg-market__hide-sm">—</td>
                      <td className="num mono cg-market__hide-sm">—</td>
                      <td className={`num cg-market__surplus${active === 'surplus' ? ' cg-market__active' : ''}`}>
                        <span className={`mono cg-val--${valOf(surplus)}`}>{fmtMsign(surplus)}</span>
                        <MicroBand surplus={surplus} />
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="cg-market__expand">
                        <td colSpan={7}>
                          <MarketExpansion asset={a} grade={expandedGrade} onOpen={onOpen} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
          {filtered.length > limit && (
            <button className="cg-market__more" onClick={() => setLimit((l) => l + 25)}>Show more</button>
          )}
          <p className="cg-market__foot">
            Active contracts, minimum $1M AAV · {filtered.length} deals.
          </p>
        </>
      )}
    </div>
  )
}

/** §2.3 — the expanded row: verdict + receipts + actions (left), mini chart (right). */
function MarketExpansion({ asset, grade, onOpen }: {
  asset: TradeableAsset; grade: ContractGrade | null; onOpen: (id: number, name: string) => void
}) {
  if (!grade) return <div className="cg-market__loading"><SkeletonLoader height={140} /></div>
  const d = derive(grade)
  const v = GRADE_VALENCE[grade.grade] ?? 'neutral'
  const pct = Math.abs(Math.round(d.pctOverFair * 100))
  const framing = d.deltaVsFair <= 0 ? `${pct}% under fair value` : `${pct}% over fair value`
  const nearest = grade.comparables?.[0]
  return (
    <div className="cg-market__dossier">
      <div className="cg-market__dleft">
        <p className="cg-verdict-text">
          <b className={`cg-val--${v}`}>{GRADE_WORD[grade.grade] ?? grade.verdict}</b>{' '}
          At {framing}, it returns{' '}
          <span className={`mono cg-val--${valOf(grade.total_discounted_surplus)}`}>{fmtMsign(grade.total_discounted_surplus)}</span> over the term.
        </p>
        <div className="cg-receipts cg-receipts--tight">
          <Receipt valence="neutral">
            Projected <span className="mono">{d.firstWar != null ? war1(d.firstWar) : '—'}→{d.lastWar != null ? war1(d.lastWar) : '—'} WAR</span> across the term
          </Receipt>
          <Receipt valence={valOf(-d.deltaVsFair)}>
            Fair AAV this term ≈ <span className="mono">{fmtM(d.breakEven)}</span> ({fmtMsign(-d.deltaVsFair)} vs cap hit)
          </Receipt>
          {nearest && (
            <Receipt valence={nearest.grade ? GRADE_VALENCE[nearest.grade] : 'neutral'}>
              Nearest comp {nearest.name} ({fmtM(nearest.aav)} × {nearest.term}y){nearest.grade ? <span className={`cg-grade-inline cg-val--${GRADE_VALENCE[nearest.grade]}`}> {nearest.grade}</span> : null}
            </Receipt>
          )}
        </div>
        <div className="cg-market__actions">
          <button className="cg-btn cg-btn--primary" onClick={() => asset.player_id && onOpen(asset.player_id, asset.label)}>
            Open in the grader <ArrowRight size={13} />
          </button>
          {asset.player_id && <Link className="cg-btn" to={`/players/${asset.player_id}`}>Player profile</Link>}
          {asset.player_id && <Link className="cg-btn" to={`/studio/trades/build?add=${asset.player_id}`}>Build a trade around it</Link>}
        </div>
      </div>
      <div className="cg-market__dright">
        <PaidVsWorthChart g={grade} unit="$" mini />
        <p className="cg-market__dcap">Solid ink is the cap hit; dashed blue is projected fair value.</p>
      </div>
    </div>
  )
}
