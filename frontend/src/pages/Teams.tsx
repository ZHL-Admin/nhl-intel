/**
 * Teams (P2) — the single home for the standings landscape AND the team ratings that used to live on
 * the standalone Rankings page. A view switcher (URL state `?view=standings|power|deserved`, default
 * standings) sits in the PageCard controls; the power and deserved views are the old Rankings lists,
 * rendered verbatim from components/teams/RatingsViews. Standings is the original Teams body, unchanged.
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PageLayout, PageCard, Tabs } from '../components/common'
import StyleMapChart from '../components/teams/StyleMapChart'
import { PowerRatingsView, DeservedStandingsView } from '../components/teams/RatingsViews'
import { usePageTitle } from '../hooks/usePageTitle'
import './Teams.css'

type View = 'standings' | 'power' | 'deserved'
const VIEWS: View[] = ['standings', 'power', 'deserved']

function StandingsView() {
  const [grouping, setGrouping] = useState<'division' | 'conference' | 'league'>('division')
  return (
    <>
      {/* League style map (Phase 3.2) */}
      <section className="teams__landscape">
        <h2 className="teams__section-title">League landscape</h2>
        <StyleMapChart />
      </section>

      <div className="page-divider" />

      {/* League Table */}
      <section className="teams__table">
        <div className="teams__table-header">
          <h2 className="teams__section-title">League table</h2>
          <div className="teams__grouping-toggle">
            {(['division', 'conference', 'league'] as const).map((g) => (
              <button
                key={g}
                className={`teams__grouping-button ${grouping === g ? 'teams__grouping-button--active' : ''}`}
                onClick={() => setGrouping(g)}
              >
                {g[0].toUpperCase() + g.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div className="teams__table-placeholder">
          <p className="teams__placeholder-text">
            League table with all 32 teams - data not yet available
          </p>
          <p className="teams__placeholder-subtext">
            Columns: Rank · Team · GP · Record · PTS · Last 10 · GF/GP · GA/GP · CF% · xGF% · PDO
          </p>
        </div>
      </section>
    </>
  )
}

function Teams() {
  usePageTitle('Teams')
  const [searchParams, setSearchParams] = useSearchParams()
  const raw = searchParams.get('view') as View | null
  const view: View = raw && VIEWS.includes(raw) ? raw : 'standings'

  const setView = (v: string) => {
    const next = new URLSearchParams(searchParams)
    if (v === 'standings') next.delete('view')
    else next.set('view', v)
    setSearchParams(next, { replace: true })
  }

  return (
    <PageLayout>
      <div className="teams">
        <PageCard
          title="Teams"
          subtitle="Standings, strength, and luck."
          controls={
            <div className="teams__viewbar">
              <Tabs
                options={[
                  { value: 'standings', label: 'Standings' },
                  { value: 'power', label: 'Power ratings' },
                  { value: 'deserved', label: 'Deserved' },
                ]}
                value={view}
                onChange={setView}
              />
            </div>
          }
        >
          {view === 'standings' && <StandingsView />}
          {view === 'power' && <PowerRatingsView />}
          {view === 'deserved' && <DeservedStandingsView />}
        </PageCard>
      </div>
    </PageLayout>
  )
}

export default Teams
