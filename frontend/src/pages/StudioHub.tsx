/**
 * StudioHub (P3 + Blueprint 2.9/D32) — the `/studio` landing. Five area cards as .page-inset blocks;
 * the player-based areas carry an inline EntityPicker launcher ("Grade a contract for…") so the hub
 * is a launcher, not a menu — picking routes into the tool prefilled.
 */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { PageLayout, PageCard, EntityPicker } from '../components/common'
import { usePageTitle } from '../hooks/usePageTitle'
import type { PlayerSearchResult } from '../api/types'
import './StudioHub.css'

interface AreaCard {
  name: string
  blurb: string
  to: string
  modes?: { label: string; to: string }[]
  /** Inline launcher: prompt + the route to open, prefilled with the picked player. */
  pick?: { prompt: string; route: (id: number) => string }
}

const AREAS: AreaCard[] = [
  {
    name: 'Trades', blurb: 'Build a deal, find a fit, or study history’s verdicts.', to: '/studio/trades',
    modes: [
      { label: 'Build Trade', to: '/studio/trades/build' },
      { label: 'Player Fit', to: '/studio/trades/fit' },
      { label: 'Trade History', to: '/studio/trades/history' },
    ],
    pick: { prompt: 'Find a fit for…', route: (id) => `/studio/trades/fit?player=${id}` },
  },
  {
    name: 'Lineups', blurb: 'Project lines before they take a shift.', to: '/studio/lineups',
    modes: [
      { label: 'Line Builder', to: '/studio/lineups/lines' },
      { label: 'Team Builder', to: '/studio/lineups/roster' },
    ],
    pick: { prompt: 'Add a player to a line…', route: (id) => `/studio/lineups/lines?add=${id}` },
  },
  {
    name: 'Contracts', blurb: 'Grade any deal against the aging curve and the market.', to: '/studio/contracts',
    pick: { prompt: 'Grade a contract for…', route: (id) => `/studio/contracts?player=${id}` },
  },
  { name: 'Draft', blurb: 'What picks are worth, measured from draft history.', to: '/studio/draft' },
  { name: 'Offseason', blurb: 'Projected WAR change for every roster, updated daily.', to: '/studio/offseason' },
]

export default function StudioHub() {
  usePageTitle('Studio')
  const navigate = useNavigate()
  const [picking, setPicking] = useState<AreaCard | null>(null)

  const onSelect = (p: PlayerSearchResult) => {
    if (picking?.pick) navigate(picking.pick.route(p.player_id))
    setPicking(null)
  }

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
              {a.pick && (
                <button type="button" className="studio-hub__launcher" onClick={() => setPicking(a)}>
                  <Search size={14} /> {a.pick.prompt}
                </button>
              )}
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
      <EntityPicker open={picking !== null} onClose={() => setPicking(null)} onSelect={onSelect} title={picking?.pick?.prompt ?? 'Search players'} />
    </PageLayout>
  )
}
