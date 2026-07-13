/**
 * ContextStrip (00c) — a slim single-line Sheet variant for utility mastheads where a large
 * display title wastes space (currently: Home). Primary context sits left in ink, secondary
 * context right in muted, baseline-aligned, closed by a neutral hairline at the Well width.
 * Pages that want the full masthead keep the standard Sheet / PageHeader instead.
 */
import { ReactNode } from 'react'
import './ContextStrip.css'

export default function ContextStrip({ primary, secondary }: {
  primary: ReactNode
  secondary?: ReactNode
}) {
  return (
    <div className="context-strip">
      <span className="context-strip__primary">{primary}</span>
      {secondary && <span className="context-strip__secondary">{secondary}</span>}
    </div>
  )
}
