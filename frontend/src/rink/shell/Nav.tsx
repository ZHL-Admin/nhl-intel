import { NavLink } from 'react-router-dom'

/**
 * Site nav — the routing rule made visible: NOTES · RATINGS · TOOLS.
 * Per plan §2 there is no Search in v1 (the mockups show one; the plan of
 * record overrides). Every page carries this nav.
 */
export default function Nav() {
  const cls = ({ isActive }: { isActive: boolean }) => (isActive ? 'is-active' : undefined)
  return (
    <nav className="rt-nav" aria-label="Primary">
      <NavLink to="/notes" className={cls}>Notes</NavLink>
      <NavLink to="/ratings" className={cls}>Ratings</NavLink>
      {/* Tools is active for /tools and every /tools/* tool route. */}
      <NavLink to="/tools" className={cls}>Tools</NavLink>
    </nav>
  )
}
