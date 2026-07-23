import { NavLink } from 'react-router-dom'
import NavDropdown from './NavDropdown'

/**
 * Site nav (§2, amended). NOTES is a plain link; RATINGS and TOOLS are
 * dropdowns so no nav item leads to a page that is just more navigation.
 * No Search in v1 (plan of record overrides the mockups). /tools stays
 * reachable by URL as a plain index, but the nav skips it.
 */
const RATINGS_ITEMS = [
  { to: '/ratings', label: 'Teams' },
  { to: '/ratings/players', label: 'Players' },
]

const TOOLS_ITEMS = [
  { to: '/tools/trade-ledger', label: 'Trade Ledger' },
  { to: '/tools/draft-value', label: 'Draft Value' },
  { to: '/tools/lineup-lab', label: 'Lineup Lab' },
  { to: '/tools/contract-grader', label: 'Contract Grader' },
]

export default function Nav() {
  return (
    <nav className="rt-nav" aria-label="Primary">
      <NavLink to="/notes" className={({ isActive }) => (isActive ? 'is-active' : undefined)}>
        Notes
      </NavLink>
      <NavDropdown label="Ratings" items={RATINGS_ITEMS} activePrefix="/ratings" />
      <NavDropdown label="Tools" items={TOOLS_ITEMS} activePrefix="/tools" />
    </nav>
  )
}
