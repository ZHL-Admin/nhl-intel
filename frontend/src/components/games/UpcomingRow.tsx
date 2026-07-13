/**
 * UpcomingRow — row anatomy B (§01, pregame). A game tile on the Well:
 *   400px matchup | 1fr middle | 160px probability | 76px time.
 * The matchup is one logo/name/vs/logo/name line; the middle column stacks venue over season
 * series, left-anchored so every row shares one left edge; probability is the pregame split bar;
 * time is the local start. Lazy-fetches the pregame win prob and the season series.
 */
import { useEffect, useState } from 'react'
import GameLink from '../common/GameLink'
import SplitBar from './SplitBar'
import { getGamePreview, getGameContext } from '../../api/games'
import type { Game } from '../../api/types'
import { getTeamLogoUrl, getTeamName } from '../../utils/teams'
import './GameRow.css'

export default function UpcomingRow({ game: g }: { game: Game }) {
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

  // TODO(data): venue is not on the Game list payload (only getGameDetail carries venue_name).
  // Per §4 fallbacks, with venue missing we render the season series alone, vertically centered.
  const venue: string | null = null

  return (
    <GameLink to={`/games/${g.game_id}`} className="game-tile game-row--b">
      <div className="gr-matchup">
        <img className="gr-logo" src={getTeamLogoUrl(g.away_team_abbrev)} alt=""
          onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
        <span className="gr-name">{getTeamName(g.away_team_abbrev)}</span>
        <span className="gr-vs">vs</span>
        <img className="gr-logo" src={getTeamLogoUrl(g.home_team_abbrev)} alt=""
          onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
        <span className="gr-name">{getTeamName(g.home_team_abbrev)}</span>
      </div>

      <div className={`gr-mid ${venue ? '' : 'gr-mid--single'}`}>
        {venue && <span className="gr-mid__venue">{venue}</span>}
        {series && <span className="gr-mid__series">{series}</span>}
      </div>

      <div className="gr-prob">
        {homeWp != null && (
          <SplitBar homeWp={homeWp} homeAbbrev={g.home_team_abbrev} awayAbbrev={g.away_team_abbrev} />
        )}
      </div>

      <div className={`gr-time num ${g.game_time ? '' : 'gr-time--tbd'}`}>
        {g.game_time || 'TBD'}
      </div>
    </GameLink>
  )
}
