import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { CalendarDays, Home, Users, Shield, Menu } from 'lucide-react'
import MoreSheet from './MoreSheet'
import { GAMES_ENABLED } from '../../config/features'
import './BottomTabBar.css'

// D18 mobile tabs. The first four are direct destinations; "More" opens a sheet with everything
// the collapsed NavBar center links would otherwise hold (Studio areas, Learn, seasonal Playoffs).
// Games is gated behind GAMES_ENABLED; the flex tabbar redistributes evenly with it removed.
const TABS = [
  { to: '/', label: 'Today', icon: Home, end: true },
  ...(GAMES_ENABLED ? [{ to: '/games', label: 'Games', icon: CalendarDays }] : []),
  { to: '/players', label: 'Players', icon: Users },
  { to: '/teams', label: 'Teams', icon: Shield },
]

export default function BottomTabBar() {
  const [moreOpen, setMoreOpen] = useState(false)
  return (
    <>
      <nav className="tabbar" aria-label="Primary">
        {TABS.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end}
            className={({ isActive }) => `tabbar__tab ${isActive ? 'tabbar__tab--active' : ''}`}>
            <Icon size={20} strokeWidth={2} />
            <span>{label}</span>
          </NavLink>
        ))}
        <button type="button" className={`tabbar__tab ${moreOpen ? 'tabbar__tab--active' : ''}`}
          onClick={() => setMoreOpen(true)} aria-haspopup="dialog" aria-expanded={moreOpen}>
          <Menu size={20} strokeWidth={2} />
          <span>More</span>
        </button>
      </nav>
      <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} />
    </>
  )
}
