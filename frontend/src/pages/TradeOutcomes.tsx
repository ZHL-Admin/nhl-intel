/**
 * Trade Outcomes (Handoff 6) — entity-first redesign. The unit of the page is the entity (team or GM)
 * and the hypothesis (a trade archetype), not the transaction. Traders mode: a league value map ->
 * a trader dossier -> the single-trade balance-bar leaf. Patterns mode: the archetype explorer.
 * A retrospective on realized outcomes, never a grade of the decision at the time.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChartPanel, PageHeader, PageLayout, SkeletonLoader, Tabs } from '../components/common'
import ValueMap from '../components/trades/ValueMap'
import TraderDossier from '../components/trades/TraderDossier'
import ArchetypeExplorer from '../components/trades/ArchetypeExplorer'
import TradeSearch from '../components/trades/TradeSearch'
import { getValueMap, ValueMapPoint } from '../api/trades'
import './TradeOutcomes.css'

type Mode = 'traders' | 'patterns'
type Kind = 'team' | 'gm'
type Lens = 'slot' | 'actual'
type Selection = { kind: Kind; id: string } | null

const LS_KIND = 'nhlintel.trades.kind'
const LS_SEL = 'nhlintel.trades.selected'

export default function TradeOutcomes() {
  const [mode, setMode] = useState<Mode>('traders')
  const [lens, setLens] = useState<Lens>('slot')
  const [kind, setKind] = useState<Kind>(() => (localStorage.getItem(LS_KIND) as Kind) || 'team')
  const [selected, setSelected] = useState<Selection>(() => {
    try { return JSON.parse(localStorage.getItem(LS_SEL) || 'null') } catch { return null }
  })
  const [points, setPoints] = useState<ValueMapPoint[] | null>(null)

  useEffect(() => { localStorage.setItem(LS_KIND, kind) }, [kind])
  useEffect(() => {
    if (selected) localStorage.setItem(LS_SEL, JSON.stringify(selected))
    else localStorage.removeItem(LS_SEL)
  }, [selected])

  // load the value map when in Traders mode with no entity open
  useEffect(() => {
    if (mode !== 'traders' || selected) return
    setPoints(null)
    getValueMap(kind, lens).then(setPoints).catch(() => setPoints([]))
  }, [mode, kind, lens, selected])

  const select = (id: string) => setSelected({ kind, id })

  return (
    <PageLayout>
      <div className="to">
        <PageHeader
          title="Trade outcomes"
          subtitle="Who actually wins trades — by team, by GM, and by the kind of deal. Realized value in WAR; a retrospective on outcomes, not a grade of the decision at the time."
        />

        <div className="to-controls">
          <Tabs options={[{ value: 'traders', label: 'Traders' }, { value: 'patterns', label: 'Patterns' }]}
            value={mode} onChange={(v) => setMode(v as Mode)} />
          {mode === 'traders' && !selected && (
            <Tabs options={[{ value: 'team', label: 'Teams' }, { value: 'gm', label: 'GMs' }]}
              value={kind} onChange={(v) => setKind(v as Kind)} />
          )}
          <Tabs options={[{ value: 'slot', label: 'Slot lens' }, { value: 'actual', label: 'Actual lens' }]}
            value={lens} onChange={(v) => setLens(v as Lens)} />
          <TradeSearch onPickEntity={(k, id) => { setKind(k); setMode('traders'); setSelected({ kind: k, id }) }} />
        </div>

        {mode === 'patterns' ? (
          <section className="to-section"><ArchetypeExplorer lens={lens} /></section>
        ) : selected ? (
          <section className="to-section">
            <TraderDossier kind={selected.kind} id={selected.id} lens={lens} onBack={() => setSelected(null)} />
          </section>
        ) : (
          <section className="to-section">
            <ChartPanel title={kind === 'team' ? 'The league trade map' : 'GMs as traders'}
              subtitle="Value gained vs given up. Above the diagonal is a net winner; bubble size is trade volume. Click an entity for its dossier.">
              {points ? <ValueMap points={points} onSelect={select} /> : <SkeletonLoader height={460} />}
            </ChartPanel>
          </section>
        )}

        <p className="to-footnote">
          GM attribution is to the decision-maker of record from a curated tenure table (approximate near
          handovers; the GM is not the sole decision-maker). The slot lens values picks at their slot's
          expectation and isolates the trade; the actual lens values a pick by the player it became and is
          partly unresolved. Bands are real; "too close" means even within the margin; incomplete recent
          trades are excluded by default. See the <Link to="/learn/archetypes">methodology</Link>.
        </p>
      </div>
    </PageLayout>
  )
}
