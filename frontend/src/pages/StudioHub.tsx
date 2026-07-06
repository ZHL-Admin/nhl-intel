/**
 * StudioHub (P3) — the `/studio` landing. Five area cards as .page-inset blocks (not nested cards),
 * 3-2 grid on desktop, single column on mobile. Card body click goes to the area's default route;
 * the mode links are quiet inline shortcuts. Copy is the exact §5.4 table.
 */
import { Link } from 'react-router-dom'
import { PageLayout, PageCard } from '../components/common'
import { usePageTitle } from '../hooks/usePageTitle'
import './StudioHub.css'

interface AreaCard {
  name: string
  blurb: string
  to: string
  modes?: { label: string; to: string }[]
}

const AREAS: AreaCard[] = [
  {
    name: 'Trades', blurb: 'Build a deal, find a fit, or study history’s verdicts.', to: '/studio/trades',
    modes: [
      { label: 'Build', to: '/studio/trades/build' },
      { label: 'Fit', to: '/studio/trades/fit' },
      { label: 'History', to: '/studio/trades/history' },
    ],
  },
  {
    name: 'Lineups', blurb: 'Project lines before they take a shift.', to: '/studio/lineups',
    modes: [
      { label: 'Lines', to: '/studio/lineups/lines' },
      { label: 'Roster', to: '/studio/lineups/roster' },
    ],
  },
  { name: 'Contracts', blurb: 'Grade any deal against the aging curve and the market.', to: '/studio/contracts' },
  { name: 'Draft', blurb: 'What picks are worth, measured from draft history.', to: '/studio/draft' },
  { name: 'Offseason', blurb: 'Projected WAR change for every roster, updated daily.', to: '/studio/offseason' },
]

export default function StudioHub() {
  usePageTitle('Studio')
  return (
    <PageLayout>
      <PageCard title="Studio" subtitle="The what-if suite. Every claim shows its work.">
        <div className="studio-hub__grid">
          {AREAS.map((a) => (
            <div key={a.name} className="page-inset studio-hub__card">
              <Link to={a.to} className="studio-hub__card-main">
                <span className="studio-hub__card-name">{a.name}</span>
                <span className="studio-hub__card-blurb">{a.blurb}</span>
              </Link>
              {a.modes && (
                <div className="studio-hub__modes">
                  {a.modes.map((m, i) => (
                    <span key={m.to} className="studio-hub__mode-wrap">
                      {i > 0 && <span className="studio-hub__mode-sep">·</span>}
                      <Link to={m.to} className="studio-hub__mode">{m.label}</Link>
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </PageCard>
    </PageLayout>
  )
}
