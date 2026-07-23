import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import Shell from '../shell/Shell'

/** Toolkit shelf (§3.5): short list, each tool = name + one line. No hero. */
const TOOLS = [
  { to: '/tools/trade-ledger', name: 'Trade Ledger', line: 'Historical trade outcomes, graded with hindsight.' },
  { to: '/tools/draft-value', name: 'Draft Value', line: 'The pick-value curve and a value-adjusted board.' },
  { to: '/tools/lineup-lab', name: 'Lineup Lab', line: 'Project how a line of skaters fits together.' },
  { to: '/tools/contract-grader', name: 'Contract Grader', line: 'Grade a cap hit against a player’s value.' },
]

export default function Tools() {
  useEffect(() => { document.title = 'Tools · Rink Theory' }, [])
  return (
    <Shell>
      <h1 className="rt-pagetitle">Tools</h1>
      <p className="rt-intro">A small, curated shelf of interactive pieces worth keeping alive.</p>
      <ul className="rt-toolshelf">
        {TOOLS.map((t) => (
          <li key={t.to}>
            <Link to={t.to} className="rt-toolshelf__name">{t.name} <span aria-hidden>→</span></Link>
            <span className="rt-toolshelf__line">{t.line}</span>
          </li>
        ))}
      </ul>
    </Shell>
  )
}
