/**
 * Draft Value (Handoff 5) — the empirical pick-value curve, the "85%" theory test, and the
 * steal/bust board. Every number is realized 7-year-window pWAR (same WAR units as the value stack),
 * an explicit wide-band estimate before 2021. Reuses ChartPanel, PlayerAvatar, Tabs, Tooltip.
 */
import { useEffect, useMemo, useState } from 'react'
import { usePageTitle } from '../hooks/usePageTitle'
import { Link, useNavigate } from 'react-router-dom'
import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ReferenceDot, Label,
} from 'recharts'
import {
  PageLayout, PageCard, ChartPanel, PlayerAvatar, Tabs, Tooltip, SkeletonLoader,
} from '../components/common'
import { useChartPanelHeight } from '../components/common/ChartPanel'
import {
  getPickValueCurve, getDraftTheorySummary, getDraftBoard,
  PickValueCurveRow, DraftTheorySummaryRow, DraftBoardRow,
} from '../api/draft'
import './DraftValue.css'

const pct0 = (v: number) => `${Math.round(v * 100)}%`
const RANGE_LABEL: Record<string, string> = {
  '1-10': 'Top 10', '11-31': 'Rest of Rd 1', 'R2': 'Round 2', 'R3-7': 'Rounds 3–7', 'POOLED': 'All picks',
}

// ---------------------------------------------------------------- curve chart
function CurveChartTip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="dv-charttip">
      <div className="dv-charttip__head">Pick #{d.overall_pick} · {d.n} drafted</div>
      <div className="dv-charttip__row"><span>Expected (mean)</span><span className="mono">{d.ev_mean_smooth.toFixed(1)} WAR</span></div>
      <div className="dv-charttip__row"><span>Median outcome</span><span className="mono">{d.ev_median.toFixed(1)} WAR</span></div>
      <div className="dv-charttip__row dv-charttip__row--muted"><span>Middle 80% (p10–p90)</span><span className="mono">{d.p10.toFixed(1)}–{d.p90.toFixed(1)}</span></div>
      <div className="dv-charttip__row dv-charttip__row--muted"><span>Never play NHL</span><span className="mono">{pct0(d.share_never_nhl)}</span></div>
    </div>
  )
}

// Bounds-aware line label: recharts' position="right" anchors at the line's right end (overall pick
// ~217, where the curves converge near 0) and clips past the chart's right edge. Instead anchor at the
// line's high/left end, just inside the plot, where the two lines are well separated.
function lineLabel(text: string, fill: string, fontSize: number, fontWeight: number) {
  return ({ viewBox }: any) => {
    if (!viewBox) return null
    return (
      <text x={viewBox.x + 6} y={viewBox.y + 12} fill={fill} fontSize={fontSize} fontWeight={fontWeight} textAnchor="start">
        {text}
      </text>
    )
  }
}

// Bounds-aware annotation label: sits above the dot (below when the dot is already high), and clamps its
// text anchor to the side the dot is on so a name near an edge stays inside the plot.
function annotationLabel(a: Annotation, yMax: number, fill: string) {
  return ({ viewBox }: any) => {
    if (!viewBox) return null
    const cx = (viewBox.x ?? 0) + (viewBox.width ?? 0) / 2
    const cy = (viewBox.y ?? 0) + (viewBox.height ?? 0) / 2
    const dy = a.realized_value <= yMax * 0.85 ? -8 : 16
    const anchor = a.overall_pick <= 4 ? 'start' : a.overall_pick >= 140 ? 'end' : 'middle'
    const dx = anchor === 'start' ? 6 : anchor === 'end' ? -6 : 0
    return (
      <text x={cx + dx} y={cy + dy} fill={fill} fontSize={10} fontWeight={600} textAnchor={anchor}>
        {a.label}
      </text>
    )
  }
}

// §S7: a curve landmark — a small ink dot with a 1px leader line and a Newsreader-italic callout.
// Leader lines drop below 900px (narrow), where only the dot stays.
function landmarkLabel(text: string, narrow: boolean, up = true) {
  return ({ viewBox }: any) => {
    if (!viewBox) return null
    const x = viewBox.x ?? 0
    const y = viewBox.y ?? 0
    const len = 22
    const ty = up ? y - len - 4 : y + len + 12
    return (
      <g>
        {!narrow && <line x1={x} y1={y} x2={x} y2={up ? y - len : y + len} stroke="var(--color-border-strong)" strokeWidth={1} />}
        <circle cx={x} cy={y} r={3} fill="var(--color-text-primary)" opacity={0.5} />
        {!narrow && (
          <text x={x} y={ty} textAnchor="middle"
            style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, fill: 'var(--color-text-secondary)' }}>
            {text}
          </text>
        )}
      </g>
    )
  }
}

