/**
 * Shared page header CARD: an optional back link, the title + subtitle side-by-side, and an optional
 * controls slot (children) — page tabs, filters, a toolbar — rendered inside the SAME card, below a
 * subtle divider. Lets every tool/index page keep its title and its initial controls in one card.
 */
import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import './PageHeader.css'

export default function PageHeader({ title, subtitle, back, children }: {
  title: string
  subtitle?: ReactNode
  back?: { to: string; label: string }
  /** Page controls (tabs / filters / toolbar) rendered inside the header card, under a divider. */
  children?: ReactNode
}) {
  return (
    <header className="page-header">
      {back && <Link to={back.to} className="page-header__back">← {back.label}</Link>}
      <div className="page-header__row">
        <h1 className="page-header__title">{title}</h1>
        {subtitle && <p className="page-header__sub">{subtitle}</p>}
      </div>
      {children && <div className="page-header__controls">{children}</div>}
    </header>
  )
}
