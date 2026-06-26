/**
 * Leaderboards (Handoff 7 §4.3) — the ranked complement to the value map. Tabs: Trades | Teams | GMs;
 * every row carries a 60px inline tilt sparkline so the ranking is also visual.
 */
import { useEffect, useMemo, useState } from 'react'
import { Tabs, SkeletonLoader, Select } from '../common'
import { getTeamColor, getTeamLogoUrl } from '../../utils/teams'
import {
  getTradeBoard, getValueMap, TradeBoardItem, ValueMapPoint,
} from '../../api/trades'
import Tilt from './Tilt'
import './trades.css'

const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`
type Tab = 'trades' | 'team' | 'gm'

export default function Leaderboards({ lens, onOpenTrade, onOpenEntity }: {
  lens: 'slot' | 'actual'
  onOpenTrade: (id: string) => void
  onOpenEntity: (kind: 'team' | 'gm', id: string) => void
}) {
  const [tab, setTab] = useState<Tab>('trades')
  const [tradeSort, setTradeSort] = useState<'lopsided' | 'closest' | 'recent'>('lopsided')
  const [entitySort, setEntitySort] = useState<'best' | 'worst'>('best')
  const [trades, setTrades] = useState<TradeBoardItem[] | null>(null)
  const [teams, setTeams] = useState<ValueMapPoint[] | null>(null)
  const [gms, setGms] = useState<ValueMapPoint[] | null>(null)

  useEffect(() => {
    if (tab === 'trades') { setTrades(null); getTradeBoard({ sort: tradeSort, lens, limit: 12 }).then(setTrades).catch(() => setTrades([])) }
  }, [tab, tradeSort, lens])
  useEffect(() => {
    if (tab === 'team' && !teams) getValueMap('team', lens).then(setTeams).catch(() => setTeams([]))
    if (tab === 'gm' && !gms) getValueMap('gm', lens).then(setGms).catch(() => setGms([]))
  }, [tab, lens]) // eslint-disable-line

  const entities = useMemo(() => {
    const src = tab === 'team' ? teams : gms
    if (!src) return null
    return [...src].sort((a, b) => entitySort === 'best' ? b.net_war - a.net_war : a.net_war - b.net_war).slice(0, 12)
  }, [tab, teams, gms, entitySort])

  return (
    <div className="lb t-panel">
      <div className="lb-controls">
        <Tabs options={[{ value: 'trades', label: 'Trades' }, { value: 'team', label: 'Teams' }, { value: 'gm', label: 'GMs' }]}
          value={tab} onChange={(v) => setTab(v as Tab)} />
        {tab === 'trades'
          ? <Select value={tradeSort} onChange={(v) => setTradeSort(v as any)}
              options={[{ value: 'lopsided', label: 'Most lopsided' }, { value: 'closest', label: 'Closest' }, { value: 'recent', label: 'Recent' }]} />
          : <Select value={entitySort} onChange={(v) => setEntitySort(v as any)}
              options={[{ value: 'best', label: 'Best' }, { value: 'worst', label: 'Worst' }]} />}
      </div>

      {tab === 'trades' ? (
        trades ? (trades.length ? trades.map((t) => {
          const win = t.sides.find((s) => s.team_id === t.winner_team_id)
          const lose = t.sides.find((s) => s.team_id !== t.winner_team_id)
          const color = win ? getTeamColor(win.team_abbrev) : 'var(--color-text-muted)'
          return (
            <div key={t.trade_id} className="lb-row" onClick={() => onOpenTrade(t.trade_id)}>
              <span className="lb-rank" />
              <span className="lb-name">
                {win && <img src={getTeamLogoUrl(win.team_abbrev)} alt="" className="tbl-logo" />}
                <span>{win ? win.team_abbrev : '—'}{lose ? ` over ${lose.team_abbrev}` : ''} <span className="tbl-muted">{t.date.slice(0, 4)}</span></span>
              </span>
              <Tilt signed={t.margin_slot} bandHw={t.band_hw_slot} color={color}
                tooClose={t.verdict === 'too_close'} incomplete={t.incomplete} size="sparkline" animate={false} />
              <span className="lb-net">{fmt(t.margin_slot)}</span>
            </div>
          )
        }) : <div className="vm-empty">No trades.</div>) : <SkeletonLoader height={300} />
      ) : (
        entities ? (entities.length ? entities.map((e, i) => (
          <div key={e.id} className="lb-row" onClick={() => onOpenEntity(tab as 'team' | 'gm', e.id)}>
            <span className="lb-rank">{i + 1}</span>
            <span className="lb-name">
              <img src={getTeamLogoUrl(e.team_abbrev_for_color)} alt="" className="tbl-logo" />
              <span>{e.label}</span>
            </span>
            <Tilt signed={e.net_war} bandHw={e.net_band_hw} color={getTeamColor(e.team_abbrev_for_color)}
              tooClose={false} incomplete={false} size="sparkline" animate={false} />
            <span className={`lb-net ${e.net_war >= 0 ? 'dos-pos' : 'dos-neg'}`}>{fmt(e.net_war)}</span>
          </div>
        )) : <div className="vm-empty">No entities.</div>) : <SkeletonLoader height={300} />
      )}
    </div>
  )
}
