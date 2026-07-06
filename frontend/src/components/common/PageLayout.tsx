import React, { createContext, useContext } from 'react'
import NavBar from './NavBar'
import FooterMeta from './FooterMeta'
import './PageLayout.css'

/**
 * True when a page is rendered INSIDE a Studio shell (P3). The shell already supplies the one
 * NavBar + main + FooterMeta chrome, so a nested page's own PageLayout collapses to a pass-through —
 * this keeps each tool page untouched (it still returns `<PageLayout><PageCard>…`) while avoiding a
 * duplicated NavBar/footer. Default false → every non-shell page renders the full chrome as before.
 */
export const ShellContext = createContext(false)

interface PageLayoutProps {
  children: React.ReactNode
}

function PageLayout({ children }: PageLayoutProps) {
  const nested = useContext(ShellContext)
  if (nested) return <>{children}</>
  return (
    <>
      <NavBar />
      <main className="page-layout">
        <div className="page-layout__container">
          {children}
        </div>
        <FooterMeta />
      </main>
    </>
  )
}

export default PageLayout
