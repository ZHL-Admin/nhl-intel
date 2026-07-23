import type { ReactNode } from 'react'
import './figures.css'

/**
 * Base figure card (§5.3). White card, optional plot field, mono caption below
 * rendered as "FIG. N — caption". Used directly for image figures and wrapped
 * by the chart figures.
 */
export function Figure({
  n,
  caption,
  children,
  plain = false,
}: {
  n?: number
  caption?: ReactNode
  children: ReactNode
  /** plain = no gray plot field (e.g. tables, images that own their background) */
  plain?: boolean
}) {
  return (
    <figure className="rt-fig">
      {plain ? children : <div className="rt-fig__plot">{children}</div>}
      {caption && (
        <figcaption className="rt-fig__caption">
          {n != null && <b>FIG. {n} — </b>}
          {caption}
        </figcaption>
      )}
    </figure>
  )
}

/** Image figure — a static chart image + caption (§5.3 `Figure`). */
export function ImageFigure({ src, alt, n, caption }: { src: string; alt: string; n?: number; caption?: ReactNode }) {
  return (
    <Figure n={n} caption={caption} plain>
      <img className="rt-fig__img" src={src} alt={alt} />
    </Figure>
  )
}

/**
 * Pull-stat block (§6): a single big number with a mono label and a 3px orange
 * left rule. For the one number a note is really about.
 */
export function PullStat({ value, label }: { value: ReactNode; label: ReactNode }) {
  return (
    <div className="rt-pullstat">
      <div className="rt-pullstat__value">{value}</div>
      <div className="rt-pullstat__label">{label}</div>
    </div>
  )
}
