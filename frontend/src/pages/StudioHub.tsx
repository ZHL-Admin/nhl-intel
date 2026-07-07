/**
 * StudioHub (§09) — the Studio's table of contents. Not a menu of cards but a single-column
 * contents list, like the front of a journal issue: each tool is one hairline-separated row with
 * its name in Newsreader, a one-line dek, and — the signature — a Spline Sans Mono input→output
 * "contract" telling you what it computes before you click. Rows are ordered by narrative (roster
 * construction first, retrospectives last), not numbered. Learn sits in its own group below.
 */
import { Link } from 'react-router-dom'
import { PageLayout, PageCard } from '../components/common'
import { usePageTitle } from '../hooks/usePageTitle'
import './StudioHub.css'

interface ToolRow {
  name: string
  blurb: string
  to: string
  /** The input→output contract, in the machine's voice. */
  contract: string
}

const STUDIO: ToolRow[] = [
  { name: 'Lineup Lab', blurb: 'Project a line before it takes a shift.', to: '/studio/lineups/lines', contract: '5 skaters → projected xGF%' },
  { name: 'Roster Builder', blurb: 'Assemble 23 players against the cap and the curve.', to: '/studio/lineups/roster', contract: 'roster → cap fit + team WAR' },
  { name: 'Player Fit', blurb: 'Score how one player suits a given team.', to: '/studio/trades/fit', contract: 'player + team → fit score' },
  { name: 'Trade Builder', blurb: 'Weigh a deal, asset for asset.', to: '/studio/trades/build', contract: 'assets ⇄ assets → value balance' },
  { name: 'Contract Grader', blurb: 'Grade any deal against the aging curve and the market.', to: '/studio/contracts', contract: 'term + AAV → surplus vs market' },
  { name: 'Draft Value', blurb: 'What a pick is worth, measured from draft history.', to: '/studio/draft', contract: 'pick number → expected value' },
  { name: 'Offseason', blurb: 'Projected WAR change for every roster, updated daily.', to: '/studio/offseason', contract: 'roster moves → projected WAR Δ' },
  { name: 'Trade Outcomes', blurb: "Study history's verdict on past deals.", to: '/studio/trades/history', contract: 'past trade → who won' },
]

const LEARN: ToolRow[] = [
  { name: 'Archetype Explorer', blurb: 'The playing-style families, and who defines each.', to: '/learn', contract: 'archetype → player exemplars' },
]

function ToolList({ rows }: { rows: ToolRow[] }) {
  return (
    <div className="studio-hub__list">
      {rows.map((t) => (
        <Link key={t.to} to={t.to} className="studio-hub__row">
          <span className="studio-hub__row-main">
            <span className="studio-hub__row-name">{t.name}</span>
            <span className="studio-hub__row-blurb">{t.blurb}</span>
          </span>
          <span className="studio-hub__row-contract">{t.contract}</span>
        </Link>
      ))}
    </div>
  )
}

export default function StudioHub() {
  usePageTitle('Studio')
  return (
    <PageLayout>
      <PageCard eyebrow="Studio" title="Studio" subtitle="Interactive models. Same engine as the rankings.">
        <div className="studio-hub">
          <ToolList rows={STUDIO} />
          <h2 className="studio-hub__group">Learn</h2>
          <ToolList rows={LEARN} />
        </div>
      </PageCard>
    </PageLayout>
  )
}
