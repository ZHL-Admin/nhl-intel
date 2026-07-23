import { useEffect, useId, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'

export interface DropdownItem { to: string; label: string }

/**
 * Editorial nav dropdown (no nav item should lead to a page that is just more
 * navigation). The trigger opens a white panel of destination links; it is not
 * itself a link. Opens on hover and on click/keyboard; closes on Escape, outside
 * click, or item selection. Active when the current path matches `activePrefix`.
 */
export default function NavDropdown({
  label,
  items,
  activePrefix,
}: {
  label: string
  items: DropdownItem[]
  activePrefix: string
}) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const menuId = useId()
  const { pathname } = useLocation()
  const isActive = pathname === activePrefix || pathname.startsWith(activePrefix + '/')

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  // Close the panel whenever the route changes (e.g. after selecting an item).
  useEffect(() => { setOpen(false) }, [pathname])

  return (
    <div
      className="rt-navdd"
      ref={wrapRef}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className={`rt-navdd__trigger${isActive ? ' is-active' : ''}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
      >
        {label}<span className="rt-navdd__caret" aria-hidden>▾</span>
      </button>
      {open && (
        <div className="rt-navdd__panel" id={menuId} role="menu">
          {items.map((it) => (
            <NavLink key={it.to} to={it.to} role="menuitem" className="rt-navdd__item">
              {it.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}
