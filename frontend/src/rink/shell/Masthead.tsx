import RinkTheoryLogo from '../../components/common/RinkTheoryLogo'
import Nav from './Nav'

/**
 * Home masthead (§3.1). A thin top bar (date left, nav right), then the
 * full-size masthead: the kept mark (~48px) centered above the "RINK THEORY"
 * wordmark, a mono subline, and the 2px+1px ink double rule.
 */
export default function Masthead() {
  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  }).toUpperCase()

  return (
    <>
      <div className="rt-thinbar">
        <div className="rt-container rt-thinbar__inner">
          <span className="rt-mono rt-thinbar__date">{today}</span>
          <Nav />
        </div>
      </div>

      <div className="rt-container rt-masthead">
        <div className="rt-masthead__mark">
          {/* Full-size mark, its own labelled/animated control on Home. */}
          <RinkTheoryLogo size={48} withWordmark={false} interactive />
        </div>
        <h1 className="rt-masthead__title">Rink Theory</h1>
        <div className="rt-masthead__subline">An ongoing study of the NHL</div>
        <hr className="rt-masthead__rule" />
      </div>
    </>
  )
}
