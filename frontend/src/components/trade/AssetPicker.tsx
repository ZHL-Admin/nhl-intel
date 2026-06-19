/**
 * Asset picker for the Trade Builder — debounced search against /assets/search, spanning players,
 * prospects, and picks for one org. Each result shows its talent value (WAR) and surplus so the
 * user picks with the numbers in view. Selecting an asset adds it to the sending team's ledger.
 */
import { useEffect, useRef, useState } from 'react'
import { Search, User, Sprout, Ticket } from 'lucide-react'
import { searchAssets } from '../../api/assets'
import { TradeableAsset } from '../../api/types'
import { fmtWar, fmtDollarsM } from '../../utils/format'
import './AssetPicker.css'

const TYPE_ICON = { player: User, prospect: Sprout, pick: Ticket } as const

export default function AssetPicker({ orgTeam, usedIds, onAdd }: {
  orgTeam: string
  usedIds: Set<string>
  onAdd: (asset: TradeableAsset) => void
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<TradeableAsset[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancel = false
    setLoading(true)
    const t = setTimeout(async () => {
      try {
        const data = await searchAssets({ q: query.trim(), org: orgTeam, limit: 20 })
        if (!cancel) { setResults(data); setLoading(false) }
      } catch {
        if (!cancel) { setResults([]); setLoading(false) }
      }
    }, 200)
    return () => { cancel = true; clearTimeout(t) }
  }, [query, orgTeam, open])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const choose = (a: TradeableAsset) => { onAdd(a); setQuery(''); setOpen(false) }
  const visible = results.filter((a) => !usedIds.has(a.asset_id))

  return (
    <div className="asset-picker" ref={ref}>
      <div className="asset-picker__input-wrap">
        <Search size={15} className="asset-picker__icon" />
        <input
          className="asset-picker__input"
          value={query}
          placeholder={`Send from ${orgTeam}…`}
          onFocus={() => setOpen(true)}
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
        />
      </div>
      {open && (
        <ul className="asset-picker__results" role="listbox">
          {visible.length === 0 && !loading && (
            <li className="asset-picker__empty">No assets found for {orgTeam}</li>
          )}
          {visible.map((a) => {
            const Icon = TYPE_ICON[a.asset_type]
            return (
              <li key={a.asset_id}>
                <button className="asset-picker__opt" onMouseDown={(e) => { e.preventDefault(); choose(a) }}>
                  <span className={`asset-picker__type asset-picker__type--${a.asset_type}`}><Icon size={13} /></span>
                  <span className="asset-picker__meta">
                    <span className="asset-picker__name">{a.label}</span>
                    <span className="asset-picker__sub">{a.pos_or_slot}</span>
                  </span>
                  <span className="asset-picker__nums">
                    <span className="asset-picker__war">{fmtWar(a.value_war)} WAR</span>
                    <span className="asset-picker__surplus">{fmtDollarsM(a.surplus_dollars, true)}</span>
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
