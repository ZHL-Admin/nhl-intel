/**
 * Asset picker for the Trade Builder. Loads the FULL asset list for one org (players, prospects,
 * and picks — not a top-N slice) and groups it players -> prospects -> picks so everything a team
 * can trade is reachable. Typing filters the loaded list instantly. Each row shows talent value
 * (WAR) and surplus so the user picks with the numbers in view.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, User, Sprout, Ticket } from 'lucide-react'
import { searchAssets } from '../../api/assets'
import { TradeableAsset } from '../../api/types'
import { fmtWar, fmtDollarsM } from '../../utils/format'
import './AssetPicker.css'

const GROUPS: { key: TradeableAsset['asset_type']; label: string; Icon: typeof User }[] = [
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
  const [loaded, setLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // load the team's FULL asset list once (org max is ~83; 100 covers every team). Lazy on first open.
  useEffect(() => { setAll([]); setLoaded(false) }, [orgTeam])
  useEffect(() => {
    if (!open || loaded) return
    let cancel = false
    setLoading(true)
    searchAssets({ org: orgTeam, limit: 100 })
      .then((d) => { if (!cancel) { setAll(d); setLoaded(true) } })
      .catch(() => { if (!cancel) { setAll([]); setLoaded(true) } })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [open, loaded, orgTeam])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const choose = (a: TradeableAsset) => { onAdd(a); setQuery('') }

  // group players -> prospects -> picks; players/prospects by WAR desc, picks by year+round (label)
  const grouped = useMemo(() => {
    const ql = query.trim().toLowerCase()
    const pool = all.filter((a) => !usedIds.has(a.asset_id) && (!ql || a.label.toLowerCase().includes(ql)))
    return GROUPS.map((g) => {
      const items = pool.filter((a) => a.asset_type === g.key)
      items.sort((a, b) => g.key === 'pick'
        ? a.label.localeCompare(b.label)
        : (b.value_war ?? -99) - (a.value_war ?? -99))
      return { ...g, items }
    }).filter((g) => g.items.length > 0)
  }, [all, usedIds, query])

  const total = grouped.reduce((n, g) => n + g.items.length, 0)

  return (
    <div className="asset-picker" ref={ref}>
      <div className="asset-picker__input-wrap">
        <Search size={15} className="asset-picker__icon" />
        <input
          className="asset-picker__input"
          value={query}
          placeholder={`Search or browse ${orgTeam}…`}
          onFocus={() => setOpen(true)}
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
        />
      </div>
      {open && (
        <div className="asset-picker__results" role="listbox">
          {loading && !loaded && <div className="asset-picker__empty">Loading {orgTeam} assets…</div>}
          {loaded && total === 0 && <div className="asset-picker__empty">No assets match for {orgTeam}.</div>}
          {grouped.map((g) => (
            <div key={g.key} className="asset-picker__group">
              <div className="asset-picker__group-head">
                <g.Icon size={12} /> {g.label} <span className="asset-picker__group-n">{g.items.length}</span>
              </div>
              {g.items.map((a) => (
                <button key={a.asset_id} className="asset-picker__opt"
                        onMouseDown={(e) => { e.preventDefault(); choose(a) }}>
                  <span className={`asset-picker__type asset-picker__type--${a.asset_type}`}><g.Icon size={13} /></span>
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
