import type { ReactNode } from 'react'
import TopBar from './TopBar'
import Footer from './Footer'

/**
 * Standard inner-page frame: compact top bar, page body, footer.
 * Home does not use this — it renders its own <Masthead/> (§3.1).
 */
export default function Shell({ children }: { children: ReactNode }) {
  return (
    <>
      <TopBar />
      <main className="rt-main">
        <div className="rt-container">{children}</div>
      </main>
      <Footer />
    </>
  )
}
