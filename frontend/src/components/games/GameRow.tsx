/**
 * GameRow (Blueprint 2.2) — a scannable 52px game row: status/time mono left, matchup with score,
 * a MiniWorm of the xG differential (live/final) or a possession lean bar (pregame), and one
 * deterministic "reason" to click on the right. The whole row links to the game. Each scored row
 * lazy-fetches its own xG-worm series so the list stays one call + N cheap worm calls.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import MiniWorm from '../common/MiniWorm'
import { getGameXGWorm } from '../../api/games'
import type { Game, XGWormPoint } from '../../api/types'
import { getTeamLogoUrl, getTeamColor } from '../../utils/teams'
import './GameRow.css'

function statusLabel(g: Game): string {
  if (g.is_live) return `LIVE ${g.period ?? ''}${g.time_remaining ? ` ${g.time_remaining}` : ''}`.trim()
  if (g.is_preview) return g.game_time || 'TBD'
  return 'FINAL'
}

/** One deterministic reason to care, from the available list fields. */
function reason(g: Game): string {
  if (g.is_live) return g.period ? `${g.period}${g.time_remaining ? ` ${g.time_remaining}` : ''}` : 'In progress'
  if (g.is_preview) {
    if (g.home_cf_rank && g.away_cf_rank && Math.abs(g.away_cf_rank - g.home_cf_rank) >= 5) {
      return `${g.home_cf_rank < g.away_cf_rank ? g.home_team_abbrev : g.away_team_abbrev} edge`
    }
    return 'Even matchup'
  }
  if (g.home_cf_pct != null && g.away_cf_pct != null && Math.abs(g.home_cf_pct - g.away_cf_pct) > 10) {
    return `${g.home_cf_pct > g.away_cf_pct ? g.home_team_abbrev : g.away_team_abbrev} controlled play`
  }
  return 'Final'
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

  const homeShare = g.home_cf_pct != null && g.away_cf_pct != null
    ? g.home_cf_pct / (g.home_cf_pct + g.away_cf_pct) * 100
    : null
  const wormData = worm?.map((p) => ({ time: p.game_time_seconds, diff: p.cumulative_xg_diff })) ?? []

  return (
    <Link to={`/games/${g.game_id}`} className={`game-row ${g.is_live ? 'game-row--live' : ''}`}>
      <span className={`game-row__status mono ${g.is_live ? 'game-row__status--live' : ''}`}>{statusLabel(g)}</span>

      <span className="game-row__match">
        <img className="game-row__logo" src={getTeamLogoUrl(g.away_team_abbrev)} alt="" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
        <span className="game-row__abbrev">{g.away_team_abbrev}</span>
        <span className="game-row__mid mono">
          {scored ? <span className="game-row__score">{g.away_score ?? 0}–{g.home_score ?? 0}</span> : <span className="game-row__at">@</span>}
        </span>
        <span className="game-row__abbrev">{g.home_team_abbrev}</span>
        <img className="game-row__logo" src={getTeamLogoUrl(g.home_team_abbrev)} alt="" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
      </span>

      <span className="game-row__lean" aria-hidden>
        {scored && wormData.length > 1
          ? <MiniWorm data={wormData} width={112} height={26} />
          : homeShare != null && (
            <span className="game-row__lean-track">
              <span className="game-row__lean-fill" style={{ width: `${homeShare}%`, background: getTeamColor(g.home_team_abbrev) }} />
            </span>
          )}
      </span>

      <span className="game-row__reason mono">{reason(g)} →</span>
    </Link>
  )
}