function CurveChart({ curve, annotations }: { curve: PickValueCurveRow[]; annotations: Annotation[] }) {
  const height = useChartPanelHeight()
  const narrow = typeof window !== 'undefined' && window.innerWidth < 900
  // Split the expected curve: solid where the sample is dense (fitted), dashed in the sparse tail.
  const boundaryPick = [...curve].reverse().find((r) => r.n >= 30)?.overall_pick ?? curve[curve.length - 1]?.overall_pick ?? 217
  const data = curve.map((r) => ({
    ...r,
    bandLo: r.p10_smooth,
    bandSpan: Math.max(0, r.p90_smooth - r.p10_smooth),
    evFit: r.overall_pick <= boundaryPick ? r.ev_mean_smooth : null,
    evExtrap: r.overall_pick >= boundaryPick ? r.ev_mean_smooth : null,
  }))
  const yMax = Math.max(
    ...data.map((d) => d.p90_smooth),
    ...annotations.map((a) => a.realized_value),
    ...data.map((d) => d.ev_mean_smooth),
  )
  // Three structural landmarks: 1st-overall value, the early-pick cliff, round-2 flattening.
  const at = (pick: number) => curve.find((c) => c.overall_pick === pick)
  const firstOverall = curve[0]
  let cliffPick = 3, cliffDrop = 0
  for (let i = 1; i < Math.min(curve.length, 15); i++) {
    const d = curve[i - 1].ev_mean_smooth - curve[i].ev_mean_smooth
    if (d > cliffDrop) { cliffDrop = d; cliffPick = curve[i].overall_pick }
  }
  const landmarks = [
    firstOverall && { x: firstOverall.overall_pick, y: firstOverall.ev_mean_smooth, text: `1st overall ≈ ${firstOverall.ev_mean_smooth.toFixed(1)} WAR`, up: true },
    at(cliffPick) && { x: cliffPick, y: at(cliffPick)!.ev_mean_smooth, text: 'the cliff after the top picks', up: true },
    at(45) && { x: 45, y: at(45)!.ev_mean_smooth, text: 'round 2 flattens', up: false },
  ].filter(Boolean) as { x: number; y: number; text: string; up: boolean }[]
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 16, right: 16, bottom: 18, left: 4 }}>
        <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" />
        {/* log x so the steep top of the draft (picks 1–30) gets the room it deserves */}
        <XAxis dataKey="overall_pick" type="number" scale="log" domain={[1, 217]} allowDataOverflow
          stroke="var(--color-border)" tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
          ticks={[1, 2, 5, 10, 31, 62, 124, 217]} tickFormatter={(v: number) => `${v}`} height={34}>
          <Label value="Overall pick (log scale)" position="insideBottom" dy={12}
            style={{ fontSize: 11, fill: 'var(--color-text-muted)' }} />
        </XAxis>
        <YAxis domain={[0, Math.ceil(yMax)]} stroke="var(--color-border)"
          tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
          tickFormatter={(v: number) => `${v}`} width={36}>
          <Label value="Realized WAR (7yr)" angle={-90} position="insideLeft" dy={56}
            style={{ fontSize: 11, fill: 'var(--color-text-muted)' }} />
        </YAxis>
        <RTooltip content={<CurveChartTip />} />
        {/* p10–p90 band */}
        <Area dataKey="bandLo" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} />
        <Area dataKey="bandSpan" stackId="band" stroke="none" fill="var(--color-data-1)" fillOpacity={0.12} isAnimationActive={false} />
        <Line type="monotone" dataKey="ev_median" stroke="var(--color-text-muted)" strokeWidth={1.5}
          strokeDasharray="5 4" dot={false} isAnimationActive={false}>
          {/* anchor at the line's high (left) end, inside the plot — the right end converges to ~0 and
              would clip past the chart's right edge */}
          <Label content={lineLabel('median', 'var(--color-text-muted)', 10, 400)} />
        </Line>
        {/* §S7: fitted region solid 2px --line-blue; sparse extrapolated tail dashed. */}
        <Line type="monotone" dataKey="evFit" stroke="var(--line-blue)" strokeWidth={2}
          dot={false} connectNulls={false} animationDuration={400}>
          <Label content={lineLabel('expected', 'var(--line-blue)', 11, 600)} />
        </Line>
        <Line type="monotone" dataKey="evExtrap" stroke="var(--line-blue)" strokeWidth={2}
          strokeDasharray="5 4" dot={false} connectNulls={false} isAnimationActive={false} />
        {landmarks.map((m) => (
          <ReferenceDot key={m.text} x={m.x} y={m.y} r={0} fill="none" stroke="none">
            <Label content={landmarkLabel(m.text, narrow, m.up)} />
          </ReferenceDot>
        ))}
        {annotations.map((a) => {
          const color = a.tone === 'steal' ? 'var(--color-data-positive)' : 'var(--color-data-negative)'
          return (
            <ReferenceDot key={a.label} x={a.overall_pick} y={a.realized_value} r={4}
              fill={color} stroke="var(--color-bg-surface)" strokeWidth={1.5}>
              <Label content={annotationLabel(a, yMax, color)} />
            </ReferenceDot>
          )
        })}
      </ComposedChart>
    </ResponsiveContainer>
  )
}

