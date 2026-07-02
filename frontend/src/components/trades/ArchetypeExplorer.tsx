/**
 * ArchetypeExplorer (Handoff 8) — Tab 3 "Patterns", ONE card. Archetype sub-tabs in the card header;
 * the body is three divider-separated regions (no nested cards): a split (honest headline + 3-segment
 * bar + plain takeaway), exemplars (subtle insets, mini balance bars), and timing (labeled bars). Splits
 * are settled-only; a denominator note states it. Only data-taggable archetypes (no rental/salary-dump).
 */
import { useEffect, useState } from 'react'
import { Tabs, SkeletonLoader } from '../common'
import { getTeamColor } from '../../utils/teams'
import { getArchetypes, getBoardItem, ArchetypeAgg, TradeBoardItem } from '../../api/trades'
import Tilt from './Tilt'
import './trades.css'

const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`

function headline(a: ArchetypeAgg): string {
  const s = a.split
  if (a.archetype === 'player_for_picks') {
    const close = Math.abs((s.player_side_won_pct || 0) - (s.pick_side_won_pct || 0)) <= 12
    return close ? 'Trading a star for picks is close to a coin-flip.'
      : (s.player_side_won_pct || 0) > (s.pick_side_won_pct || 0)
        ? 'The side that got the player usually came out ahead.'
        : 'The picks usually paid off.'
  }
  if (a.archetype === 'picks_for_picks') return 'Pick-only swaps rarely move realized value decisively.'
  return `One side won clearly ${s.decisive_pct || 0}% of the time; the rest came out even.`
}

function takeaway(a: ArchetypeAgg): string {
  const s = a.split
  if (a.archetype === 'player_for_picks') {
    return `Across ${a.trade_count} settled player-for-picks deals, the player side won ${s.player_side_won_pct}%, the picks paid off ${s.pick_side_won_pct}%, and ${s.even_pct}% were even within the margin.`
  }
  if (a.archetype === 'player_for_player') {
    return `Across ${a.trade_count} settled player-for-player deals, one side won clearly ${s.decisive_pct}%; ${s.even_pct}% came out even.`
  }
  if (a.archetype === 'picks_for_picks') {
    return `Across ${a.trade_count} settled picks-for-picks deals, ${s.even_pct}% were even within the margin.`
  }
  if (a.archetype === 'blockbuster') {
    return `Across ${a.trade_count} settled blockbusters (8+ WAR moved), one side won clearly ${s.decisive_pct}%; ${s.even_pct}% stayed within the band.`
  }
  return `Across ${a.trade_count} settled three-team deals, one side won clearly ${s.decisive_pct}%.`
}

// the 3- (player-for-picks) or 2-segment split bar
function SplitBar({ a }: { a: ArchetypeAgg }) {
  const s = a.split
  const segs = a.archetype === 'player_for_picks'
    ? [
        { label: 'player side won', pct: s.player_side_won_pct || 0, color: 'var(--color-success)' },
        { label: 'even', pct: s.even_pct || 0, color: 'var(--color-border-strong)' },
        { label: 'picks won', pct: s.pick_side_won_pct || 0, color: 'var(--color-warning)' },
      ]
    : [
        { label: 'one side won', pct: s.decisive_pct || 0, color: 'var(--color-success)' },
        { label: 'even', pct: s.even_pct || 0, color: 'var(--color-border-strong)' },
      ]
  return (
    <>
      <div className="split-bar">
        {segs.map((g) => g.pct > 0 && <div key={g.label} className="split-bar__seg" style={{ width: `${g.pct}%`, background: g.color }} />)}
      </div>
      <div className="split-legend">
        {segs.map((g) => (
          <span key={g.label}><span className="split-legend__dot" style={{ background: g.color }} />{g.label} <b className="mono">{g.pct}%</b></span>
        ))}
      </div>
    </>
  )
}

function ExemplarInset({ label, tradeId, onOpenTrade }: { label: string; tradeId: string; onOpenTrade: (id: string) => void }) {
  const [t, setT] = useState<TradeBoardItem | null>(null)
  useEffect(() => { let live = true; getBoardItem(tradeId).then((x) => live && setT(x)).catch(() => {}); return () => { live = false } }, [tradeId])
  const win = t?.sides.find((s) => s.team_id === t?.winner_team_id)
  const color = win ? getTeamColor(win.team_abbrev) : 'var(--color-text-muted)'
  return (
    <button className="t-inset" style={{ textAlign: 'left', border: 'none', cursor: 'pointer', width: '100%' }}
      onClick={() => onOpenTrade(tradeId)}>
      <div className="arch-stat__l" style={{ marginBottom: 'var(--space-2)' }}>{label}</div>
      {t ? (
        <>
          <div style={{ fontSize: 'var(--text-sm)', marginBottom: 4 }}>
            {win ? win.team_abbrev : t.sides.map((s) => s.team_abbrev).join(' · ')}
            <span className="tbl-muted"> · {t.date.slice(0, 4)}</span>
            <span className="lb-net" style={{ float: 'right' }}>{fmt(t.margin_slot)}</span>
          </div>
          <Tilt signed={t.margin_slot} bandHw={t.band_hw_slot} color={color}
            even={t.verdict === 'even'} edge={t.verdict === 'edge' && !t.incomplete}
            incomplete={t.incomplete} size="compact" animate={false} />
        </>
      ) : <SkeletonLoader height={48} />}
    </button>
  )
}

export default function ArchetypeExplorer({ onOpenTrade }: { onOpenTrade: (id: string) => void }) {
  const [aggs, setAggs] = useState<ArchetypeAgg[] | null>(null)
  const [pick, setPick] = useState('player_for_picks')
  useEffect(() => { getArchetypes().then(setAggs).catch(() => setAggs([])) }, [])

  if (!aggs) return <SkeletonLoader height={400} />
  if (!aggs.length) return <div className="vm-empty">No taggable archetypes in this filter.</div>
  const a = aggs.find((x) => x.archetype === pick) || aggs[0]
  const exemplars = Array.from(new Map(a.exemplars.map((e) => [e.trade_id, e])).values())

  return (
    <div className="t-panel">
      <div className="t-cardhead">
        <div className="t-cardhead__titles">
          <h2 className="t-panel__title">Do the classic trade theses hold?</h2>
          <p className="t-panel__sub">Tested on every settled trade since 2015-16.</p>
        </div>
        <div className="t-cardhead__controls">
          <Tabs options={aggs.map((x) => ({ value: x.archetype, label: x.label }))} value={a.archetype} onChange={setPick} />
        </div>
      </div>

      {/* Split */}
      <p className="arch-insight" style={{ fontWeight: 600 }}>{headline(a)}</p>
      <SplitBar a={a} />
      <p className="t-note" style={{ marginTop: 'var(--space-2)' }}>{takeaway(a)}</p>

      <div className="t-divider" />

      {/* Exemplars */}
      <h3 className="t-region-title">Notable deals</h3>
      <div className="arch-exemplars">
        {exemplars.map((ex) => <ExemplarInset key={ex.trade_id} label={ex.label} tradeId={ex.trade_id} onOpenTrade={onOpenTrade} />)}
      </div>

      {a.timing.length > 0 && (
        <>
          <div className="t-divider" />
          <h3 className="t-region-title">When these trades happen</h3>
          <div className="arch-timing__row">
            {a.timing.map((t) => (
              <div key={t.bucket} className="t-inset">
                <span className="arch-stat__v">{t.decisive_pct}%</span>
                <span className="arch-stat__l">{t.bucket.replace('_', '-')}</span>
                <span className="tbl-muted" style={{ fontSize: 'var(--text-xs)' }}>{t.count} deals · acquiring side ahead</span>
              </div>
            ))}
          </div>
        </>
      )}

      <p className="t-note" style={{ marginTop: 'var(--space-5)' }}>
        Splits cover {a.settled_count} settled deals{a.maturing_count ? ` (${a.maturing_count} still maturing, not yet counted)` : ''}.
        Archetypes are tagged from the trade data alone; rental and salary-dump deals aren't shown (they need
        contract/cap context this source lacks). Timing is by date, an honest proxy for rentals, not a cap tag.
      </p>
    </div>
  )
}
