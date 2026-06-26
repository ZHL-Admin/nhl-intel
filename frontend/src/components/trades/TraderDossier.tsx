/**
 * TraderDossier (Handoff 6, surface 5B) — one component for a team OR a GM. Verdict header, the
 * regime-banded cumulative-net timeline (the signature visual), best/worst deals, and the full deal
 * list (collapsed). For a team, the timeline bands by attributed GM regime; for a GM, by franchise.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine,
  ReferenceArea, Tooltip as RTooltip, Label,
} from 'recharts'
import { ChevronLeft, Info } from 'lucide-react'
import { SkeletonLoader, Tooltip } from '../common'
import { getTeamColor, getTeamLogoUrl } from '../../utils/teams'
import { getDossier, TraderDossier as Dossier, TradeBoardItem } from '../../api/trades'
import TradeBalanceCard from './TradeBalanceCard'
import './trades.css'

const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`

/** Contiguous regime bands for the timeline background (by gm_id for a team, team_abbrev for a GM). */
function regimeBands(d: Dossier) {
  const bands: { key: string; from: number; to: number; label: string }[] = []
  d.timeline.forEach((p, i) => {
    const x = new Date(p.date).getTime()
    const last = bands[bands.length - 1]
    if (last && last.key === p.regime_key) last.to = x
    else bands.push({ key: p.regime_key, from: x, to: x, label: regimeLabel(d, p.regime_key) })
    if (i === d.timeline.length - 1 && bands.length) bands[bands.length - 1].to = x
  })
  return bands
}
function regimeLabel(d: Dossier, key: string): string {
  if (d.kind === 'team') return key === 'unknown' ? 'unknown' : key.replace(/_/g, ' ')
  return key  // franchise abbrev
}
function regimeColor(d: Dossier, key: string): string {
  if (d.kind === 'gm') return getTeamColor(key)
  return 'var(--color-text-secondary)'
}

function Timeline({ d }: { d: Dossier }) {
  const data = d.timeline.map((p) => ({ ...p, t: new Date(p.date).getTime() }))
  const bands = useMemo(() => regimeBands(d), [d])
  if (data.length < 2) return <div className="dos-empty">Not enough trades to chart a trend.</div>
  const insight = trendInsight(d)
  return (
    <>
      <div className="dos-section-title">Cumulative net value over time</div>
      <p className="dos-sentence">{insight}</p>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}
          role="img" aria-label={`Cumulative net WAR over time, banded by ${d.kind === 'team' ? 'GM regime' : 'franchise'}. ${insight}`}>
          <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" />
          {bands.map((b, i) => (
            <ReferenceArea key={i} x1={b.from} x2={b.to} ifOverflow="extendDomain"
              fill={regimeColor(d, b.key)} fillOpacity={d.kind === 'gm' ? 0.10 : 0.05}
              stroke="var(--color-border-subtle)" strokeOpacity={0.4}>
              <Label value={b.label} position="insideTop" style={{ fontSize: 10, fill: 'var(--color-text-muted)' }} />
            </ReferenceArea>
          ))}
          <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']}
            tickFormatter={(t) => new Date(t).getFullYear().toString()}
            tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} stroke="var(--color-border)" />
          <YAxis tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }} stroke="var(--color-border)" width={40}>
            <Label value="cumulative net WAR" angle={-90} position="insideLeft" dy={60} style={{ fontSize: 11, fill: 'var(--color-text-muted)' }} />
          </YAxis>
          <ReferenceLine y={0} stroke="var(--color-border-strong)" />
          <RTooltip
            labelFormatter={(t) => new Date(t).toLocaleDateString()}
            formatter={(v: any) => [`${fmt(Number(v))} WAR`, 'cumulative']}
            contentStyle={{ background: 'var(--color-bg-overlay)', border: '1px solid var(--color-border)', borderRadius: 8, fontSize: 12 }} />
          <Line type="stepAfter" dataKey="cumulative_net_war" stroke="var(--color-data-1)" strokeWidth={2}
            dot={{ r: 2 }} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </>
  )
}

