/**
 * Shared player search-and-pick control (Phase 5.2, blueprint 6.1).
 *
 * Debounced search against GET /players/search, keyboard navigable (up/down/enter/esc), shows
 * headshot + team + archetype chip per result. Renders either the selected player (with a clear
 * button) or the search input. Reused by the Lineup Lab and the embedded LineSwapWidget.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { Search, X } from 'lucide-react'
import { searchPlayers } from '../../api/tools'
import { PlayerSearchResult } from '../../api/types'
import { getTeamLogoUrl } from '../../utils/teams'
import './PlayerPicker.css'

interface PlayerPickerProps {
  value?: PlayerSearchResult | null
  onSelect: (player: PlayerSearchResult) => void
  onClear?: () => void
  season?: string
  placeholder?: string
  /** Restrict results: 'F' = forwards (C/L/R), 'D' = defensemen, or an exact position 'C'|'L'|'R'. */
  positionFilter?: 'F' | 'D' | 'C' | 'L' | 'R'
}

export default function PlayerPicker({
  value, onSelect, onClear, season, placeholder = 'Search players…', positionFilter,
}: PlayerPickerProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PlayerSearchResult[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [loading, setLoading] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  const matchesFilter = useCallback((p: PlayerSearchResult) => {
    if (!positionFilter) return true
    const pos = p.position ?? ''
    if (positionFilter === 'F') return ['C', 'L', 'R'].includes(pos)
    if (positionFilter === 'D') return pos === 'D'
    return pos === positionFilter   // exact position: 'C' | 'L' | 'R'
  }, [positionFilter])

  useEffect(() => {
    if (query.trim().length < 1) { setResults([]); return }
    let cancelled = false
    setLoading(true)
    const t = setTimeout(async () => {
      try {
        const data = await searchPlayers(query.trim(), 12, season)
        if (!cancelled) {
          setResults(data.filter(matchesFilter))
          setActive(0)
          setOpen(true)
        }
      } catch {
        if (!cancelled) setResults([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, 220)
    return () => { cancelled = true; clearTimeout(t) }
  }, [query, season, matchesFilter])

  // close on outside click
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const choose = (p: PlayerSearchResult) => {
    onSelect(p)
    setQuery(''); setResults([]); setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); choose(results[active]) }
    else if (e.key === 'Escape') { setOpen(false) }
  }

  if (value) {
    return (
      <div className="player-picker player-picker--selected">
        {value.headshot_url && (
          <img className="player-picker__headshot" src={value.headshot_url} alt=""
               onError={(e) => ((e.target as HTMLImageElement).style.visibility = 'hidden')} />
        )}
        <div className="player-picker__selected-meta">
          <span className="player-picker__name">{value.name}</span>
          <span className="player-picker__sub">
            {value.team_abbrev ?? ''} · {value.position ?? ''}
            {value.archetype && <span className="player-picker__chip">{value.archetype}</span>}
          </span>
        </div>
        {onClear && (
          <button className="player-picker__clear" onClick={onClear} aria-label="Remove player">
            <X size={16} />
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="player-picker" ref={boxRef}>
      <div className="player-picker__input-wrap">
        <Search size={16} className="player-picker__search-icon" />
        <input
          className="player-picker__input"
          value={query}
          placeholder={placeholder}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && (results.length > 0 || (!loading && query.trim().length >= 1)) && (
        <ul className="player-picker__results" role="listbox">
          {results.length === 0 && !loading && (
            <li className="player-picker__empty">No players found</li>
          )}
          {results.map((p, i) => (
            <li
              key={p.player_id}
              role="option"
              aria-selected={i === active}
              className={`player-picker__result ${i === active ? 'player-picker__result--active' : ''}`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => { e.preventDefault(); choose(p) }}
            >
              {p.headshot_url
                ? <img className="player-picker__headshot" src={p.headshot_url} alt=""
                       onError={(e) => ((e.target as HTMLImageElement).style.visibility = 'hidden')} />
                : <span className="player-picker__headshot player-picker__headshot--blank" />}
              <div className="player-picker__result-meta">
                <span className="player-picker__name">{p.name}</span>
                <span className="player-picker__sub">
                  {p.team_abbrev && (
                    <img className="player-picker__team-logo" src={getTeamLogoUrl(p.team_abbrev)} alt=""
                         onError={(e) => ((e.target as HTMLImageElement).style.visibility = 'hidden')} />
                  )}
                  {p.position ?? ''}
                  {p.archetype && <span className="player-picker__chip">{p.archetype}</span>}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
