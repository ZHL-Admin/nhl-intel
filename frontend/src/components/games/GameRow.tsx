/**
 * GameRow (§01) — a 64px scoreboard row. Away and home stacked as two lines (logo + name), a
 * tabular score column with the leader inked and the trailer greyed, a status column (LIVE
 * dot-chip / Final / start time in mono), the xG-differential MiniWorm at 160x36, and the
 * possession share as a small tabular percent. The whole row links to the game; hover is the
 * crease wash. Each scored row lazy-fetches its own worm series.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import MiniWorm from '../common/MiniWorm'
import { getGameXGWorm } from '../../api/games'
import type { Game, XGWormPoint } from '../../api/types'
import { getTeamLogoUrl, getTeamColor, getTeamName } from '../../utils/teams'
import './GameRow.css'

function TeamLine({ abbrev, score, leader, showScore }: {
  abbrev: string; score: number | null; leader: boolean; showScore: boolean
}) {
  return (
    <div className={`game-row__team ${leader ? 'game-row__team--leader' : ''}`}>
      <img className="game-row__logo" src={getTeamLogoUrl(abbrev)} alt=""
        onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
      <span className="game-row__name">{getTeamName(abbrev)}</span>
      {showScore && <span className="game-row__score num">{score ?? 0}</span>}
    </div>
  )
}

export default function GameRow({ game: g }: { game: Game }) {
  const scored = g.is_live || !g.is_preview
  const [worm, setWorm] = useState<XGWormPoint[] | null>(null)

  useEffect(() => {
    if (!scored) return
    let active = true
    getGameXGWorm(g.game_id).then((w) => active && setWorm(w)).catch(() => active && setWorm([]))
    return () => { active = false }
  }, [g.game_id, scored])

  const wormData = worm?.map((p) => ({ time: p.game_time_seconds, diff: p.cumulative_xg_diff })) ?? []

  // Leader (for score inking + worm color): the higher score once scored.
  const awayLeads = scored && (g.away_score ?? 0) > (g.home_score ?? 0)
  const homeLeads = scored && (g.home_score ?? 0) > (g.away_score ?? 0)
  const leaderColor = getTeamColor(awayLeads ? g.away_team_abbrev : g.home_team_abbrev)

  // Possession share (proxy for the "percent" column); label the favored side.
  const homeShare = g.home_cf_pct != null && g.away_cf_pct != null
    ? (g.home_cf_pct / (g.home_cf_pct + g.away_cf_pct)) * 100 : null
  const favShare = homeShare != null ? Math.max(homeShare, 100 - homeShare) : null
  const favAbbrev = homeShare != null ? (homeShare >= 50 ? g.home_team_abbrev : g.away_team_abbrev) : null

  return (
    <Link to={`/games/${g.game_id}`} className={`game-row ${g.is_live ? 'game-row--live' : ''}`}>
      <div className="game-row__teams">
        <TeamLine abbrev={g.away_team_abbrev} score={g.away_score} leader={awayLeads} showScore={scored} />
        <TeamLine abbrev={g.home_team_abbrev} score={g.home_score} leader={homeLeads} showScore={scored} />
      </div>

      <div className="game-row__status">
        {g.is_live ? (
          <span className="game-row__live">
            <span className="live-dot" />
            <span className="game-row__live-text">
              {g.period ?? 'LIVE'}{g.time_remaining ? ` · ${g.time_remaining}` : ''}
            </span>
          </span>
        ) : g.is_preview ? (
          <span className="game-row__time">{g.game_time || 'TBD'}</span>
        ) : (
          <span className="game-row__final">Final</span>
        )}
      </div>

      <div className="game-row__worm" aria-hidden>
        {scored && wormData.length > 1 ? (
          <MiniWorm data={wormData} width={160} height={36} color={leaderColor} midline />
        ) : homeShare != null ? (
          <span className="game-row__lean-track">
            <span className="game-row__lean-fill"
              style={{ width: `${homeShare}%`, background: getTeamColor(g.home_team_abbrev) }} />
          </span>
        ) : null}
      </div>

      <div className="game-row__pct">
        {favShare != null && (
          <>
            <span className="game-row__pct-val num">{Math.round(favShare)}%</span>
            <span className="game-row__pct-team">{favAbbrev}</span>
          </>
        )}
      </div>
    </Link>
  )
}
