/**
 * Command palette (§6.1): a centered 560px dialog reusing the site's team + player search.
 * Opens on ⌘K (Ctrl+K off Mac), full keyboard support (arrows, Enter, Escape), focus trap,
 * and focus restore. Mounted once by PageLayout; the NavBar trigger dispatches the same open
 * event. Mobile: full-screen sheet.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { DIVISIONS, getTeamLogoUrl, getTeamName, getPlayerHeadshotUrl } from '../../utils/teams'
import { searchPlayers } from '../../api/tools'
import type { PlayerSearchResult } from '../../api/types'
import './CommandPalette.css'

export const PALETTE_OPEN_EVENT = 'rt:open-palette'

type Item =
  | { kind: 'team'; id: number; abbrev: string; name: string; to: string }
  | { kind: 'player'; id: number; name: string; meta: string; headshot: string; to: string }

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [players, setPlayers] = useState<PlayerSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const restoreFocus = useRef<HTMLElement | null>(null)
  const navigate = useNavigate()

  const close = useCallback(() => {
    setOpen(false)
    setQuery('')
    setPlayers([])
    setActive(0)
    restoreFocus.current?.focus()
  }, [])

  const openPalette = useCallback(() => {
    restoreFocus.current = document.activeElement as HTMLElement | null
    setOpen(true)
  }, [])

  // Global ⌘K / Ctrl+K + custom open event from the NavBar trigger.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault()
        openPalette()
      }
    }
    const onOpen = () => openPalette()
    document.addEventListener('keydown', onKey)
    window.addEventListener(PALETTE_OPEN_EVENT, onOpen)
    return () => {
      document.removeEventListener('keydown', onKey)
      window.removeEventListener(PALETTE_OPEN_EVENT, onOpen)
    }
  }, [openPalette])

  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])

  // Debounced player search; teams matched client-side.
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) { setPlayers([]); setSearching(false); return }
    setSearching(true)
    const h = setTimeout(() => {
      searchPlayers(q, 6)
        .then((r) => { setPlayers(r); setSearching(false) })
        .catch(() => { setPlayers([]); setSearching(false) })
    }, 200)
    return () => clearTimeout(h)
  }, [query])

  const allTeams = useMemo(() => DIVISIONS.flatMap((d) => d.teams), [])
  const items = useMemo<Item[]>(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    const teams: Item[] = allTeams
      .filter((t) => getTeamName(t.abbrev).toLowerCase().includes(q) || t.abbrev.toLowerCase().includes(q))
      .slice(0, 4)
      .map((t) => ({ kind: 'team', id: t.id, abbrev: t.abbrev, name: getTeamName(t.abbrev), to: `/teams/${t.id}` }))
    const ppl: Item[] = players.map((p) => ({
      kind: 'player',
      id: p.player_id,
      name: p.name ?? `#${p.player_id}`,
      meta: [p.position, p.team_abbrev].filter(Boolean).join(' · '),
      headshot: p.headshot_url || getPlayerHeadshotUrl(p.player_id, p.team_abbrev ?? ''),
      to: `/players/${p.player_id}`,
    }))
    return [...teams, ...ppl]
  }, [query, players, allTeams])

  useEffect(() => { setActive(0) }, [items.length])

  const go = useCallback((to: string) => { navigate(to); close() }, [navigate, close])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); close() }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(items.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)) }
    else if (e.key === 'Enter') {
      e.preventDefault()
      const it = items[active]
      if (it) go(it.to)
    } else if (e.key === 'Tab') {
      // focus trap: only the input is focusable, so keep focus on it
      e.preventDefault()
      inputRef.current?.focus()
    }
  }

  if (!open) return null

  return (
    <div className="palette" role="presentation" onMouseDown={close}>
      <div
        className="palette__dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Search players and teams"
        ref={dialogRef}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="palette__field">
          <Search size={16} className="palette__icon" />
          <input
            ref={inputRef}
            className="palette__input"
            placeholder="Search players or teams…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <kbd className="palette__esc">Esc</kbd>
        </div>
        <div className="palette__results" role="listbox">
          {query.trim().length > 0 && items.length === 0 && (
            <div className="palette__empty">{searching ? 'Searching…' : 'No players or teams found'}</div>
          )}
          {items.map((it, i) => (
            <button
              key={`${it.kind}-${it.id}`}
              type="button"
              role="option"
              aria-selected={i === active}
              className={`palette__item ${i === active ? 'palette__item--active' : ''}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => go(it.to)}
            >
              {it.kind === 'team' ? (
                <img className="palette__thumb" src={getTeamLogoUrl(it.abbrev)} alt=""
                  onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
              ) : (
                <img className="palette__thumb palette__thumb--round" src={it.headshot} alt=""
                  onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
              )}
              <span className="palette__name">{it.name}</span>
              <span className="palette__meta">{it.kind === 'team' ? it.abbrev : it.meta}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
