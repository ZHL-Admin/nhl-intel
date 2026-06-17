/**
 * Shared page header: an optional back link, then the title and subtitle side-by-side and
 * baseline-aligned (wrapping on narrow screens). Used across the index/tool pages for a
 * consistent, compact header.
 */
import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import './PageHeader.css'

export default function PageHeader({ title, subtitle, back }: {
  title: string
  subtitle?: ReactNode
  back?: { to: string; label: string }
}) {
  return (
    <header className="page-header">
      {back && <Link to={back.to} className="page-header__back">← {back.label}</Link>}
      <div className="page-header__row">
        <h1 className="page-header__title">{title}</h1>
        {subtitle && <p className="page-header__sub">{subtitle}</p>}
      </div>
    </header>
  )
}
