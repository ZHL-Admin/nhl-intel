/**
 * PageCard — the ONE card every page lives in. A header (optional back link, a title + subtitle OR a
 * custom `header` node for rich identity pages, and a controls slot for tabs/filters) sits at the top,
 * separated from the body by a divider; the body holds the page's sections directly.
 *
 * One page = one card. Sections inside a PageCard must NOT carry their own card chrome (border / shadow
 * / surface background): structural sections are separated with `.page-card__divider` / `.page-divider`,
 * grouped with `.page-region-title`, and callouts use the subtle `.page-inset`. Shared card components
 * (ChartPanel, StatCard, InsightCard, IdentityHeader, …) read `PageCardContext` and auto-flatten so they
 * never become a card-on-card — page authors don't need to pass a `flat` prop at every call site.
 */
import { createContext, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import './PageCard.css'

/** True for anything rendered inside a PageCard — card components consume this to drop their chrome. */
export const PageCardContext = createContext(false)

export default function PageCard({ title, subtitle, back, header, controls, bodyClassName, children }: {
  title?: string
  subtitle?: ReactNode
  back?: { to: string; label: string }
  /** A custom header node (e.g. an IdentityHeader) used instead of the title/subtitle row. */
  header?: ReactNode
  /** Page controls (tabs / filters / toolbar) rendered in the header region, above the divider. */
  controls?: ReactNode
  /** Optional class on the body wrapper (e.g. for a grid/list layout). */
  bodyClassName?: string
  children: ReactNode
}) {
  return (
    <PageCardContext.Provider value={true}>
      <section className="page-card">
        <header className="page-card__head">
          {back && <Link to={back.to} className="page-card__back">← {back.label}</Link>}
          {header ?? (
            (title || subtitle) && (
              <div className="page-card__row">
                {title && <h1 className="page-card__title">{title}</h1>}
                {subtitle && <p className="page-card__sub">{subtitle}</p>}
              </div>
            )
          )}
          {controls && <div className="page-card__controls">{controls}</div>}
        </header>
        <div className="page-card__divider" />
        <div className={bodyClassName ? `page-card__body ${bodyClassName}` : 'page-card__body'}>
          {children}
        </div>
      </section>
    </PageCardContext.Provider>
  )
}
