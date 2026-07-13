import React, { createContext, useContext } from 'react'
import NavBar from './NavBar'
import CommandPalette from './CommandPalette'
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
      <CommandPalette />
      <main className="page-layout">
        {/* The Well (00b): one white sheet on the ice, wrapping the whole page body incl. the
            Sheet header. The footer sits on the canvas below it, container width. */}
        <div className="page-layout__well">
          {children}
        </div>
        <FooterMeta />
      </main>
    </>
  )
}

export default PageLayout
