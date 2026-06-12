import { useState } from 'react'
import { PageLayout } from '../components/common'
import './Players.css'

function Players() {
  const [positionFilter, setPositionFilter] = useState<'all' | 'F' | 'D' | 'G'>('all')
  const [sortBy, setSortBy] = useState<'points' | 'xg' | 'cf'>('points')

  return (
    <PageLayout>
      <div className="players">
        <div className="players__header">
          <h1 className="players__title">Players</h1>
        </div>

        {/* Trending Players Strip */}
        <section className="players__trending">
          <h2 className="players__section-title">Trending This Week</h2>
          <div className="players__trending-placeholder">
            <p className="players__placeholder-text">
              Trending players carousel (hot/cold performers) - data not yet available
            </p>
          </div>
        </section>

        {/* Players Leaderboard */}
        <section className="players__leaderboard">
          <div className="players__leaderboard-header">
            <h2 className="players__section-title">Leaderboard</h2>
            <div className="players__controls">
              <div className="players__position-filter">
                <button
                  className={`players__filter-button ${positionFilter === 'all' ? 'players__filter-button--active' : ''}`}
                  onClick={() => setPositionFilter('all')}
                >
                  All
                </button>
                <button
                  className={`players__filter-button ${positionFilter === 'F' ? 'players__filter-button--active' : ''}`}
                  onClick={() => setPositionFilter('F')}
                >
                  Forwards
                </button>
                <button
                  className={`players__filter-button ${positionFilter === 'D' ? 'players__filter-button--active' : ''}`}
                  onClick={() => setPositionFilter('D')}
                >
                  Defense
                </button>
                <button
                  className={`players__filter-button ${positionFilter === 'G' ? 'players__filter-button--active' : ''}`}
                  onClick={() => setPositionFilter('G')}
                >
                  Goalies
                </button>
              </div>
              <div className="players__sort">
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as 'points' | 'xg' | 'cf')}
                  className="players__sort-select"
                >
                  <option value="points">Sort by Points</option>
                  <option value="xg">Sort by xG</option>
                  <option value="cf">Sort by CF%</option>
                </select>
              </div>
            </div>
          </div>

          <div className="players__leaderboard-placeholder">
            <p className="players__placeholder-text">
              Players leaderboard table - data not yet available
            </p>
            <p className="players__placeholder-subtext">
              Columns: Rank · Player · Team · Pos · GP · TOI/GP · G · A · P · P/60 · SOG · SH% · xG · iCF · CF% · xGF%
            </p>
          </div>
        </section>
      </div>
    </PageLayout>
  )
}

export default Players
