/**
 * RecentResults (§01, sparse/empty slates) — the backfill section shown when the selected date
 * has 3 or fewer games. Walks backward through the prior game dates, pulls the most recent
 * played (final) games, and renders up to three compact single-line result tiles:
 *   50px date | 1fr matchup | 70px status | worm.
 * The playoff series-number tag column is omitted (not derivable from the list payload), so the
 * matchup widens per the doc. Each row lazy-fetches its own worm and links to the recap.
 */
import { useEffect, useState } from 'react'
import GameLink from '../common/GameLink'
import MiniWorm from '../common/MiniWorm'
import { getGamesByDate, getGameXGWorm } from '../../api/games'
import type { Game, GameDate, XGWormPoint } from '../../api/types'
import { getTeamLogoUrl, getTeamColor } from '../../utils/teams'
import './GameRow.css'

function RecentRow({ game: g }: { game: Game }) {
  const [worm, setWorm] = useState<XGWormPoint[] | null>(null)
  useEffect(() => {
    let active = true
    getGameXGWorm(g.game_id).then((w) => active && setWorm(w)).catch(() => active && setWorm([]))
    return () => { active = false }
  }, [g.game_id])

  const wormData = worm?.map((p) => ({ time: p.game_time_seconds, diff: p.cumulative_xg_diff })) ?? []
  const away = g.away_score ?? 0
  const home = g.home_score ?? 0
  const awayLeads = away > home
  const homeLeads = home > away
  const tied = away === home
  const wormColor = tied
    ? 'var(--color-data-neutral)'
    : getTeamColor(awayLeads ? g.away_team_abbrev : g.home_team_abbrev)

  const dateLabel = new Date(`${g.game_date}T00:00:00`)
    .toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    .toUpperCase()

  return (
    <GameLink to={`/games/${g.game_id}`} className="game-tile recent-row">
      <span className="recent-row__date num">{dateLabel}</span>
      <span className="recent-row__matchup">
        <img className="gr-logo" src={getTeamLogoUrl(g.away_team_abbrev)} alt=""
          onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
        <span className={`recent-row__abbrev ${awayLeads ? 'is-winner' : ''}`}>{g.away_team_abbrev}</span>
        <span className={`recent-row__num num ${awayLeads ? 'is-winner' : ''}`}>{away}</span>
        <span className="recent-row__mid">·</span>
        <span className={`recent-row__num num ${homeLeads ? 'is-winner' : ''}`}>{home}</span>
        <span className={`recent-row__abbrev ${homeLeads ? 'is-winner' : ''}`}>{g.home_team_abbrev}</span>
        <img className="gr-logo" src={getTeamLogoUrl(g.home_team_abbrev)} alt=""
          onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
      </span>
      {/* TODO(data): OT/SO suffix — not on the list payload. */}
      <span className="recent-row__status">FINAL</span>
      <span className="recent-row__worm" aria-hidden="true">
        {wormData.length > 1 && (
          <MiniWorm data={wormData} width={180} height={26} color={wormColor} midline />
        )}
      </span>
    </GameLink>
  )
}

export default function RecentResults({ gameDates, selectedDate, onFullSchedule }: {
  gameDates: GameDate[]
  selectedDate: string
  onFullSchedule: () => void
}) {
  const [recent, setRecent] = useState<Game[] | null>(null)

  useEffect(() => {
    let active = true
    const priorDates = gameDates
      .map((d) => d.date)
      .filter((d) => d < selectedDate)
      .sort((a, b) => (a < b ? 1 : -1)) // most recent first

    ;(async () => {
      const collected: Game[] = []
      for (const date of priorDates.slice(0, 6)) {
        if (!active) return
        try {
          const games = await getGamesByDate(date)
          const finals = games.filter((g) => !g.is_preview && !g.is_live)
          collected.push(...finals)
        } catch { /* skip a bad date */ }
        if (collected.length >= 3) break
      }
      if (active) setRecent(collected.slice(0, 3))
    })()

    return () => { active = false }
  }, [gameDates, selectedDate])

  if (!recent || recent.length === 0) return null

  return (
    <section className="recent-results">
      <div className="recent-results__head">
        <h2 className="games-section__eyebrow">Recent results</h2>
        <button type="button" className="recent-results__link" onClick={onFullSchedule}>
          Full schedule →
        </button>
      </div>
      <div className="games-rows">
        {recent.map((g) => <RecentRow key={g.game_id} game={g} />)}
      </div>
    </section>
  )
}
