/**
 * StudioShell (P3) — a slim chrome strip above an existing tool page, mounted via nested routes.
 * It provides the ONE PageLayout chrome and a breadcrumb + mode tabs; the child tool page renders
 * inside via <Outlet/> and keeps its own PageCard (the strip is chrome, not a card, so the
 * one-page-one-card rule holds). Nested pages' own PageLayout collapses to a pass-through through
 * ShellContext, so no tool logic is rewritten. Mode tabs are links → deep-linkable, cmd-clickable.
 */
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { PageLayout } from '../common'
import { ShellContext } from '../common/PageLayout'
import { usePageTitle } from '../../hooks/usePageTitle'
import './StudioShell.css'

export interface ShellTab { label: string; to: string }

export default function StudioShell({ area, tabs }: { area: string; tabs: ShellTab[] }) {
  const { pathname } = useLocation()
  // Active tab = the longest `to` that prefixes the current path (so History stays active on its
  // nested dossier routes). Drives the document title for every shell'd tool page in one place.
  const active = [...tabs].sort((a, b) => b.to.length - a.to.length).find((t) => pathname.startsWith(t.to))
  usePageTitle(active ? `${active.label} · ${area}` : area)

  return (
    <PageLayout>
      <div className="studio-shell">
        <div className="studio-shell__strip">
          <div className="studio-shell__crumb">
            <Link to="/studio" className="studio-shell__crumb-root">Studio</Link>
            <span className="studio-shell__crumb-sep">/</span>
            <span className="studio-shell__crumb-area">{area}</span>
          </div>
          <nav className="studio-shell__tabs" aria-label={`${area} views`}>
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={false}
                className={({ isActive }) => `studio-shell__tab ${isActive ? 'studio-shell__tab--active' : ''}`}
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <ShellContext.Provider value={true}>
          <Outlet />
        </ShellContext.Provider>
      </div>
    </PageLayout>
  )
}
