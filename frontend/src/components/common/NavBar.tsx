import React, { useState, useRef, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Search, Menu, X, ChevronDown } from 'lucide-react'
import ThemeToggle from './ThemeToggle'
import { DIVISIONS, getTeamLogoUrl, getTeamName } from '../../utils/teams'
import './NavBar.css'

const TOOLS = [
  { to: '/tools/lineup-lab', label: 'Lineup Lab' },
  { to: '/tools/trade-fit', label: 'Trade Fit' },
]

function NavBar() {
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [teamsOpen, setTeamsOpen] = useState(false)
  const toolsRef = useRef<HTMLDivElement>(null)
  const teamsRef = useRef<HTMLDivElement>(null)
  const teamsCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const location = useLocation()
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
            type="text"
            className="navbar__search-input"
            placeholder="Search teams and players..."
            value={searchQuery}
            onChange={handleSearchChange}
            onFocus={() => setIsSearchFocused(true)}
            onBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
          />
          {searchQuery && (
            <div className="navbar__search-results">
              <div className="navbar__search-empty">
                Search functionality coming soon
              </div>
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
