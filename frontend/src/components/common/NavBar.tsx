import { useState, useRef, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Search, ChevronDown } from 'lucide-react'
import ThemeToggle from './ThemeToggle'
import RinkTheoryLogo from './RinkTheoryLogo'
import { PALETTE_OPEN_EVENT } from './CommandPalette'
import { BRAND_NAME } from '../../config/brand'
import { GAMES_ENABLED } from '../../config/features'
import { inPlayoffWindow } from '../../utils/seasonal'
import { DIVISIONS, getTeamLogoUrl, getTeamName } from '../../utils/teams'
import './NavBar.css'

// Studio areas (Trades, Lineups, Contracts, Draft, Offseason) → their Studio homes (P3).
const STUDIO_AREAS = [
  { to: '/studio/trades', label: 'Trades' },
  { to: '/studio/lineups', label: 'Lineups' },
  { to: '/studio/contracts', label: 'Contracts' },
  { to: '/studio/draft', label: 'Draft' },
  { to: '/studio/offseason', label: 'Offseason' },
]

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

function openPalette() { window.dispatchEvent(new CustomEvent(PALETTE_OPEN_EVENT)) }

function NavBar() {
  const [studioOpen, setStudioOpen] = useState(false)
  const [teamsOpen, setTeamsOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const studioRef = useRef<HTMLDivElement>(null)
  const teamsRef = useRef<HTMLDivElement>(null)
  const teamsCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const location = useLocation()
  const onStudio = location.pathname.startsWith('/tools') || location.pathname.startsWith('/studio')
  const onTeams = location.pathname.startsWith('/teams')
  const showPlayoffs = inPlayoffWindow()

  // Scrolled state: the bar frosts once the page moves (§6.1).
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

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

  const openTeams = () => { if (teamsCloseTimer.current) clearTimeout(teamsCloseTimer.current); setTeamsOpen(true) }
  const scheduleCloseTeams = () => { teamsCloseTimer.current = setTimeout(() => setTeamsOpen(false), 160) }
  const closeMenus = () => { setStudioOpen(false); setTeamsOpen(false) }

  const linkClass = ({ isActive }: { isActive: boolean }) => `navbar__link ${isActive ? 'navbar__link--active' : ''}`

  return (
    <nav className={`navbar ${scrolled ? 'navbar--scrolled' : ''}`}>
      <div className="navbar__container">
        <div className="navbar__logo">
          <NavLink to="/" aria-label={BRAND_NAME}>
            <RinkTheoryLogo size={32} interactive={false} />
          </NavLink>
        </div>

        <div className="navbar__links">
          <NavLink to="/" end className={linkClass}>Today</NavLink>
          {GAMES_ENABLED && <NavLink to="/games" className={linkClass}>Games</NavLink>}
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
          {/* Command-palette trigger (§6.1): slim bordered button on desktop, icon on mobile. */}
          <button type="button" className="navbar__palette" onClick={openPalette} aria-label="Search players or teams">
            <Search size={15} className="navbar__palette-icon" />
            <span className="navbar__palette-text">Search</span>
            <kbd className="navbar__palette-kbd">{isMac ? '⌘K' : 'Ctrl K'}</kbd>
          </button>
        </div>
      </div>
    </nav>
  )
}

export default NavBar
