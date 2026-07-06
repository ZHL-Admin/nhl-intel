/**
 * EntityPicker (Blueprint P3) — the ONE modal for every "choose a player". Omnibox input, session-local
 * recents (last 8), results as Player M rows, position filter chips, Enter selects the top hit, Esc
 * closes. Replaces the five bespoke pickers across the Studio tools.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import EntityIdentity, { type PlayerIdentity } from './EntityIdentity'
import { searchPlayers } from '../../api/tools'
import type { PlayerSearchResult } from '../../api/types'
import './EntityPicker.css'

const RECENT_KEY = 'oi.picker.recent'
const POSITIONS = ['C', 'L', 'R', 'D', 'G']

function loadRecent(): PlayerSearchResult[] {
  try { return JSON.parse(sessionStorage.getItem(RECENT_KEY) ?? '[]') } catch { return [] }
}
function pushRecent(p: PlayerSearchResult) {
  const next = [p, ...loadRecent().filter((r) => r.player_id !== p.player_id)].slice(0, 8)
  try { sessionStorage.setItem(RECENT_KEY, JSON.stringify(next)) } catch { /* noop */ }
}

const toIdentity = (p: PlayerSearchResult): PlayerIdentity => ({
  id: p.player_id,
  name: p.name ?? `#${p.player_id}`,
  position: p.position,
  teamAbbrev: p.team_abbrev,
  archetypes: p.archetype ? [p.archetype] : undefined,
})

interface EntityPickerProps {
  open: boolean
  onClose: () => void
  onSelect: (player: PlayerSearchResult) => void
  title?: string
  season?: string
}

export default function EntityPicker({ open, onClose, onSelect, title = 'Search players', season }: EntityPickerProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PlayerSearchResult[]>([])
  const [posFilter, setPosFilter] = useState<string | null>(null)
  const [searching, setSearching] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    setQuery(''); setResults([]); setPosFilter(null)
    const t = setTimeout(() => inputRef.current?.focus(), 30)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => { clearTimeout(t); document.removeEventListener('keydown', onKey) }
  }, [open, onClose])

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) { setResults([]); setSearching(false); return }
    setSearching(true)
    const h = setTimeout(() => {
      searchPlayers(q, 12, season)
        .then((r) => { setResults(r); setSearching(false) })
        .catch(() => { setResults([]); setSearching(false) })
    }, 180)
    return () => clearTimeout(h)
  }, [query, season])

  const recent = useMemo(() => (open ? loadRecent() : []), [open])
  const shown = (query.trim().length >= 2 ? results : recent)
    .filter((p) => !posFilter || (p.position ?? '').toUpperCase().startsWith(posFilter))

  const choose = (p: PlayerSearchResult) => { pushRecent(p); onSelect(p); onClose() }
  const onKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter' && shown[0]) choose(shown[0]) }

  if (!open) return null
  return (
    <div className="entity-picker" role="dialog" aria-modal="true" aria-label={title}>
      <div className="entity-picker__scrim" onClick={onClose} />
      <div className="entity-picker__panel">
        <div className="entity-picker__omnibox">
          <Search size={18} className="entity-picker__search-icon" />
          <input
            ref={inputRef}
            className="entity-picker__input"
            placeholder={title}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <button type="button" className="entity-picker__close" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>

        <div className="entity-picker__chips">
          {POSITIONS.map((pos) => (
            <button key={pos} type="button"
              className={`entity-picker__chip ${posFilter === pos ? 'is-on' : ''}`}
              onClick={() => setPosFilter((f) => (f === pos ? null : pos))}>{pos}</button>
          ))}
        </div>

        <div className="entity-picker__results">
          {query.trim().length < 2 && recent.length > 0 && <div className="entity-picker__grouphead">Recent</div>}
          {shown.map((p) => (
            <button key={p.player_id} type="button" className="entity-picker__row" onClick={() => choose(p)}>
              <EntityIdentity kind="player" size="m" player={toIdentity(p)} />
            </button>
          ))}
          {shown.length === 0 && (
            <div className="entity-picker__empty">
              {searching ? 'Searching…' : query.trim().length >= 2 ? 'No players found' : 'Type to search players'}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
