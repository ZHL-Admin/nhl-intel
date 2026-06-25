/**
 * Draft Value (Handoff 5) — the empirical pick-value curve, the "85%" theory test, and the
 * steal/bust board. Every number is realized 7-year-window pWAR (same WAR units as the value stack),
 * an explicit wide-band estimate before 2021. Reuses ChartPanel, PlayerAvatar, Tabs, Tooltip.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ReferenceDot, Label,
} from 'recharts'
import {
  PageLayout, PageHeader, ChartPanel, PlayerAvatar, Tabs, Tooltip, SkeletonLoader,
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
      <div className="dv-charttip__row"><span>Median outcome</span><span className="mono">{d.ev_median_smooth.toFixed(1)} WAR</span></div>
      <div className="dv-charttip__row dv-charttip__row--muted"><span>Middle 80% (p10–p90)</span><span className="mono">{d.p10.toFixed(1)}–{d.p90.toFixed(1)}</span></div>
      <div className="dv-charttip__row dv-charttip__row--muted"><span>Never play NHL</span><span className="mono">{pct0(d.share_never_nhl)}</span></div>
    </div>
  )
}

function CurveChart({ curve, annotations }: { curve: PickValueCurveRow[]; annotations: Annotation[] }) {
  const height = useChartPanelHeight()
  const data = curve.map((r) => ({
    ...r,
    bandLo: r.p10,
    bandSpan: Math.max(0, r.p90 - r.p10),
  }))
  const yMax = Math.max(
    ...data.map((d) => d.p90),
    ...annotations.map((a) => a.realized_value),
    ...data.map((d) => d.ev_mean_smooth),
  )
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 16, right: 16, bottom: 18, left: 4 }}>
        <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" />
        <XAxis dataKey="overall_pick" type="number" domain={[1, 'dataMax']} stroke="var(--color-border)"
          tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
          ticks={[1, 31, 62, 93, 124, 155, 186, 217]} height={34}>
          <Label value="Overall pick" position="insideBottom" dy={12}
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
        <Line type="monotone" dataKey="ev_median_smooth" stroke="var(--color-text-muted)" strokeWidth={1.5}
          strokeDasharray="5 4" dot={false} isAnimationActive={false}>
          <Label value="median" position="right" fill="var(--color-text-muted)" style={{ fontSize: 10 }} />
        </Line>
        <Line type="monotone" dataKey="ev_mean_smooth" stroke="var(--color-data-1)" strokeWidth={2.25}
          dot={false} animationDuration={400}>
          <Label value="expected" position="right" fill="var(--color-data-1)" style={{ fontSize: 11, fontWeight: 600 }} />
        </Line>
        {annotations.map((a) => (
          <ReferenceDot key={a.label} x={a.overall_pick} y={a.realized_value} r={4}
            fill={a.tone === 'steal' ? 'var(--color-success)' : 'var(--color-danger)'} stroke="var(--color-bg-surface)" strokeWidth={1.5}>
            <Label value={a.label} position={a.realized_value > 4 ? 'top' : 'bottom'}
              fill={a.tone === 'steal' ? 'var(--color-success)' : 'var(--color-danger)'}
              style={{ fontSize: 10, fontWeight: 600 }} />
          </ReferenceDot>
        ))}
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
          const body = (
            <>
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
            </>
          )
          return r.resolved_player_id ? (
            <tr key={r.overall_pick + '-' + r.draft_year} className="dv-board__row dv-board__row--link">
              <td colSpan={5} style={{ padding: 0 }}>
                <Link to={`/players/${r.resolved_player_id}`} className="dv-board__link">
                  <table className="dv-board__inner"><tbody><tr>{body}</tr></tbody></table>
                </Link>
              </td>
            </tr>
          ) : (
            <tr key={r.overall_pick + '-' + r.draft_year} className="dv-board__row">{body}</tr>
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
        <PageHeader
          title="Draft Value"
          subtitle="What a pick is actually worth — measured on what every slot has returned since 2010, not a formula. Value is realized production over a player's first seven seasons, in the same WAR units used across the site (an estimate for older seasons, shown with its band)."
        />

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
        </section>

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
          {summary ? <TheoryTable rows={summary} /> : <SkeletonLoader height={220} />}
        </section>

        {/* board */}
        <section className="dv-section">
          <h2 className="dv-section__title">Steals and busts</h2>
          <p className="dv-section__sub">Evaluable picks (classes 2010–2018) ranked by how far their realized value beat or trailed the expectation for their slot.</p>
          <div className="dv-controls">
            <Tabs options={[{ value: 'steals', label: 'Steals' }, { value: 'busts', label: 'Busts' }]}
              value={boardType} onChange={(v) => setBoardType(v as 'steals' | 'busts')} />
            <Tabs options={POS_TABS} value={pos} onChange={setPos} />
          </div>
          {board ? <Board rows={board} /> : <SkeletonLoader height={400} />}
        </section>

        <p className="dv-footnote">
          This is a <strong>performance</strong> curve — what slots have <em>returned</em> — not a market curve of what teams <em>pay</em> in trades, and not a grade of any pick at the time it was made. Value before 2021-22 is estimated from box production and carries a wide band; goalie value is cruder still. Read the <Link to="/learn/archetypes">methodology</Link> for the full method and its limits.
        </p>
      </div>
    </PageLayout>
  )
}

function lastName(full: string | null): string {
  if (!full) return ''
  const parts = full.trim().split(/\s+/)
  return parts[parts.length - 1]
}
