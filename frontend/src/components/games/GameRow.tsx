/**
 * GameRow — row anatomy A (§01, live + final). A game tile on the Well:
 *   280px teams | 48px score | 100px status | 1fr worm | 128px right.
 * Teams are two logo+name lines (leader inked); scores are two right-aligned tabular lines;
 * status is a mono period/clock or FINAL; the worm spans its full column; the right column
 * carries the live win-probability split bar, or a quiet "Recap" affordance once final.
 * Each tile lazy-fetches its own worm series, and live tiles also fetch the live win prob.
 */
import { useEffect, useState } from 'react'
import GameLink from '../common/GameLink'
import MiniWorm from '../common/MiniWorm'
import SplitBar from './SplitBar'
import { getGameXGWorm, getGameWinProb } from '../../api/games'
import type { Game, XGWormPoint } from '../../api/types'
import { getTeamLogoUrl, getTeamColor, getTeamName } from '../../utils/teams'
import './GameRow.css'

function TeamLine({ abbrev, leader }: { abbrev: string; leader: boolean }) {
  return (
    <div className={`gr-team ${leader ? 'gr-team--leader' : ''}`}>
      <img className="gr-logo" src={getTeamLogoUrl(abbrev)} alt=""
        onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
      <span className="gr-name">{getTeamName(abbrev)}</span>
      {/* TODO(data): team overall record ("26-12-4") — needs a standings source keyed by
          team; not present on the Game list payload. Render nothing until wired. */}
    </div>
  )
}

export default function GameRow({ game: g }: { game: Game }) {
  const isLive = !!g.is_live
  const [worm, setWorm] = useState<XGWormPoint[] | null>(null)
  const [homeWp, setHomeWp] = useState<number | null>(null)

  useEffect(() => {
    let active = true
    getGameXGWorm(g.game_id).then((w) => active && setWorm(w)).catch(() => active && setWorm([]))
    return () => { active = false }
  }, [g.game_id])

  useEffect(() => {
    if (!isLive) return
    let active = true
    getGameWinProb(g.game_id)
      .then((s) => {
        if (!active) return
        const last = s.series[s.series.length - 1]
        setHomeWp(last ? last.home_wp : null)
      })
      // If live win prob isn't served, the split bar is dropped and status shows alone.
      // TODO(backend): serve a live win-probability feed for in-progress games.
      .catch(() => active && setHomeWp(null))
    return () => { active = false }
  }, [g.game_id, isLive])

  const wormData = worm?.map((p) => ({ time: p.game_time_seconds, diff: p.cumulative_xg_diff })) ?? []

  const away = g.away_score ?? 0
  const home = g.home_score ?? 0
  const awayLeads = away > home
  const homeLeads = home > away
  const tied = away === home
  // Only the leader/winner is inked; ties (incl. live ties) leave both scores secondary.

  const wormColor = tied
    ? 'var(--color-data-neutral)'
    : getTeamColor(awayLeads ? g.away_team_abbrev : g.home_team_abbrev)

  const statusText = isLive
    ? `${(g.period ?? 'LIVE').toUpperCase()}${g.time_remaining ? ` · ${g.time_remaining}` : ''}`
    // TODO(data): OT/SO suffix ("FINAL · OT") — not present on the Game list payload.
    : 'FINAL'

  return (
    <GameLink to={`/games/${g.game_id}`} className="game-tile game-row--a">
      <div className="gr-teams">
        <TeamLine abbrev={g.away_team_abbrev} leader={awayLeads} />
        <TeamLine abbrev={g.home_team_abbrev} leader={homeLeads} />
      </div>

      <div className="gr-scores">
        <span className={`gr-score num ${awayLeads ? 'gr-score--leader' : ''}`}>{away}</span>
        <span className={`gr-score num ${homeLeads ? 'gr-score--leader' : ''}`}>{home}</span>
      </div>

      <div className="gr-status">{statusText}</div>

      <div className="gr-worm" aria-hidden="true">
        {wormData.length > 1 && (
          <MiniWorm data={wormData} width={220} height={28} color={wormColor} midline />
        )}
      </div>

      <div className="gr-right">
        {isLive ? (
          homeWp != null && (
            <SplitBar homeWp={homeWp} homeAbbrev={g.home_team_abbrev} awayAbbrev={g.away_team_abbrev} />
          )
        ) : (
          <span className="gr-recap">Recap →</span>
        )}
      </div>
    </GameLink>
  )
}