interface Annotation { overall_pick: number; realized_value: number; label: string; tone: 'steal' | 'bust' }

// ---------------------------------------------------------------- theory table
function TheoryTable({ rows }: { rows: DraftTheorySummaryRow[] }) {
  return (
    <table className="dv-table dv-theory">
      <thead>
        <tr>
          <th>Pick range</th><th className="num">Picks</th>
          <th className="num"><Tooltip content="Share of picks whose 7-year realized value came in below the average value of picks at that slot. With a right-skewed distribution, most picks fall below the mean by construction.">Below slot avg</Tooltip></th>
          <th className="num"><Tooltip content="Share below the MEDIAN pick at that slot — the more honest 'worse than a coin-flip pick' rate.">Below median</Tooltip></th>
          <th className="num"><Tooltip content="Share who never played a single NHL game (realized value 0).">Never NHL</Tooltip></th>
          <th className="num"><Tooltip content="Share who reached ~200 career games — the literature's 'became a regular' bar.">Became regular</Tooltip></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.pick_range} className={r.pick_range === 'POOLED' ? 'dv-theory__pooled' : ''}>
            <td>{RANGE_LABEL[r.pick_range] ?? r.pick_range}</td>
            <td className="num mono">{r.picks}</td>
            <td className="num mono">{pct0(r.share_below_mean)}</td>
            <td className="num mono">{pct0(r.share_below_median)}</td>
            <td className="num mono">{pct0(r.share_never_nhl)}</td>
            <td className="num mono">{pct0(r.share_became_regular)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ---------------------------------------------------------------- board
function Board({ rows }: { rows: DraftBoardRow[] }) {
  const navigate = useNavigate()
  return (
    <table className="dv-table dv-board">
      <thead>
        <tr>
          <th>Player</th><th className="num">Pick</th>
          <th className="num">Realized</th><th className="num">Slot exp.</th><th className="num">vs slot</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const to = r.resolved_player_id ? `/players/${r.resolved_player_id}` : null
          return (
            <tr key={r.overall_pick + '-' + r.draft_year}
              className={`dv-board__row${to ? ' dv-board__row--link' : ''}`}
              onClick={to ? () => navigate(to) : undefined}
              tabIndex={to ? 0 : undefined}
              onKeyDown={to ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(to) } } : undefined}>
              <td className="dv-board__player">
                {r.resolved_player_id
                  ? <PlayerAvatar id={r.resolved_player_id} team={r.draft_team_abbrev} name={r.full_name} size={28} />
                  : <span className="dv-board__noavatar" aria-hidden />}
                <div className="dv-board__name">
                  <span>{r.full_name ?? '—'}</span>
                  <span className="dv-board__meta">{r.draft_year} · {r.draft_team_abbrev ?? ''} · {r.pos_group ?? ''}</span>
                </div>
              </td>
              <td className="num mono">#{r.overall_pick}</td>
              <td className="num mono">{r.realized_value.toFixed(1)}</td>
              <td className="num mono dv-muted">{r.expected_mean.toFixed(1)}</td>
              <td className={`num mono ${r.value_above_slot >= 0 ? 'dv-pos' : 'dv-neg'}`}>
                {r.value_above_slot >= 0 ? '+' : '−'}{Math.abs(r.value_above_slot).toFixed(1)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// ---------------------------------------------------------------- page
const POS_TABS = [
  { value: 'all', label: 'All' }, { value: 'F', label: 'Forwards' },
  { value: 'D', label: 'Defense' }, { value: 'G', label: 'Goalies' },
]

export default function DraftValue() {
  usePageTitle('Draft value')
  const [curve, setCurve] = useState<PickValueCurveRow[] | null>(null)
  const [summary, setSummary] = useState<DraftTheorySummaryRow[] | null>(null)
  const [boardType, setBoardType] = useState<'steals' | 'busts'>('steals')
  const [pos, setPos] = useState('all')
  const [board, setBoard] = useState<DraftBoardRow[] | null>(null)
  const [annotations, setAnnotations] = useState<Annotation[]>([])

  useEffect(() => {
    getPickValueCurve().then(setCurve).catch(() => setCurve([]))
    getDraftTheorySummary().then(setSummary).catch(() => setSummary([]))
    // chart annotations: a famous late steal (fits the scale) + a famous early bust
    Promise.all([getDraftBoard('steals', undefined, 50), getDraftBoard('busts', undefined, 50)])
      .then(([steals, busts]) => {
        const steal = steals.find((s) => s.overall_pick >= 60)
        const bust = busts.find((b) => b.overall_pick <= 10)
        const ann: Annotation[] = []
        if (steal) ann.push({ overall_pick: steal.overall_pick, realized_value: steal.realized_value, label: lastName(steal.full_name), tone: 'steal' })
        if (bust) ann.push({ overall_pick: bust.overall_pick, realized_value: bust.realized_value, label: lastName(bust.full_name), tone: 'bust' })
        setAnnotations(ann)
      })
      .catch(() => setAnnotations([]))
  }, [])

  useEffect(() => {
    setBoard(null)
    getDraftBoard(boardType, pos === 'all' ? undefined : pos, 25).then(setBoard).catch(() => setBoard([]))
  }, [boardType, pos])

  const pooled = useMemo(() => summary?.find((s) => s.pick_range === 'POOLED'), [summary])

  return (
    <PageLayout>
      <div className="dv">
        <PageCard
          eyebrow="Studio"
          title="Draft value"
          subtitle="What a draft slot is actually worth, measured from draft history."
        >
        {/* curve */}
        <section className="dv-section">
          <h2 className="dv-section__title">
            {curve && curve.length
              ? `A top-five pick is worth roughly ${curve.find((c) => c.overall_pick === 5)?.ev_mean_smooth.toFixed(1)} WAR; by the third round, essentially replacement level`
              : 'The empirical pick-value curve'}
          </h2>
          <p className="dv-section__sub">Expected and median realized value by overall pick, with the middle 80% of outcomes shaded. The curve falls steeply — the gap between the first pick and the tenth dwarfs the gap across entire later rounds.</p>
          <ChartPanel title="Realized value by pick" subtitle="Smoothed across pick number; later picks never worth more in expectation">
            {curve ? <CurveChart curve={curve} annotations={annotations} /> : <SkeletonLoader height={280} />}
          </ChartPanel>
          {/* §S7: this is a real figure sequence — earned figure numbering. */}
          <p className="dv-figcap">
            <span className="dv-figcap__n">Fig. 1</span>
            Realized 7-year WAR by draft slot: a fitted expected-value curve (solid) with its
            sparse-sample tail extrapolated (dashed) and the middle 80% of outcomes shaded.
          </p>
        </section>

        <div className="page-divider" />

        {/* theory test */}
        <section className="dv-section">
          <h2 className="dv-section__title">
            {pooled
              ? `${pct0(pooled.share_never_nhl)} of all picks never play an NHL game — and ${pct0(pooled.share_below_mean)} return below their slot's average`
              : 'Do most picks "bust"?'}
          </h2>
          <p className="dv-section__sub">
            The folk claim that the vast majority of picks bust is roughly true — but how you count matters. Most picks fall below their slot's <em>mean</em> because a few stars pull the average up; the <em>median</em> tells a gentler story. Both are shown, with the never-play rate, so the number is read honestly.
          </p>
          <div className="dv-card">
            {summary ? <TheoryTable rows={summary} /> : <SkeletonLoader height={220} />}
          </div>
        </section>

        <div className="page-divider" />

        {/* board */}
        <section className="dv-section">
          <h2 className="dv-section__title">Steals and busts</h2>
          <p className="dv-section__sub">Evaluable picks (classes 2010–2018) ranked by how far their realized value beat or trailed the expectation for their slot.</p>
          <div className="dv-card">
            <div className="dv-card__controls">
              <Tabs options={[{ value: 'steals', label: 'Steals' }, { value: 'busts', label: 'Busts' }]}
                value={boardType} onChange={(v) => setBoardType(v as 'steals' | 'busts')} />
              <Tabs options={POS_TABS} value={pos} onChange={setPos} />
            </div>
            {board ? <Board rows={board} /> : <SkeletonLoader height={400} />}
          </div>
        </section>

        <p className="dv-footnote">
          This is a <strong>performance</strong> curve — what slots have <em>returned</em> — not a market curve of what teams <em>pay</em> in trades, and not a grade of any pick at the time it was made. Value before 2021-22 is estimated from box production and carries a wide band; goalie value is cruder still. Read the <Link to="/learn/archetypes">methodology</Link> for the full method and its limits.
        </p>
        </PageCard>
      </div>
    </PageLayout>
  )
}

function lastName(full: string | null): string {
  if (!full) return ''
  const parts = full.trim().split(/\s+/)
  return parts[parts.length - 1]
}
