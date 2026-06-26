/**
 * Trade Outcomes (Handoff 7) — the oriented, entity-first redesign. Three modes (Overview / Traders /
 * Patterns) plus a trader dossier and a single-trade leaf, all reachable by route and search. The unit
 * is the entity and the hypothesis, not the transaction. A retrospective on outcomes, never a grade of
 * the decision at the time.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { ChartPanel, PageHeader, PageLayout, SkeletonLoader, Tabs } from '../components/common'
import { getTeamName } from '../utils/teams'
import Overview from '../components/trades/Overview'
import ValueMap from '../components/trades/ValueMap'
import TraderDossier from '../components/trades/TraderDossier'
import ArchetypeExplorer from '../components/trades/ArchetypeExplorer'
import TradeBalanceCard from '../components/trades/TradeBalanceCard'
import TradeSearch from '../components/trades/TradeSearch'
import { getBoardItem, getValueMap, TradeBoardItem, ValueMapPoint } from '../api/trades'
import './TradeOutcomes.css'

type Mode = 'overview' | 'traders' | 'patterns'
type Kind = 'team' | 'gm'
type Lens = 'slot' | 'actual'
const LS_KIND = 'nhlintel.trades.kind'
const LS_SEL = 'nhlintel.trades.selected'
const BASE = '/tools/trade-outcomes'

function Breadcrumb({ trail }: { trail: { label: string; to?: string }[] }) {
  return (
    <nav className="to-crumb">
      {trail.map((c, i) => (
        <span key={i}>
          {i > 0 && <ChevronRight size={13} className="to-crumb__sep" />}
          {c.to ? <Link to={c.to}>{c.label}</Link> : <span>{c.label}</span>}
        </span>
      ))}
    </nav>
  )
}

function TradeLeaf({ tradeId, lens }: { tradeId: string; lens: Lens }) {
  const [t, setT] = useState<TradeBoardItem | null>(null)
  const [missing, setMissing] = useState(false)
  useEffect(() => { setT(null); getBoardItem(tradeId).then(setT).catch(() => setMissing(true)) }, [tradeId])
  if (missing) return <div className="to-empty">That trade could not be found.</div>
  if (!t) return <SkeletonLoader height={240} />
  return <TradeBalanceCard trade={t} lens={lens} defaultOpen />
}

export default function TradeOutcomes() {
  const { kind: pKind, id: pId, tradeId } = useParams()
  const [sp] = useSearchParams()
  const navigate = useNavigate()
  const mode = (sp.get('mode') as Mode) || 'overview'

  const [lens, setLens] = useState<Lens>('slot')
  const [entityKind, setEntityKind] = useState<Kind>(() => (localStorage.getItem(LS_KIND) as Kind) || 'team')
  const [mapPoints, setMapPoints] = useState<ValueMapPoint[] | null>(null)

  useEffect(() => { localStorage.setItem(LS_KIND, entityKind) }, [entityKind])

  // remember the open entity; on a bare landing, return a previous visitor to their dossier
  useEffect(() => {
    if (pKind && pId) { localStorage.setItem(LS_SEL, `${pKind}/${pId}`); return }
    if (!tradeId && !sp.get('mode')) {
      const remembered = localStorage.getItem(LS_SEL)
      if (remembered) navigate(`${BASE}/${remembered}`, { replace: true })
    }
  }, [pKind, pId, tradeId]) // eslint-disable-line

  // value map for the foregrounded Traders mode
  useEffect(() => {
    if (mode !== 'traders' || pKind || tradeId) return
    setMapPoints(null)
    getValueMap(entityKind, lens).then(setMapPoints).catch(() => setMapPoints([]))
  }, [mode, entityKind, lens, pKind, tradeId])

  const openTrade = (id: string) => navigate(`${BASE}/trade/${encodeURIComponent(id)}`)
  const openEntity = (k: Kind, id: string) => navigate(`${BASE}/${k}/${encodeURIComponent(id)}`)
  const setMode = (m: Mode) => navigate(m === 'overview' ? BASE : `${BASE}?mode=${m}`)

  const isDossier = pKind && pId
  const isLeaf = !!tradeId

  return (
    <PageLayout>
      <div className="to">
        <PageHeader
          title="Trade outcomes"
          subtitle="Who actually wins trades — by team, by GM, and by the kind of deal. Realized value in WAR; a retrospective on outcomes, not a grade of the decision at the time."
        />

        {!isDossier && !isLeaf && (
          <div className="to-controls">
            <Tabs options={[{ value: 'overview', label: 'Overview' }, { value: 'traders', label: 'Traders' }, { value: 'patterns', label: 'Patterns' }]}
              value={mode} onChange={(v) => setMode(v as Mode)} />
            {mode === 'traders' && (
              <Tabs options={[{ value: 'team', label: 'Teams' }, { value: 'gm', label: 'GMs' }]}
                value={entityKind} onChange={(v) => setEntityKind(v as Kind)} />
            )}
            <Tabs options={[{ value: 'slot', label: 'Slot lens' }, { value: 'actual', label: 'Actual lens' }]}
              value={lens} onChange={(v) => setLens(v as Lens)} />
            <TradeSearch onPickEntity={openEntity} onPickTrade={openTrade} />
          </div>
        )}

        {isLeaf ? (
          <section className="to-section">
            <Breadcrumb trail={[{ label: 'Overview', to: BASE }, { label: 'Trade' }]} />
            <TradeLeaf tradeId={tradeId!} lens={lens} />
          </section>
        ) : isDossier ? (
          <section className="to-section">
            <Breadcrumb trail={[
              { label: 'Overview', to: BASE },
              { label: 'Traders', to: `${BASE}?mode=traders` },
              { label: pKind === 'team' ? getTeamName(pId!) : pId! },
            ]} />
            <TraderDossier kind={pKind as Kind} id={pId!} lens={lens} onBack={() => navigate(`${BASE}?mode=traders`)} />
          </section>
        ) : mode === 'overview' ? (
          <section className="to-section">
            <Overview kind={entityKind} lens={lens} onOpenTrade={openTrade} onOpenEntity={openEntity}
              onGoPatterns={() => setMode('patterns')} />
          </section>
        ) : mode === 'patterns' ? (
          <section className="to-section"><ArchetypeExplorer lens={lens} /></section>
        ) : (
          <section className="to-section">
            <ChartPanel title={entityKind === 'team' ? 'The league trade map' : 'GMs as traders'}
              subtitle="value gained vs given up; above the diagonal is a net winner; bubble size is trade volume. Click an entity for its dossier.">
              {mapPoints ? <ValueMap points={mapPoints} onSelect={(id) => openEntity(entityKind, id)} /> : <SkeletonLoader height={460} />}
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
