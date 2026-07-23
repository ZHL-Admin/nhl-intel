import { useEffect } from 'react'
import Masthead from '../shell/Masthead'
import Footer from '../shell/Footer'
import Rail from '../home/Rail'
import '../home/rail.css'

/**
 * Home (§3.1). The right rail (ratings snapshot, luck watch, toolkit) is live as
 * of Step 4. The left column — lead note + RECENT NOTES feed — is assembled in
 * Step 6 once notes publish; it stays a placeholder until then.
 */
export default function Home() {
  useEffect(() => { document.title = 'Rink Theory' }, [])
  return (
    <>
      <Masthead />
      <main className="rt-main">
        <div className="rt-container rt-home">
          <div>
            <div className="rt-placeholder">
              <strong>Lead note + RECENT NOTES feed</strong> are assembled in <code>Step 6</code>,
              once notes publish. The right rail is live.
            </div>
          </div>
          <Rail />
        </div>
      </main>
      <Footer />
    </>
  )
}
