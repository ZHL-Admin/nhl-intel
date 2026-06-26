/**
 * Archetype explorer (Handoff 6, surface 5C / "Patterns" mode) — tests trade theses on the whole
 * dataset. Pick an archetype; see the aggregate split + exemplar trades. Only data-taggable archetypes
 * (no rental/salary-dump, which the trades CSV cannot support).
 */
import { useEffect, useMemo, useState } from 'react'
import { Tabs, SkeletonLoader } from '../common'
import { getArchetypes, getBoardItem, ArchetypeAgg, TradeBoardItem } from '../../api/trades'
import TradeBalanceCard from './TradeBalanceCard'
import './trades.css'

function insight(a: ArchetypeAgg): string {
  const s = a.split
  if (a.archetype === 'player_for_picks') {
    return `Across ${a.trade_count} player-for-picks deals, the side that got the player won ${s.player_side_won_pct}%, the picks paid off ${s.pick_side_won_pct}%, and ${s.even_pct}% were even within the margin.`
  }
  if (a.archetype === 'player_for_player') {
    return `Across ${a.trade_count} player-for-player deals, one side won clearly ${s.decisive_pct}% of the time; ${s.even_pct}% were too close to call.`
  }
  if (a.archetype === 'picks_for_picks') {
    return `Across ${a.trade_count} picks-for-picks deals, ${s.even_pct}% were even within the margin — pick-only swaps rarely move realized value decisively.`
  }
  if (a.archetype === 'blockbuster') {
    return `Across ${a.trade_count} blockbusters (8+ WAR moved), one side won clearly ${s.decisive_pct}% of the time; ${s.even_pct}% stayed within the band.`
  }
  return `Across ${a.trade_count} three-team deals, one side won clearly ${s.decisive_pct}% of the time.`
}

function Exemplars({ a, lens }: { a: ArchetypeAgg; lens: 'slot' | 'actual' }) {
  const [items, setItems] = useState<Record<string, TradeBoardItem>>({})
  const ids = useMemo(() => Array.from(new Set(Object.values(a.exemplars))).filter(Boolean), [a])
  useEffect(() => {
    let live = true
    Promise.all(ids.map((id) => getBoardItem(id).then((t) => [id, t] as const).catch(() => null)))
      .then((res) => { if (live) setItems(Object.fromEntries(res.filter(Boolean) as any)) })
    return () => { live = false }
  }, [a.archetype])
  const order: [string, string][] = [
    ['biggest_for_a', 'Biggest win one way'],
    ['biggest_for_b', 'Biggest win the other way'],
    ['closest', 'Closest call'],
  ]
  return (
    <div className="arch-exemplars">
      {order.map(([k, label]) => {
        const t = items[a.exemplars[k]]
        return (
          <div key={k}>
            <div className="arch-stat__l" style={{ marginBottom: 'var(--space-2)' }}>{label}</div>
            {t ? <TradeBalanceCard trade={t} lens={lens} /> : <SkeletonLoader height={120} />}
          </div>
        )
      })}
    </div>
  )
}

export default function ArchetypeExplorer({ lens }: { lens: 'slot' | 'actual' }) {
  const [aggs, setAggs] = useState<ArchetypeAgg[] | null>(null)
  const [pick, setPick] = useState('player_for_picks')
  useEffect(() => { getArchetypes(lens).then(setAggs).catch(() => setAggs([])) }, [lens])

  if (!aggs) return <SkeletonLoader height={400} />
  if (!aggs.length) return <div className="vm-empty">No taggable archetypes in this filter.</div>
  const current = aggs.find((a) => a.archetype === pick) || aggs[0]

  return (
    <div className="arch">
      <div className="t-panel">
      <Tabs options={aggs.map((a) => ({ value: a.archetype, label: a.label }))}
        value={current.archetype} onChange={setPick} />
      <p className="arch-insight">{insight(current)}</p>
      <div className="arch-strip">
        {Object.entries(current.split).map(([k, v]) => (
          <div key={k} className="arch-stat">
            <span className="arch-stat__v">{v}%</span>
            <span className="arch-stat__l">{k.replace(/_pct$/, '').replace(/_/g, ' ')}</span>
          </div>
        ))}
        <div className="arch-stat"><span className="arch-stat__v">{current.trade_count}</span><span className="arch-stat__l">deals</span></div>
      </div>
      {current.timing.length > 0 && (
        <div className="arch-timing">
          <div className="dos-section-title">When these trades happen</div>
          <div className="arch-timing__row">
            {current.timing.map((t) => (
              <div key={t.bucket} className="arch-timing__cell">
                <span className="arch-stat__v">{t.decisive_pct}%</span>
                <span className="arch-stat__l">{t.bucket.replace('_', '-')}</span>
                <span className="tbl-muted" style={{ fontSize: 'var(--text-xs)' }}>{t.count} deals · decisive</span>
              </div>
            ))}
          </div>
          <p className="tbl-muted" style={{ fontSize: 'var(--text-xs)', marginTop: 'var(--space-2)' }}>
            By timing, not contract status — we have trade dates, not cap or expiry, so the deadline bucket is an honest proxy for rentals, not a salary-dump tag.
          </p>
        </div>
      )}
      </div>{/* /.t-panel */}

      <div className="dos-section-title">Notable deals</div>
      <Exemplars a={current} lens={lens} />
      <p className="arch-note">
        Archetypes are tagged from the trade data alone. Rental and salary-dump deals are not shown — they
        need contract-expiry and cap context at trade time that this source lacks. A retrospective on
        outcomes, not a grade of the decision at the time.
      </p>
    </div>
  )
}
