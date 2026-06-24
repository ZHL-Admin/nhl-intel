import React, { useState, useRef, useEffect, useMemo } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Search, Menu, X, ChevronDown } from 'lucide-react'
import ThemeToggle from './ThemeToggle'
import { DIVISIONS, getTeamLogoUrl, getTeamName, getPlayerHeadshotUrl } from '../../utils/teams'
import { searchPlayers } from '../../api/tools'
import type { PlayerSearchResult } from '../../api/types'
import './NavBar.css'

const TOOLS = [
  { to: '/tools/lineup-lab', label: 'Lineup Lab' },
  { to: '/tools/trade-fit', label: 'Player Fit' },
  { to: '/tools/trade-builder', label: 'Trade Builder' },
  { to: '/tools/contract-grader', label: 'Contract Grader' },
  { to: '/learn/archetypes', label: 'Player Archetypes' },
]

function NavBar() {
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [playerResults, setPlayerResults] = useState<PlayerSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [teamsOpen, setTeamsOpen] = useState(false)
  const toolsRef = useRef<HTMLDivElement>(null)
  const teamsRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const teamsCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const location = useLocation()
  const navigate = useNavigate()
  const onTools = location.pathname.startsWith('/tools')
  const onTeams = location.pathname.startsWith('/teams')

  // close dropdowns on outside click
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (toolsRef.current && !toolsRef.current.contains(e.target as Node)) setToolsOpen(false)
      if (teamsRef.current && !teamsRef.current.contains(e.target as Node)) setTeamsOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])
  useEffect(() => { setToolsOpen(false); setTeamsOpen(false) }, [location.pathname])

  // hover-with-delay for the wide Teams mega-menu (so the gap doesn't drop it)
  const openTeams = () => { if (teamsCloseTimer.current) clearTimeout(teamsCloseTimer.current); setTeamsOpen(true) }
  const scheduleCloseTeams = () => { teamsCloseTimer.current = setTimeout(() => setTeamsOpen(false), 160) }

  const closeMenus = () => { setIsMobileMenuOpen(false); setToolsOpen(false); setTeamsOpen(false) }

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value)
  }

  // player search (debounced) — teams are matched client-side from the static division list
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

  return (
    <nav className="navbar">
      <div className="navbar__container">
        <div className="navbar__logo">
          <NavLink to="/">NHL Intel</NavLink>
        </div>

        <div className={`navbar__links ${isMobileMenuOpen ? 'navbar__links--open' : ''}`}>
          <NavLink
            to="/"
            className={({ isActive }) => `navbar__link ${isActive ? 'navbar__link--active' : ''}`}
            onClick={() => setIsMobileMenuOpen(false)}
          >
            Games
          </NavLink>
          <div
            className={`navbar__dropdown navbar__dropdown--mega ${teamsOpen ? 'navbar__dropdown--open' : ''}`}
            ref={teamsRef}
            onMouseEnter={openTeams}
            onMouseLeave={scheduleCloseTeams}
          >
            <button
              type="button"
              className={`navbar__link navbar__dropdown-trigger ${onTeams ? 'navbar__link--active' : ''}`}
              onClick={() => setTeamsOpen((o) => !o)}
              aria-haspopup="true"
              aria-expanded={teamsOpen}
            >
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
          <NavLink
            to="/rankings"
            className={({ isActive }) => `navbar__link ${isActive ? 'navbar__link--active' : ''}`}
            onClick={() => setIsMobileMenuOpen(false)}
          >
            Rankings
          </NavLink>
          <NavLink
            to="/players"
            className={({ isActive }) => `navbar__link ${isActive ? 'navbar__link--active' : ''}`}
            onClick={() => setIsMobileMenuOpen(false)}
          >
            Players
          </NavLink>
          <NavLink
            to="/playoffs"
            className={({ isActive }) => `navbar__link ${isActive ? 'navbar__link--active' : ''}`}
            onClick={() => setIsMobileMenuOpen(false)}
          >
            Playoffs
          </NavLink>
          <div
            className={`navbar__dropdown ${toolsOpen ? 'navbar__dropdown--open' : ''}`}
            ref={toolsRef}
          >
            <button
              type="button"
              className={`navbar__link navbar__dropdown-trigger ${onTools ? 'navbar__link--active' : ''}`}
              onClick={() => setToolsOpen((o) => !o)}
              aria-haspopup="true"
              aria-expanded={toolsOpen}
            >
              Tools <ChevronDown size={14} className="navbar__dropdown-chev" />
            </button>
            <div className="navbar__dropdown-menu">
              {TOOLS.map((t) => (
                <NavLink
                  key={t.to}
                  to={t.to}
                  className={({ isActive }) => `navbar__dropdown-item ${isActive ? 'navbar__dropdown-item--active' : ''}`}
                  onClick={closeMenus}
                >
                  {t.label}
                </NavLink>
              ))}
            </div>
          </div>
        </div>

        <div className="navbar__actions">
          <ThemeToggle />
          <div className={`navbar__search ${isSearchFocused ? 'navbar__search--focused' : ''}`}>
          <Search size={16} className="navbar__search-icon" />
          <input
            ref={searchRef}
            type="text"
            className="navbar__search-input"
            placeholder="Search teams and players..."
            value={searchQuery}
            onChange={handleSearchChange}
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
                      <span className="navbar__search-meta">{[p.position, p.team_abbrev].filter(Boolean).join(' · ')}</span>
                    </button>
                  ))}
                </div>
              )}
              {teamMatches.length === 0 && playerResults.length === 0 && (
                <div className="navbar__search-empty">{searching ? 'Searching…' : 'No teams or players found'}</div>
              )}
            </div>
          )}
          </div>
        </div>

        <button
          className="navbar__mobile-toggle"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label="Toggle menu"
        >
          {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>
    </nav>
  )
}

export default NavBar
