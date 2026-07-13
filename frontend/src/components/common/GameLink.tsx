/**
 * GameLink — the single wrapper for any anchor that navigates into a game page. When GAMES_ENABLED
 * is true it is a normal router <Link>; when false it renders the SAME content as an inert element
 * (no anchor, no navigation, no hover affordance, cursor default) so scores/schedules still read as
 * plain content. Keying every game link off this keeps re-enabling a one-line flag flip.
 */
import { ReactNode, HTMLAttributes } from 'react'
import { Link } from 'react-router-dom'
import { GAMES_ENABLED } from '../../config/features'

/**
 * Props for an element (button / table row) that navigates into a game via an onClick handler
 * (rather than an anchor). When games are disabled the handler is dropped and the element goes
 * inert (pointer-events:none removes hover + click + cursor; tabIndex −1 removes keyboard focus),
 * so the surrounding score/schedule content still reads as plain content.
 */
export function gameButtonProps(onNavigate: () => void): HTMLAttributes<HTMLElement> {
  if (GAMES_ENABLED) return { onClick: onNavigate }
  return { onClick: undefined, tabIndex: -1, style: { pointerEvents: 'none' } }
}

interface GameLinkProps {
  to: string
  className?: string
  children: ReactNode
  'aria-label'?: string
}

export default function GameLink({ to, className, children, ...rest }: GameLinkProps) {
  if (GAMES_ENABLED) {
    return <Link to={to} className={className} {...rest}>{children}</Link>
  }
  // Inert: same layout via the same className; pointer-events:none removes hover + click + the
  // pointer cursor, so the tile reads as plain content.
  return <div className={className} style={{ pointerEvents: 'none' }} {...rest}>{children}</div>
}
