/**
 * GameNarrative (Blueprint 2.3) — the top of "The game": the deterministic verdict sentence, the three
 * biggest win-probability moments, and the P4 team comparison. All composed from the game's own
 * payloads — no free text.
 *
 * Consistency fixes (F1–F4):
 *  F1  GSAx is single-sourced from the danger-band table (getGameGoalieDanger) — the per-game,
 *      xG-derived number — and drives the verdict's theft branch.
 *  F2  the comparison's xG row is all-situations total xGF (same basis as the team-stats receipts);
 *      the timeline worm lane carries its own basis label separately.
 *  F3  CF% renders as a percent (the payload is a fraction).
 *  F4  moments are computed from the raw win-prob SERIES joined to the goals feed (goal_swings has a
 *      bracketing bug), signed from the scoring team's own perspective, floored at 5 points, top 3.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { CompareRows, Tabs, type CompareRow } from '../common'
import { getGameTeamStats, getGameGoalieDanger, getGameWinProb, getGameGoals, getGameXGWorm } from '../../api/games'
import type { GameDetail, TeamComparisonStats, GoalieDangerStat, WinProbPoint, GoalDetail, XGWormPoint } from '../../api/types'
import { composeGameVerdict } from '../../config/gameVerdicts'
import { getTeamColor } from '../../utils/teams'
import './GameNarrative.css'

const momentTime = (s: number) => {
  const period = s < 3600 ? Math.floor(s / 1200) + 1 : 4
  const inP = s < 3600 ? s - (period - 1) * 1200 : s - 3600
  return `${period > 3 ? 'OT' : `P${period}`} ${Math.floor(inP / 60)}:${String(Math.floor(inP % 60)).padStart(2, '0')}`
}

const MOMENT_FLOOR = 0.05 // 5 win-probability points to qualify as a moment (F4)

export default function GameNarrative({ game, timeline }: { game: GameDetail; timeline?: ReactNode }) {
  const [teamStats, setTeamStats] = useState<TeamComparisonStats | null>(null)
  const [goalieDanger, setGoalieDanger] = useState<GoalieDangerStat[]>([])
  const [series, setSeries] = useState<WinProbPoint[] | null>(null)
  const [goals, setGoals] = useState<GoalDetail[]>([])
  const [worm, setWorm] = useState<XGWormPoint[] | null>(null) // F2: single xG source (matches the lane)
  const [adjusted, setAdjusted] = useState(false) // V7: Raw | Adjusted for the comparison block

  const gid = game.game_id
  useEffect(() => {
    let active = true
    getGameTeamStats(gid).then((d) => active && setTeamStats(d)).catch(() => {})
    getGameGoalieDanger(gid).then((d) => active && setGoalieDanger(d)).catch(() => {})
    getGameWinProb(gid).then((d) => active && setSeries(d.series ?? [])).catch(() => active && setSeries([]))
    getGameGoals(gid).then((d) => active && setGoals(d)).catch(() => {})
    getGameXGWorm(gid).then((d) => active && setWorm(d)).catch(() => {})
    return () => { active = false }
  }, [gid])

  // F2: the timeline worm and the comparison must agree on xG. Both use the shot-level worm source
  // (models.shot_xg summed) — the worm's terminal home/away xG — NOT the team-mart xgf (a different
  // model that even disagreed on who led). Fall back to detail xgf only until the worm loads.
  const wormLast = worm && worm.length ? worm[worm.length - 1] : null
  const awayXg = wormLast ? wormLast.away_xg : (game.away_team.xgf ?? 0)
  const homeXg = wormLast ? wormLast.home_xg : (game.home_team.xgf ?? 0)

  const home = game.home_team
  const away = game.away_team
  const homeWon = (home.score ?? 0) > (away.score ?? 0)
  const winner = homeWon ? home : away
  const loser = homeWon ? away : home

  // F1: winning team's starter (most danger shots faced), GSAx from the danger table.
  const winGoalie = goalieDanger
    .filter((g) => g.team_abbrev === winner.team_abbrev)
    .sort((a, b) => (b.high_shots + b.med_shots + b.low_shots) - (a.high_shots + a.med_shots + a.low_shots))[0]

  const margin = Math.abs((home.score ?? 0) - (away.score ?? 0))
  const ppToWinner = teamStats
    ? (homeWon ? teamStats.home_pp_goals - teamStats.away_pp_goals : teamStats.away_pp_goals - teamStats.home_pp_goals)
    : 0

  const verdict = composeGameVerdict({
    winnerAbbrev: winner.team_abbrev,
    loserAbbrev: loser.team_abbrev,
    upset: false, // D33: pregame win-prob isn't on this payload (deferred, no backend change)
    xgWinnerIsWinner: (homeXg > awayXg) === homeWon,
    goalieTheft: !!winGoalie && winGoalie.gsax >= 1.5,
    specialTeamsDecided: margin > 0 && ppToWinner >= margin,
    goalieName: winGoalie?.goalie_name,
    gsax: winGoalie?.gsax,
  })

  // F4: swing per goal from the raw series (before = last point strictly before; after = first point
  // at/after the goal), signed from the scoring team's own perspective.
  const s = series ?? []
  const moments = goals
    .map((g) => {
      const before = s.filter((p) => p.elapsed_seconds < g.game_time_seconds).slice(-1)[0]
      const after = s.find((p) => p.elapsed_seconds >= g.game_time_seconds)
      if (!before || !after) return null
      const homeDelta = after.home_wp - before.home_wp
      const own = g.team_id === home.team_id ? homeDelta : -homeDelta
      return { time: g.game_time_seconds, scorer: g.scorer_name ?? 'Goal', teamId: g.team_id, own }
    })
    .filter((m): m is NonNullable<typeof m> => !!m && Math.abs(m.own) >= MOMENT_FLOOR)
    .sort((a, b) => Math.abs(b.own) - Math.abs(a.own))
    .slice(0, 3)
    .sort((a, b) => a.time - b.time)

  const awayColor = getTeamColor(away.team_abbrev)
  const homeColor = getTeamColor(home.team_abbrev)

  // F3: CF% is a fraction → render as percent. K6: the control/danger rows (HD chances/60, giveaways,
  // takeaways) fold in here. V7: the Adjusted toggle swaps score/venue-adjusted variants where they exist.
  const n = (v?: number | null) => v ?? 0
  const aCf = n(adjusted ? away.cf_pct_score_adj : away.cf_pct)
  const bCf = n(adjusted ? home.cf_pct_score_adj : home.cf_pct)
  const pct = (v: number) => `${(v * 100).toFixed(0)}%`
  const cnt = (label: string, a: number, b: number, descriptive = false): CompareRow =>
    ({ label, aValue: a, bValue: b, aDisplay: String(Math.round(a)), bDisplay: String(Math.round(b)), descriptive })
  const rows: CompareRow[] = teamStats
    ? [
        { label: 'Expected goals', aValue: awayXg, bValue: homeXg, aDisplay: awayXg.toFixed(2), bDisplay: homeXg.toFixed(2) },
        { label: 'Shots on goal', aValue: teamStats.away_sog, bValue: teamStats.home_sog },
        { label: '5v5 CF%', aValue: aCf, bValue: bCf, aDisplay: pct(aCf), bDisplay: pct(bCf) },
        { label: 'HD chances / 60', aValue: n(away.hdcf_per60), bValue: n(home.hdcf_per60), aDisplay: n(away.hdcf_per60).toFixed(1), bDisplay: n(home.hdcf_per60).toFixed(1) },
        { label: 'Power-play goals', aValue: teamStats.away_pp_goals, bValue: teamStats.home_pp_goals },
        { label: 'Faceoff wins', aValue: teamStats.away_faceoff_wins, bValue: teamStats.home_faceoff_wins },
        cnt('Hits', n(adjusted ? away.hits_adj : away.hits), n(adjusted ? home.hits_adj : home.hits), true),
        cnt('Giveaways', n(adjusted ? away.giveaways_adj : away.giveaways), n(adjusted ? home.giveaways_adj : home.giveaways), true),
        cnt('Takeaways', n(adjusted ? away.takeaways_adj : away.takeaways), n(adjusted ? home.takeaways_adj : home.takeaways), true),
      ]
    : []

  return (
    <div className="game-narrative">
      <p className="game-narrative__verdict">{verdict}</p>

      {timeline && (
        <section className="game-narrative__timeline">
          <h3 className="page-region-title">Game timeline</h3>
          <p className="game-narrative__compare-dek">Cumulative xG differential (all situations), win probability, and shot pressure across the 60 minutes.</p>
          {timeline}
        </section>
      )}

      {moments.length > 0 && (
        <section className="game-narrative__moments">
          <h3 className="page-region-title">{moments.length === 1 ? 'The moment' : `The ${moments.length === 2 ? 'two' : 'three'} moments`}</h3>
          {moments.map((m, i) => (
            <div className="game-narrative__moment" key={i}>
              <span className="game-narrative__moment-time mono">{momentTime(m.time)}</span>
              <span className="game-narrative__moment-text">{m.scorer} scored</span>
              <span className="game-narrative__moment-delta mono" style={{ color: m.teamId === home.team_id ? homeColor : awayColor }}>
                +{Math.round(Math.abs(m.own) * 100)} WP
              </span>
            </div>
          ))}
        </section>
      )}

      {rows.length > 0 && (
        <section className="game-narrative__compare">
          <div className="game-narrative__compare-head">
            <h3 className="page-region-title" style={{ margin: 0 }}>
              <span style={{ color: awayColor }}>{away.team_abbrev}</span> vs <span style={{ color: homeColor }}>{home.team_abbrev}</span>
            </h3>
            <Tabs
              options={[{ value: 'raw', label: 'Raw' }, { value: 'adjusted', label: 'Adjusted' }]}
              value={adjusted ? 'adjusted' : 'raw'}
              onChange={(v) => setAdjusted(v === 'adjusted')}
            />
          </div>
          <p className="game-narrative__compare-dek">All situations · {adjusted ? 'score- and venue-adjusted' : 'raw counts'} · expected goals sum the shot-level model shown in the timeline.</p>
          <CompareRows rows={rows} aColor={awayColor} bColor={homeColor} />
        </section>
      )}
    </div>
  )
}
