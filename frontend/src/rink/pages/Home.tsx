import { useEffect } from 'react'
import Masthead from '../shell/Masthead'
import Footer from '../shell/Footer'

/**
 * Home (§3.1). Step 2 ships the real masthead + footer chrome; the lead note,
 * recent-notes feed, and right rail (ratings snapshot, luck watch, toolkit) are
 * assembled in Step 6 from the finished Notes and Ratings parts.
 */
export default function Home() {
  useEffect(() => { document.title = 'Rink Theory' }, [])
  return (
    <>
      <Masthead />
      <main className="rt-main">
        <div className="rt-container">
          <div className="rt-placeholder">
            <strong>Home body.</strong> Lead note, <code>RECENT NOTES</code> feed,
            and the right rail (<code>POWER RATINGS</code>, <code>LUCK WATCH</code>,
            <code> FROM THE TOOLKIT</code>) are assembled in <code>Step 6</code> once
            Notes and Ratings exist.
          </div>
        </div>
      </main>
      <Footer />
    </>
  )
}
