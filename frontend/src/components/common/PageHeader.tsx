/**
 * The Sheet (§6.2): every page opens with this same uncarded header block —
 *   eyebrow (section name) · title (Newsreader display) · optional dek · controls row ·
 *   then a neutral 1px hairline spanning the full Well width (00c retired the red rule).
 * Component API is unchanged (title/subtitle/back/children); `eyebrow` is the one addition.
 * On route change the divider draws in left→right and the header text fades up (stilled under
 * prefers-reduced-motion).
 */
import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import './PageHeader.css'

export default function PageHeader({ eyebrow, title, subtitle, back, children }: {
  /** Section eyebrow, e.g. "Studio" — matches the live nav labels. */
  eyebrow?: string
  title: string
  subtitle?: ReactNode
  back?: { to: string; label: string }
  /** Page controls (tabs / filters / toolbar) rendered under the head, above the red rule. */
  children?: ReactNode
}) {
  return (
    <header className="sheet">
      {back && <Link to={back.to} className="sheet__back">← {back.label}</Link>}
      {eyebrow && <p className="sheet__eyebrow">{eyebrow}</p>}
      <div className="sheet__head">
        <h1 className="sheet__title">{title}</h1>
        {subtitle && <p className="sheet__dek">{subtitle}</p>}
      </div>
      {children && <div className="sheet__controls">{children}</div>}
      <div className="sheet__rule" aria-hidden="true" />
    </header>
  )
}
