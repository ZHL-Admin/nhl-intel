import React, { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Search, Menu, X } from 'lucide-react'
import './NavBar.css'

function NavBar() {
  const [isSearchFocused, setIsSearchFocused] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

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
          <NavLink
            to="/teams"
            className={({ isActive }) => `navbar__link ${isActive ? 'navbar__link--active' : ''}`}
            onClick={() => setIsMobileMenuOpen(false)}
          >
            Teams
          </NavLink>
          <NavLink
            to="/players"
            className={({ isActive }) => `navbar__link ${isActive ? 'navbar__link--active' : ''}`}
            onClick={() => setIsMobileMenuOpen(false)}
          >
            Players
          </NavLink>
        </div>

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
