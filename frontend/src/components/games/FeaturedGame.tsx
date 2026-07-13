/**
 * FeaturedGame (§01, sparse slate) — the full-width featured tile for an upcoming game on a
 * 1-3 game night. Left: a large matchup line (logo, full name, mono vs, logo, name) over a
 * muted context line (venue + season series, with the series-only fallback when venue is
 * missing). Right: start time, the pregame split bar, and a quiet "Pregame notes" affordance.
 */
import { useEffect, useState } from 'react'
import GameLink from '../common/GameLink'
import SplitBar from './SplitBar'
import { getGamePreview, getGameContext } from '../../api/games'
import type { Game } from '../../api/types'
import { getTeamLogoUrl, getTeamName } from '../../utils/teams'
import './GameRow.css'

export default function FeaturedGame({ game: g }: { game: Game }) {
  const [homeWp, setHomeWp] = useState<number | null>(null)
  const [series, setSeries] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getGamePreview(g.game_id)
      .then((p) => { if (active) setHomeWp(p.home_pregame_wp ?? null) })
      .catch(() => { if (active) setHomeWp(null) })
    getGameContext(g.game_id)
      .then((c) => {
        if (!active || !c) return
        const a = c.season_series_away_wins
        const h = c.season_series_home_wins
        if (a == null || h == null) return
        const leader = a === h ? '' : ` · ${a > h ? g.away_team_abbrev : g.home_team_abbrev}`
        setSeries(`Season series ${a}-${h}${leader}`)
      })
      .catch(() => {})
    return () => { active = false }
  }, [g.game_id, g.away_team_abbrev, g.home_team_abbrev])

  // TODO(data): venue and playoff-series context are not on the Game list payload; with venue
  // missing the context line falls back to the season series alone (§5).
  const context = series

  return (
    <GameLink to={`/games/${g.game_id}`} className="game-tile featured-game">
      <div className="featured__left">
        <div className="featured__matchup">
          <img className="gr-logo" src={getTeamLogoUrl(g.away_team_abbrev)} alt=""
            onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
          <span>{getTeamName(g.away_team_abbrev)}</span>
          <span className="gr-vs">vs</span>
          <img className="gr-logo" src={getTeamLogoUrl(g.home_team_abbrev)} alt=""
            onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
          <span>{getTeamName(g.home_team_abbrev)}</span>
        </div>
        {context && <p className="featured__context">{context}</p>}
      </div>

      <div className="featured__right">
        <span className={`featured__time num ${g.game_time ? '' : 'featured__time--tbd'}`}>
          {g.game_time || 'Time TBD'}
        </span>
        {homeWp != null && (
          <SplitBar homeWp={homeWp} homeAbbrev={g.home_team_abbrev} awayAbbrev={g.away_team_abbrev} />
        )}
        <span className="featured__notes">Pregame notes →</span>
      </div>
    </GameLink>
  )
}
