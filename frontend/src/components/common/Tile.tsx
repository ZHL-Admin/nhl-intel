/**
 * Tile (00b) — the tappable navigation object. For game rows, matchup features, and short link
 * lists: a single elevated surface where the whole tile is the link. Lives directly on the Well,
 * one level deep, maximum — no tile inside a tile, no card chrome inside a tile. Lists longer than
 * ~10 items and all data tables stay hairline Gamesheets, not tile stacks.
 *
 * Renders as a router <Link> (`to`), an anchor (`href`), or a <button> (`onClick`) — whichever
 * prop is supplied — so it is always a real, keyboard-focusable interactive element.
 */
import { ReactNode, MouseEventHandler } from 'react'
import { Link } from 'react-router-dom'
import './Tile.css'

interface TileProps {
  to?: string
  href?: string
  onClick?: MouseEventHandler
  className?: string
  children: ReactNode
  'aria-label'?: string
}

export default function Tile({ to, href, onClick, className, children, ...rest }: TileProps) {
  const cls = className ? `tile ${className}` : 'tile'
  if (to) return <Link to={to} className={cls} onClick={onClick} {...rest}>{children}</Link>
  if (href) return <a href={href} className={cls} onClick={onClick} {...rest}>{children}</a>
  return <button type="button" className={cls} onClick={onClick} {...rest}>{children}</button>
}
