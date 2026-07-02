/**
 * TraderDossier (Handoff 8) — one component for a team OR a GM, as a STACK of section cards: identity &
 * verdict, the regime-banded cumulative-net timeline, and record & deals. Net / record / partners and the
 * cumulative line are SETTLED-ONLY; the deal list shows everything (maturing flagged). No toggle — the
 * denominator is stated in words. For a team the timeline bands by GM regime; for a GM, by franchise.
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
import Tilt from './Tilt'
import './trades.css'

const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`

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
  return key
}
function regimeColor(d: Dossier, key: string): string {
  if (d.kind === 'gm') return getTeamColor(key)
  return 'var(--color-text-secondary)'
}
function trendInsight(d: Dossier): string {
  const tl = d.timeline
  if (tl.length < 2) return ''
  const end = tl[tl.length - 1].cumulative_net_war
  const dir = end > 1 ? 'net positive' : end < -1 ? 'net negative' : 'roughly even'
  return `${d.label}'s settled trades are ${dir} at ${fmt(end)} WAR cumulatively across ${d.trade_count} deals (wide bands).`
}

function Timeline({ d }: { d: Dossier }) {
  const data = d.timeline.map((p) => ({ ...p, t: new Date(p.date).getTime() }))
  const bands = useMemo(() => regimeBands(d), [d])
  if (data.length < 2) return <div className="dos-empty">Not enough trades to chart a trend.</div>
  const insight = trendInsight(d)
  return (
    <>
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
            isAnimationActive={false}
            dot={(p: any) => {
              const mat = p.payload?.incomplete
              return <circle key={p.payload?.trade_id} cx={p.cx} cy={p.cy} r={mat ? 3 : 2}
                fill={mat ? 'var(--color-bg-surface)' : 'var(--color-data-1)'} stroke="var(--color-data-1)"
                strokeDasharray={mat ? '2 1' : undefined} />
            }} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="t-note" style={{ marginTop: 'var(--space-2)' }}>
        The line advances only on settled trades; still-maturing trades are plotted (hollow dots) but don't move it yet.
      </p>
    </>
  )
}

function DealInset({ t, label, focusTeam, onOpen }: { t: TradeBoardItem; label: string; focusTeam?: string; onOpen: (id: string) => void }) {
  const win = t.sides.find((s) => s.team_id === t.winner_team_id)
  const color = win ? getTeamColor(win.team_abbrev) : 'var(--color-text-muted)'
  const sides = [...t.sides].sort((a, b) => (a.team_abbrev === focusTeam ? -1 : b.team_abbrev === focusTeam ? 1 : 0))
  return (
    <button className="t-inset" style={{ textAlign: 'left', border: 'none', cursor: 'pointer', width: '100%' }} onClick={() => onOpen(t.trade_id)}>
      <div className="arch-stat__l" style={{ marginBottom: 'var(--space-2)' }}>{label}</div>
      <div style={{ fontSize: 'var(--text-sm)', marginBottom: 4 }}>
        {sides.map((s) => s.team_abbrev).join(' · ')}
        <span className="tbl-muted"> · {t.date.slice(0, 4)}{t.incomplete ? ' · maturing' : ''}</span>
        <span className="lb-net" style={{ float: 'right' }}>{fmt(t.margin_slot)}</span>
      </div>
      <Tilt signed={win && win.team_abbrev === sides[1]?.team_abbrev ? t.margin_slot : -t.margin_slot}
        bandHw={t.band_hw_slot} color={color} even={t.verdict === 'even'}
        edge={t.verdict === 'edge' && !t.incomplete} incomplete={t.incomplete} size="compact" animate={false} />
    </button>
  )
}

export default function TraderDossier({ kind, id, onBack, onOpenTrade }: {
  kind: 'team' | 'gm'; id: string; onBack: () => void; onOpenTrade: (tradeId: string) => void
}) {
  const [d, setD] = useState<Dossier | null>(null)
  const [showAll, setShowAll] = useState(false)
  useEffect(() => { setD(null); setShowAll(false); getDossier(kind, id).then(setD).catch(() => setD(null)) }, [kind, id])

  if (!d) return <SkeletonLoader height={500} />
  const byId = new Map(d.deal_items.map((t) => [t.trade_id, t]))
  const r = d.record
  const focusTeam = kind === 'team' ? id : undefined
  const best = d.best.map((tid) => byId.get(tid)).filter(Boolean) as TradeBoardItem[]
  const worst = d.worst.map((tid) => byId.get(tid)).filter(Boolean) as TradeBoardItem[]
  // separation cue: how far this entity's net record sits from even in units of its own band (mirrors
  // config.TRADE_BOARD.RANKING CLEAR_Z=2 / LEANS_Z=1). Tells a drilled-in user how much to trust the net.
  const z = d.net_band_hw > 0 ? d.net_war / d.net_band_hw : 0
  const sep = Math.abs(z) >= 2 ? 'clear' : Math.abs(z) >= 1 ? 'leans' : 'noise'
  const sepLabel = sep === 'clear' ? 'clearly separated from even'
    : sep === 'leans' ? 'leans, within margin of error' : 'within noise of even'

  return (
    <div className="dos-sections">
      <button className="dos-back" onClick={onBack}><ChevronLeft size={16} /> back to the map</button>

      {/* Section 1 — identity & verdict */}
      <div className="t-panel">
        <div className="dos-header">
          <span className="dos-title">
            {kind === 'team' && <img src={getTeamLogoUrl(id)} alt="" className="tbl-logo" style={{ width: 28, height: 28 }} />}
            {d.label}
            {kind === 'gm' && <span className="tbl-muted" style={{ fontSize: 'var(--text-sm)' }}>across {d.tenures.length} {d.tenures.length === 1 ? 'team' : 'teams'}</span>}
            <Tooltip content="GM of record from curated tenure dates (approximate near handovers) — not the sole decision-maker. A retrospective on outcomes, not a grade of the decision at the time."><Info size={14} className="tbl-muted" /></Tooltip>
          </span>
          <span className={`dos-net mono ${d.net_war >= 0 ? 'dos-pos' : 'dos-neg'}`}>
            {fmt(d.net_war)} <span className="dos-net__band">± {d.net_band_hw.toFixed(1)} WAR</span>
          </span>
          <span className={`dos-sep dos-sep--${sep}`}>{sepLabel}</span>
        </div>
        {/* The net is an ACCUMULATION across many small results, not "won N trades" — say so explicitly. */}
        <p className="dos-recordline">
          net {fmt(d.net_war)} (±{d.net_band_hw.toFixed(1)}) — built from <b>{r.decisive_wins}</b> decisive,
          {' '}<b>{r.edge}</b> edge{r.edge === 1 ? '' : 's'}, <b>{r.even}</b> even, <b>{r.losses}</b> losses
        </p>
        {kind === 'gm' && (
          <div className="dos-chips">
            {d.tenures.map((t, i) => (
              <span key={i} className="dos-chip">{t.team_abbrev} {t.start_date.slice(0, 4)}–{t.end_date ? t.end_date.slice(0, 4) : 'now'}</span>
            ))}
          </div>
        )}
        <p className="t-note">
          Net, record and timeline cover {d.settled_count} settled trades old enough to have played out
          {d.maturing_count ? `; ${d.maturing_count} still-maturing trades appear in the deal list below, flagged, but aren't in these numbers yet` : ''}.
        </p>
      </div>

      <div className="t-divider" />

      {/* Section 2 — timeline */}
      <div className="t-panel">
        <h3 className="t-region-title">Cumulative net value over time</h3>
        <Timeline d={d} />
      </div>

      <div className="t-divider" />

      {/* Section 3 — record & deals */}
      <div className="t-panel">
        {d.partners.length > 1 && (
          <>
            <h3 className="t-region-title">Record by trade partner</h3>
            <div className="dos-partners">
              {d.partners.slice(0, 8).map((p) => (
                <div key={p.opponent} className="dos-partner">
                  <span className="dos-partner__opp"><img src={getTeamLogoUrl(p.opponent)} alt="" className="tbl-logo" /> <span className="mono">{p.opponent}</span></span>
                  <span className="dos-partner__n tbl-muted">{p.trade_count} {p.trade_count === 1 ? 'trade' : 'trades'}</span>
                  <Tilt signed={p.net_war} bandHw={p.band_hw} color={getTeamColor(p.opponent)} even={Math.abs(p.net_war) < 0.5} incomplete={false} size="sparkline" animate={false} />
                  <span className={`mono ${p.net_war >= 0 ? 'dos-pos' : 'dos-neg'}`}>{fmt(p.net_war)}</span>
                </div>
              ))}
            </div>
            <div className="t-divider" />
          </>
        )}

        <h3 className="t-region-title">Best & worst deals</h3>
        <div className="dos-cols">
          <div className="t-stack">{best.map((t) => <DealInset key={t.trade_id} t={t} label="Best" focusTeam={focusTeam} onOpen={onOpenTrade} />)}</div>
          <div className="t-stack">{worst.map((t) => <DealInset key={t.trade_id} t={t} label="Worst" focusTeam={focusTeam} onOpen={onOpenTrade} />)}</div>
        </div>

        {d.deal_items.length > 0 && (
          <button className="dos-disclosure" onClick={() => setShowAll((s) => !s)}>
            {showAll ? 'hide deal list' : `show all ${d.deal_items.length} deals`}
          </button>
        )}
      </div>

      {/* Full deal list — flat stack of inset leaf items (siblings, never nested) */}
      {showAll && (
        <>
          <div className="t-divider" />
          <div className="t-stack">
            {d.deal_items.map((t) => <TradeBalanceCard key={t.trade_id} trade={t} focusTeam={focusTeam}
              fullHref={undefined} />)}
          </div>
        </>
      )}
    </div>
  )
}
