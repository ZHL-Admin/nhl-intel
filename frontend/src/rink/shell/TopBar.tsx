import { Link } from 'react-router-dom'
import RinkTheoryLogo from '../../components/common/RinkTheoryLogo'
import Nav from './Nav'

/**
 * Compact top bar for every inner page (Notes, Note, Ratings, Tools).
 * Left: the kept rt-logo mark (~26px) locked up with the wordmark, linking home.
 * Right: the site nav. 1px hairline below (via .rt-topbar).
 */
export default function TopBar() {
  return (
    <header className="rt-topbar">
      <div className="rt-container rt-topbar__inner">
        <Link to="/" className="rt-lockup" aria-label="Rink Theory — home">
          {/* interactive=false: the Link owns focus/activation; the mark only animates. */}
          <RinkTheoryLogo size={26} withWordmark interactive={false} />
        </Link>
        <Nav />
      </div>
    </header>
  )
}
