import { useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { X } from 'lucide-react'
import { REPO_URL } from '../../config/brand'
import { inPlayoffWindow } from '../../utils/seasonal'
import './MoreSheet.css'

// Mirrors the collapsed NavBar center links. Studio areas match STUDIO_AREAS in NavBar.
const STUDIO_AREAS = [
  { to: '/studio/trades', label: 'Trades' },
  { to: '/studio/lineups', label: 'Lineups' },
  { to: '/studio/contracts', label: 'Contracts' },
  { to: '/studio/draft', label: 'Draft' },
  { to: '/studio/offseason', label: 'Offseason' },
]

interface MoreSheetProps { open: boolean; onClose: () => void }

export default function MoreSheet({ open, onClose }: MoreSheetProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  const showPlayoffs = inPlayoffWindow()
  const itemClass = ({ isActive }: { isActive: boolean }) => `more-sheet__item ${isActive ? 'more-sheet__item--active' : ''}`

  return (
    <div className="more-sheet" role="dialog" aria-modal="true" aria-label="More">
      <div className="more-sheet__scrim" onClick={onClose} />
      <div className="more-sheet__panel">
        <div className="more-sheet__head">
          <span className="more-sheet__title">More</span>
          <button type="button" className="more-sheet__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="more-sheet__group">
          <span className="more-sheet__grouphead">Studio</span>
          {STUDIO_AREAS.map((a) => (
            <NavLink key={a.to} to={a.to} className={itemClass} onClick={onClose}>{a.label}</NavLink>
          ))}
        </div>

        <div className="more-sheet__group">
          {showPlayoffs && <NavLink to="/playoffs" className={itemClass} onClick={onClose}>Playoffs</NavLink>}
          <NavLink to="/learn" className={itemClass} onClick={onClose}>Learn</NavLink>
        </div>

        <div className="more-sheet__group">
          <NavLink to="/learn/methods" className={itemClass} onClick={onClose}>Methods</NavLink>
          <NavLink to="/learn/writing" className={itemClass} onClick={onClose}>Writing</NavLink>
          <a className="more-sheet__item" href={REPO_URL} target="_blank" rel="noreferrer" onClick={onClose}>GitHub</a>
        </div>
      </div>
    </div>
  )
}