function trendInsight(d: Dossier): string {
  const tl = d.timeline
  if (tl.length < 2) return ''
  const end = tl[tl.length - 1].cumulative_net_war
  const dir = end > 1 ? 'net positive' : end < -1 ? 'net negative' : 'roughly even'
  return `${d.label}'s trades are ${dir} at ${fmt(end)} WAR cumulatively across ${d.trade_count} deals (wide bands).`
}

export default function TraderDossier({ kind, id, lens, onBack }: {
  kind: 'team' | 'gm'; id: string; lens: 'slot' | 'actual'; onBack: () => void
}) {
  const [d, setD] = useState<Dossier | null>(null)
  const [showAll, setShowAll] = useState(false)
  useEffect(() => { setD(null); getDossier(kind, id, lens).then(setD).catch(() => setD(null)) }, [kind, id, lens])

  if (!d) return <SkeletonLoader height={500} />
  const byId = new Map(d.deal_items.map((t) => [t.trade_id, t]))
  const r = d.record
  const focusTeam = kind === 'team' ? id : undefined
  const best = d.best.map((tid) => byId.get(tid)).filter(Boolean) as TradeBoardItem[]
  const worst = d.worst.map((tid) => byId.get(tid)).filter(Boolean) as TradeBoardItem[]
  const restIds = new Set([...d.best, ...d.worst])
  const rest = d.deal_items.filter((t) => !restIds.has(t.trade_id))

  return (
    <div className="dos">
      <button className="dos-back" onClick={onBack}><ChevronLeft size={16} /> back to the map</button>

      <div className="dos-header">
        <span className="dos-title">
          {kind === 'team' && <img src={getTeamLogoUrl(id)} alt="" className="tbl-logo" style={{ width: 28, height: 28 }} />}
          {d.label}
          {kind === 'gm' && <span className="tbl-muted" style={{ fontSize: 'var(--text-sm)' }}>across {d.tenures.length} {d.tenures.length === 1 ? 'team' : 'teams'}</span>}
          <Tooltip content="GM attribution is to the decision-maker of record from curated tenure dates (approximate near handovers); the GM is not the sole decision-maker. A retrospective on outcomes, not a grade of the decision at the time."><Info size={14} className="tbl-muted" /></Tooltip>
        </span>
        <span className={`dos-net mono ${d.net_war >= 0 ? 'dos-pos' : 'dos-neg'}`}>
          {fmt(d.net_war)} <span className="dos-net__band">± {d.net_band_hw.toFixed(1)} WAR</span>
        </span>
        <span className="dos-record">
          <span><b>{r.decisive_wins}</b> wins</span><span><b>{r.leans}</b> leans</span>
          <span><b>{r.too_close}</b> close</span><span><b>{r.losses}</b> losses</span>
        </span>
      </div>

      {kind === 'gm' && (
        <div className="dos-chips">
          {d.tenures.map((t, i) => (
            <span key={i} className="dos-chip">{t.team_abbrev} {t.start_date.slice(0, 4)}–{t.end_date ? t.end_date.slice(0, 4) : 'now'}</span>
          ))}
        </div>
      )}
      <p className="dos-sentence">{trendInsight(d)}</p>

      <Timeline d={d} />

      <div className="dos-section-title">Best and worst deals</div>
      <div className="dos-cols">
        <div>{best.map((t) => <TradeBalanceCard key={t.trade_id} trade={t} lens={lens} focusTeam={focusTeam} />)}</div>
        <div>{worst.map((t) => <TradeBalanceCard key={t.trade_id} trade={t} lens={lens} focusTeam={focusTeam} />)}</div>
      </div>

      {rest.length > 0 && (
        <>
          {!showAll
            ? <button className="dos-disclosure" onClick={() => setShowAll(true)}>show all {d.deal_items.length} deals</button>
            : <>
                <div className="dos-section-title">All deals (best to worst)</div>
                {rest.map((t) => <TradeBalanceCard key={t.trade_id} trade={t} lens={lens} focusTeam={focusTeam} />)}
              </>}
        </>
      )}
    </div>
  )
}
