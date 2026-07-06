/**
 * Trade Outcomes (Handoff 8) — a retrospective on how every NHL trade since 2015-16 actually turned out,
 * in realized WAR. Organized by user INTENT into three carded tabs: Trades (lookup + the rare lopsided
 * deals), Teams & GMs (the value map + records), and Patterns (do the classic theses hold?). Plus two
 * drill states — a team/GM dossier and a single-trade detail. Most trades end roughly even; the page says
 * so plainly and never manufactures a winner the band can't support.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { PageCard, PageLayout, SkeletonLoader, Tabs } from '../components/common'
import { getTeamName } from '../utils/teams'
import TradesLanding from '../components/trades/TradesLanding'
import TeamsGms from '../components/trades/TeamsGms'
import ArchetypeExplorer from '../components/trades/ArchetypeExplorer'
import TraderDossier from '../components/trades/TraderDossier'
import TradeBalanceCard from '../components/trades/TradeBalanceCard'
import TradeSearch from '../components/trades/TradeSearch'
import { getBoardItem, TradeBoardItem } from '../api/trades'
import './TradeOutcomes.css'

type Mode = 'trades' | 'teams-gms' | 'patterns'
type Kind = 'team' | 'gm'
const LS_KIND = 'nhlintel.trades.kind'
const LS_SEL = 'nhlintel.trades.selected'
const BASE = '/studio/trades/history'

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

function TradeLeaf({ tradeId }: { tradeId: string }) {
  const [t, setT] = useState<TradeBoardItem | null>(null)
  const [missing, setMissing] = useState(false)
  useEffect(() => { setT(null); getBoardItem(tradeId).then(setT).catch(() => setMissing(true)) }, [tradeId])
  if (missing) return <div className="to-empty">That trade could not be found.</div>
  if (!t) return <SkeletonLoader height={240} />
  return <TradeBalanceCard trade={t} defaultOpen />
}

export default function TradeOutcomes() {
  const { kind: pKind, id: pId, tradeId } = useParams()
  const [sp] = useSearchParams()
  const navigate = useNavigate()
  const mode = (sp.get('mode') as Mode) || 'trades'

  const [entityKind, setEntityKind] = useState<Kind>(() => (localStorage.getItem(LS_KIND) as Kind) || 'team')
  useEffect(() => { localStorage.setItem(LS_KIND, entityKind) }, [entityKind])
  useEffect(() => { if (pKind && pId) localStorage.setItem(LS_SEL, `${pKind}/${pId}`) }, [pKind, pId])

  const openTrade = (id: string) => navigate(`${BASE}/trade/${encodeURIComponent(id)}`)
  const openEntity = (k: Kind, id: string) => navigate(`${BASE}/${k}/${encodeURIComponent(id)}`)
  const setMode = (m: Mode) => navigate(m === 'trades' ? BASE : `${BASE}?mode=${m}`)

  const isDossier = pKind && pId
  const isLeaf = !!tradeId

  // The header's controls slot: the page tabbar on the index modes, a breadcrumb in the drill states.
  const controls = isLeaf ? (
    <Breadcrumb trail={[{ label: 'Trades', to: BASE }, { label: 'Trade' }]} />
  ) : isDossier ? (
    <Breadcrumb trail={[
      { label: 'Trades', to: BASE },
      { label: 'Teams & GMs', to: `${BASE}?mode=teams-gms` },
      { label: pKind === 'team' ? getTeamName(pId!) : pId! },
    ]} />
  ) : (
    <div className="to-tabbar">
      <Tabs options={[{ value: 'trades', label: 'Trades' }, { value: 'teams-gms', label: 'Teams & GMs' }, { value: 'patterns', label: 'Patterns' }]}
        value={mode} onChange={(v) => setMode(v as Mode)} />
      <span className="to-tabbar__spacer" />
      {mode !== 'trades' && <TradeSearch onPickEntity={openEntity} onPickTrade={openTrade} />}
    </div>
  )

  return (
    <PageLayout>
      <div className="to">
        <PageCard
          title="Trade history"
          subtitle="Every trade since 2015-16, scored by what actually happened next."
          controls={controls}
        >
          {isLeaf ? (
            <TradeLeaf tradeId={tradeId!} />
          ) : isDossier ? (
            <TraderDossier kind={pKind as Kind} id={pId!} onOpenTrade={openTrade}
              onBack={() => navigate(`${BASE}?mode=teams-gms`)} />
          ) : mode === 'teams-gms' ? (
            <TeamsGms kind={entityKind} onKind={setEntityKind} onOpenEntity={openEntity} />
          ) : mode === 'patterns' ? (
            <ArchetypeExplorer onOpenTrade={openTrade} />
          ) : (
            <TradesLanding base={BASE} onOpenEntity={openEntity} onOpenTrade={openTrade} />
          )}
        </PageCard>
      </div>
    </PageLayout>
  )
}
