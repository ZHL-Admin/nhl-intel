/**
 * Panel (00c) — a quiet grouped-module container for side rails and secondary regions. Distinct
 * from a Tile: a Tile is one tappable object; a Panel groups a module (header, rows, footer link)
 * whose rows may each be individually interactive. Not nestable — no Panel inside a Panel or Tile.
 *
 * The optional module header renders an eyebrow (left) and a quiet blue action link (right).
 * Separate body rows with the `panel__row` class to get the hairline dividers.
 */
import { ReactNode } from 'react'
import './Panel.css'

interface PanelProps {
  /** Eyebrow label, left of the module header. */
  title?: ReactNode
  /** Quiet blue link (or node) at the right of the module header. */
  action?: ReactNode
  className?: string
  children: ReactNode
}

export default function Panel({ title, action, className, children }: PanelProps) {
  return (
    <section className={className ? `panel ${className}` : 'panel'}>
      {(title || action) && (
        <div className="panel__head">
          {title && <span className="panel__eyebrow">{title}</span>}
          {action && <span className="panel__action">{action}</span>}
        </div>
      )}
      {children}
    </section>
  )
}
