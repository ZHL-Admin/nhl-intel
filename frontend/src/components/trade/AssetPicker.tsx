/**
 * Asset picker for the Trade Builder. Loads a team's FULL asset list up front (players, prospects,
 * picks — not a top-N slice) so the card has content immediately. Two ways to select: click a TYPE
 * button (Players / Prospects / Picks) to browse that group, or type to search across everything.
 * Player/prospect rows show a headshot; picks show an icon. Everything stays reachable and grouped.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, User, Sprout, Ticket } from 'lucide-react'
import { PlayerAvatar } from '../common'
import { searchAssets } from '../../api/assets'
import { TradeableAsset } from '../../api/types'
import { fmtWar, fmtDollarsM } from '../../utils/format'
import './AssetPicker.css'

type Kind = TradeableAsset['asset_type']
const GROUPS: { key: Kind; label: string; Icon: typeof User }[] = [
  { key: 'player', label: 'Players', Icon: User },
  { key: 'prospect', label: 'Prospects', Icon: Sprout },
  { key: 'pick', label: 'Draft picks', Icon: Ticket },
]

export default function AssetPicker({ orgTeam, usedIds, onAdd }: {
  orgTeam: string
  usedIds: Set<string>
  onAdd: (asset: TradeableAsset) => void
}) {
  const [query, setQuery] = useState('')
  const [all, setAll] = useState<TradeableAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [typeFilter, setTypeFilter] = useState<Kind | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  // load the team's FULL list up front (org max ~83; 100 covers every team), so counts show at once
  useEffect(() => {
    let cancel = false
    setLoading(true)
    searchAssets({ org: orgTeam, limit: 100 })
      .then((d) => { if (!cancel) setAll(d) })
      .catch(() => { if (!cancel) setAll([]) })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [orgTeam])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const available = useMemo(() => all.filter((a) => !usedIds.has(a.asset_id)), [all, usedIds])
  const countOf = (k: Kind) => available.filter((a) => a.asset_type === k).length

  // searching looks across ALL types; a type button narrows to one group
  const activeType = query.trim() ? null : typeFilter
  const grouped = useMemo(() => {
    const ql = query.trim().toLowerCase()
    const pool = available.filter((a) => (!ql || a.label.toLowerCase().includes(ql))
      && (!activeType || a.asset_type === activeType))
    return GROUPS.map((g) => {
      const items = pool.filter((a) => a.asset_type === g.key)
      items.sort((a, b) => g.key === 'pick'
        ? a.label.localeCompare(b.label)
        : (b.value_war ?? -99) - (a.value_war ?? -99))
      return { ...g, items }
    }).filter((g) => g.items.length > 0)
  }, [available, query, activeType])

  const total = grouped.reduce((n, g) => n + g.items.length, 0)
  const choose = (a: TradeableAsset) => { onAdd(a); setQuery('') }
  const openType = (k: Kind) => { setTypeFilter(k); setQuery(''); setOpen(true) }

  return (
    <div className="asset-picker" ref={ref}>
      <div className="asset-picker__bar">
        {GROUPS.filter((g) => countOf(g.key) > 0).map((g) => (
          <button key={g.key} type="button"
                  className={`asset-picker__typebtn${activeType === g.key && open ? ' asset-picker__typebtn--on' : ''}`}
                  onClick={() => openType(g.key)}>
            <g.Icon size={14} /> {g.label} <span className="asset-picker__typebtn-n">{countOf(g.key)}</span>
          </button>
        ))}
      </div>
      <div className="asset-picker__input-wrap">
        <Search size={15} className="asset-picker__icon" />
        <input
          className="asset-picker__input"
          value={query}
          placeholder={`Search ${orgTeam}…`}
          onFocus={() => { setTypeFilter(null); setOpen(true) }}
          onChange={(e) => { setQuery(e.target.value); setTypeFilter(null); setOpen(true) }}
        />
      </div>

      {open && (
        <div className="asset-picker__results" role="listbox">
          {loading && <div className="asset-picker__empty">Loading {orgTeam} assets…</div>}
          {!loading && total === 0 && <div className="asset-picker__empty">No assets match for {orgTeam}.</div>}
          {grouped.map((g) => (
            <div key={g.key} className="asset-picker__group">
              <div className="asset-picker__group-head">
                <g.Icon size={12} /> {g.label} <span className="asset-picker__group-n">{g.items.length}</span>
              </div>
              {g.items.map((a) => (
                <button key={a.asset_id} className="asset-picker__opt"
                        onMouseDown={(e) => { e.preventDefault(); choose(a) }}>
                  {a.asset_type !== 'pick' && a.player_id
                    ? <PlayerAvatar id={a.player_id} team={a.org_team} name={a.label} size={26} showTeamLogo={false} />
                    : <span className={`asset-picker__type asset-picker__type--${a.asset_type}`}><g.Icon size={13} /></span>}
                  <span className="asset-picker__meta">
                    <span className="asset-picker__name">{a.label}</span>
                    <span className="asset-picker__sub">{a.pos_or_slot}</span>
                  </span>
                  <span className="asset-picker__nums">
                    <span className="asset-picker__war">{fmtWar(a.value_war)} WAR</span>
                    <span className="asset-picker__surplus">{fmtDollarsM(a.surplus_dollars, true)}</span>
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
