import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import BrandMark from './BrandMark'
import { BRAND_NAME, BRAND_TAGLINE } from '../../config/brand'
import { getFreshnessLabel } from '../../utils/freshness'
import './FooterMeta.css'

/** The freshness contract, rendered once by PageLayout so every page gets it. While the freshness
 *  date is loading or errored, the right side is omitted (no skeleton, no dashes). */
export default function FooterMeta() {
  const [fresh, setFresh] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    getFreshnessLabel().then((v) => active && setFresh(v)).catch(() => {})
    return () => { active = false }
  }, [])

  return (
    <footer className="footer-meta">
      <div className="footer-meta__left">
        <BrandMark size={14} />
        <span className="footer-meta__brand">{BRAND_NAME}</span>
        <span className="footer-meta__tagline">· {BRAND_TAGLINE}</span>
      </div>
      <div className="footer-meta__right">
        {fresh && <span className="footer-meta__fresh">Data through {fresh} games · updated nightly</span>}
        <span className="footer-meta__links">
          <Link to="/learn/methods">Methods</Link>
          <Link to="/learn/writing">Writing</Link>
        </span>
      </div>
    </footer>
  )
}
