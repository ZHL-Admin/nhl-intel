import { Link } from 'react-router-dom'

/**
 * Site footer (§3.1): hairline, "RINK THEORY © YEAR" left, RSS · ARCHIVE right.
 */
export default function Footer() {
  const year = new Date().getFullYear()
  return (
    <footer className="rt-footer">
      <div className="rt-container rt-footer__inner">
        <span>Rink Theory © {year}</span>
        <span>
          <a href="/rss.xml">RSS</a>
          {' · '}
          <Link to="/notes">Archive</Link>
        </span>
      </div>
    </footer>
  )
}
