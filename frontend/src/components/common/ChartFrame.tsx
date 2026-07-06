/**
 * ChartFrame (DS1) — the mandatory chart anatomy (§5.1): optional overline kicker, a sentence-case
 * title, a one-sentence dek (required — if you can't write it, the chart isn't ready), the plot, and
 * an optional mono source line ("Data through Jul 2 · method"). The plot region is role="img" with
 * an aria-label mirroring the dek (§5.3). No border/box — charts sit on the surface or in a
 * .page-inset (§5.2).
 */
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { fmt } from '../../utils/format'
import './ChartFrame.css'

interface ChartFrameProps {
  /** Optional mono uppercase overline kicker. */
  kicker?: string
  /** Sentence-case title — the finding when there is one, else the subject. */
  title: string
  /** One plain sentence of what you're looking at. Mandatory. */
  dek: string
  /** Source line pieces. Omit to hide the line. */
  source?: { date?: string | Date | null; methodHref?: string; methodLabel?: string }
  children: ReactNode
  className?: string
}

export default function ChartFrame({ kicker, title, dek, source, children, className }: ChartFrameProps) {
  const dateLabel = source?.date != null ? fmt.date(source.date) : null
  const hasSource = source && (dateLabel || source.methodHref || source.methodLabel)
  return (
    <figure className={`chart-frame${className ? ` ${className}` : ''}`}>
      {kicker && <span className="chart-frame__kicker">{kicker}</span>}
      <figcaption className="chart-frame__head">
        <h3 className="chart-frame__title">{title}</h3>
        <p className="chart-frame__dek">{dek}</p>
      </figcaption>
      <div className="chart-frame__plot" role="img" aria-label={dek}>
        {children}
      </div>
      {hasSource && (
        <div className="chart-frame__source">
          {dateLabel && <span>Data through {dateLabel}</span>}
          {dateLabel && (source.methodHref || source.methodLabel) && <span aria-hidden> · </span>}
          {source.methodHref
            ? <Link className="chart-frame__method" to={source.methodHref}>{source.methodLabel ?? 'method'}</Link>
            : source.methodLabel && <span className="chart-frame__method">{source.methodLabel}</span>}
        </div>
      )}
    </figure>
  )
}
