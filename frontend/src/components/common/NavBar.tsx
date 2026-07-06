import React, { useState, useRef, useEffect, useMemo } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Search, ChevronDown } from 'lucide-react'
import ThemeToggle from './ThemeToggle'
import BrandMark from './BrandMark'
import { BRAND_NAME } from '../../config/brand'
import { inPlayoffWindow } from '../../utils/seasonal'
import { DIVISIONS, getTeamLogoUrl, getTeamName, getPlayerHeadshotUrl } from '../../utils/teams'
import { searchPlayers } from '../../api/tools'
import type { PlayerSearchResult } from '../../api/types'
import './NavBar.css'

// Studio areas (Trades, Lineups, Contracts, Draft, Offseason) → their Studio homes (P3).
const STUDIO_AREAS = [
  { to: '/studio/trades', label: 'Trades' },
  { to: '/studio/lineups', label: 'Lineups' },
  { to: '/studio/contracts', label: 'Contracts' },
  { to: '/studio/draft', label: 'Draft' },
  { to: '/studio/offseason', label: 'Offseason' },
]

function NavBar() {
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [playerResults, setPlayerResults] = useState<PlayerSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [studioOpen, setStudioOpen] = useState(false)
  const [teamsOpen, setTeamsOpen] = useState(false)
  const studioRef = useRef<HTMLDivElement>(null)
  const teamsRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const teamsCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const location = useLocation()
  const navigate = useNavigate()
  const onStudio = location.pathname.startsWith('/tools') || location.pathname.startsWith('/studio')
  const onTeams = location.pathname.startsWith('/teams')
  const showPlayoffs = inPlayoffWindow()

  // close dropdowns on outside click / route change
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (studioRef.current && !studioRef.current.contains(e.target as Node)) setStudioOpen(false)
      if (teamsRef.current && !teamsRef.current.contains(e.target as Node)) setTeamsOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])
  useEffect(() => { setStudioOpen(false); setTeamsOpen(false) }, [location.pathname])

  // Global "/" focuses search (ignore when a field already has focus); Esc blurs.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '/') return
      const el = document.activeElement as HTMLElement | null
      const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
      if (typing) return
      e.preventDefault()
      searchRef.current?.focus()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const openTeams = () => { if (teamsCloseTimer.current) clearTimeout(teamsCloseTimer.current); setTeamsOpen(true) }
  const scheduleCloseTeams = () => { teamsCloseTimer.current = setTimeout(() => setTeamsOpen(false), 160) }
  const closeMenus = () => { setStudioOpen(false); setTeamsOpen(false) }

  // player search (debounced) — teams matched client-side from the static division list
  useEffect(() => {
    const q = searchQuery.trim()
    if (q.length < 2) { setPlayerResults([]); setSearching(false); return }
    setSearching(true)
    const h = setTimeout(() => {
      searchPlayers(q, 6)
        .then((r) => { setPlayerResults(r); setSearching(false) })
        .catch(() => { setPlayerResults([]); setSearching(false) })
    }, 200)
    return () => clearTimeout(h)
  }, [searchQuery])

  const allTeams = useMemo(() => DIVISIONS.flatMap((d) => d.teams), [])
  const teamMatches = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return []
    return allTeams
      .filter((t) => getTeamName(t.abbrev).toLowerCase().includes(q) || t.abbrev.toLowerCase().includes(q))
      .slice(0, 4)
  }, [searchQuery, allTeams])

  const goTo = (to: string) => {
    navigate(to)
    setSearchQuery(''); setPlayerResults([]); setIsSearchFocused(false)
    searchRef.current?.blur()
  }

  const onSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') { setSearchQuery(''); searchRef.current?.blur() }
    if (e.key === 'Enter') {
      const to = teamMatches[0] ? `/teams/${teamMatches[0].id}`
        : playerResults[0] ? `/players/${playerResults[0].player_id}` : null
      if (to) goTo(to)
    }
  }

  const linkClass = ({ isActive }: { isActive: boolean }) => `navbar__link ${isActive ? 'navbar__link--active' : ''}`

  return (
    <nav className="navbar">
      <div className="navbar__container">
        <div className="navbar__logo">
          <NavLink to="/"><BrandMark size={20} /><span>{BRAND_NAME}</span></NavLink>
        </div>

        <div className="navbar__links">
          <NavLink to="/" end className={linkClass}>Today</NavLink>
          <NavLink to="/games" className={linkClass}>Games</NavLink>
          <NavLink to="/players" className={linkClass}>Players</NavLink>

          <div
            className={`navbar__dropdown navbar__dropdown--mega ${teamsOpen ? 'navbar__dropdown--open' : ''}`}
            ref={teamsRef} onMouseEnter={openTeams} onMouseLeave={scheduleCloseTeams}
          >
            <button type="button" className={`navbar__link navbar__dropdown-trigger ${onTeams ? 'navbar__link--active' : ''}`}
              onClick={() => setTeamsOpen((o) => !o)} aria-haspopup="true" aria-expanded={teamsOpen}>
              Teams <ChevronDown size={14} className="navbar__dropdown-chev" />
            </button>
            <div className="navbar__mega">
              {DIVISIONS.map((div) => (
                <div key={div.name} className="navbar__mega-col">
                  <span className="navbar__mega-head">{div.name}</span>
                  {div.teams.map((t) => (
                    <NavLink key={t.id} to={`/teams/${t.id}`} className="navbar__mega-team" onClick={closeMenus}>
                      <img src={getTeamLogoUrl(t.abbrev)} alt="" className="navbar__mega-logo"
                        onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
                      <span>{getTeamName(t.abbrev)}</span>
                    </NavLink>
                  ))}
                </div>
              ))}
            </div>
          </div>

          {showPlayoffs && <NavLink to="/playoffs" className={linkClass}>Playoffs</NavLink>}

          <div className={`navbar__dropdown ${studioOpen ? 'navbar__dropdown--open' : ''}`} ref={studioRef}>
            <button type="button" className={`navbar__link navbar__dropdown-trigger ${onStudio ? 'navbar__link--active' : ''}`}
              onClick={() => setStudioOpen((o) => !o)} aria-haspopup="true" aria-expanded={studioOpen}>
              Studio <ChevronDown size={14} className="navbar__dropdown-chev" />
            </button>
            <div className="navbar__dropdown-menu">
              {STUDIO_AREAS.map((a) => (
                <NavLink key={a.to} to={a.to}
                  className={({ isActive }) => `navbar__dropdown-item ${isActive ? 'navbar__dropdown-item--active' : ''}`}
                  onClick={closeMenus}>{a.label}</NavLink>
              ))}
            </div>
          </div>

          <NavLink to="/learn" className={({ isActive }) =>
            `navbar__link ${isActive || location.pathname.startsWith('/learn') ? 'navbar__link--active' : ''}`}>Learn</NavLink>
        </div>

        <div className="navbar__actions">
          <ThemeToggle />
          <div className={`navbar__search ${isSearchFocused ? 'navbar__search--focused' : ''}`}>
            <Search size={16} className="navbar__search-icon" />
            <input
              ref={searchRef} type="text" className="navbar__search-input"
              placeholder="Search players or teams"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setIsSearchFocused(true)}
              onBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
              onKeyDown={onSearchKeyDown}
            />
            {isSearchFocused && searchQuery.trim().length > 0 && (
              <div className="navbar__search-results">
                {teamMatches.length > 0 && (
                  <div className="navbar__search-group">
                    <div className="navbar__search-grouphead">Teams</div>
                    {teamMatches.map((t) => (
                      <button key={`t-${t.id}`} type="button" className="navbar__search-item"
                        onMouseDown={() => goTo(`/teams/${t.id}`)}>
                        <img className="navbar__search-thumb" src={getTeamLogoUrl(t.abbrev)} alt=""
                          onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
                        <span className="navbar__search-name">{getTeamName(t.abbrev)}</span>
                        <span className="navbar__search-meta">{t.abbrev}</span>
                      </button>
                    ))}
                  </div>
                )}
                {playerResults.length > 0 && (
                  <div className="navbar__search-group">
                    <div className="navbar__search-grouphead">Players</div>
                    {playerResults.map((p) => (
                      <button key={`p-${p.player_id}`} type="button" className="navbar__search-item"
                        onMouseDown={() => goTo(`/players/${p.player_id}`)}>
                        <img className="navbar__search-thumb navbar__search-thumb--round"
                          src={p.headshot_url || getPlayerHeadshotUrl(p.player_id, p.team_abbrev ?? '')} alt=""
                          onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
                        <span className="navbar__search-name">{p.name ?? `#${p.player_id}`}</span>
                        {/* TierBadge intentionally omitted: the search payload (PlayerSearchResult) carries no
                            tier field, and D15/no-backend-change forbids adding one here (noted in the PR). */}
                        <span className="navbar__search-meta">{[p.position, p.team_abbrev].filter(Boolean).join(' · ')}</span>
                      </button>
                    ))}
                  </div>
                )}
                {teamMatches.length === 0 && playerResults.length === 0 && (
                  <div className="navbar__search-empty">{searching ? 'Searching…' : 'No players or teams found'}</div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}

export default NavBar
