/**
 * Teams (P2) — the single home for the standings landscape AND the team ratings that used to live on
 * the standalone Rankings page. A view switcher (URL state `?view=standings|power|deserved`, default
 * standings) sits in the PageCard controls; the power and deserved views are the old Rankings lists,
 * rendered verbatim from components/teams/RatingsViews. Standings is the original Teams body, unchanged.
 */
import { useSearchParams } from 'react-router-dom'
import { PageLayout, PageCard, Tabs } from '../components/common'
import StyleMapChart from '../components/teams/StyleMapChart'
import DivisionStandings from '../components/teams/DivisionStandings'
import { PowerRatingsView, DeservedStandingsView } from '../components/teams/RatingsViews'
import { usePageTitle } from '../hooks/usePageTitle'
import './Teams.css'

type View = 'standings' | 'power' | 'deserved'
const VIEWS: View[] = ['standings', 'power', 'deserved']

function StandingsView() {
  return (
    <>
      {/* League style map (Phase 3.2) */}
      <section className="teams__landscape">
        <h2 className="teams__section-title">League landscape</h2>
        <StyleMapChart />
      </section>

      <div className="page-divider" />

      {/* Division standings (Blueprint 2.6) — by division, against the playoff cut. */}
      <section className="teams__table">
        <h2 className="teams__section-title">Standings, by division</h2>
        <DivisionStandings />
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
