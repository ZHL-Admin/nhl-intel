import { useState } from 'react'
import { PageLayout } from '../components/common'
import './Teams.css'

function Teams() {
  const [grouping, setGrouping] = useState<'division' | 'conference' | 'league'>('division')

  return (
    <PageLayout>
      <div className="teams">
        <div className="teams__header">
          <h1 className="teams__title">Teams</h1>
        </div>

        {/* League Landscape Placeholder */}
        <section className="teams__landscape">
          <h2 className="teams__section-title">League Landscape</h2>
          <div className="teams__landscape-placeholder">
            <p className="teams__placeholder-text">
              League landscape scatter chart (xGF/60 vs xGA/60) - data not yet available
            </p>
          </div>
        </section>

        {/* League Table */}
        <section className="teams__table">
          <div className="teams__table-header">
            <h2 className="teams__section-title">League Table</h2>
            <div className="teams__grouping-toggle">
              <button
                className={`teams__grouping-button ${grouping === 'division' ? 'teams__grouping-button--active' : ''}`}
                onClick={() => setGrouping('division')}
              >
                Division
              </button>
              <button
                className={`teams__grouping-button ${grouping === 'conference' ? 'teams__grouping-button--active' : ''}`}
                onClick={() => setGrouping('conference')}
              >
                Conference
              </button>
              <button
                className={`teams__grouping-button ${grouping === 'league' ? 'teams__grouping-button--active' : ''}`}
                onClick={() => setGrouping('league')}
              >
                League
              </button>
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
      </div>
    </PageLayout>
  )
}

export default Teams
