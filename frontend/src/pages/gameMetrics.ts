/**
 * gameMetrics — the SINGLE source of truth for the three headline figures on the
 * Game Detail page. The header (§1 row 3) and the body sections (run of play,
 * hinges, crease) both import these pure functions, so a header figure equals its
 * body-section counterpart BY CONSTRUCTION. See gameMetrics.test.ts for the
 * equality assertions (no runner is wired yet — the file is importable/ready).
 */
import {
  GameDetail as GameDetailType, XGWormPoint, GoalieDangerStat, WinProbPoint, GoalDetail,
  ShotQualityRow, SkaterImpact, TeamComparisonStats, GameContext,
} from '../api/types'
import { composeHinge } from '../config/gameCopy'

// ── Shared payload bundle (owned here so gameMetrics is the dependency root) ──
export interface GameBundle {
  worm: XGWormPoint[]
  goalieDanger: GoalieDangerStat[]
  series: WinProbPoint[]
  goals: GoalDetail[]
  teamStats: TeamComparisonStats | null
  skaters: SkaterImpact[]
  shotQuality: ShotQualityRow[]
  context: GameContext | null
}

export const lastNameOf = (name: string) => (name || '').trim().split(' ').slice(-1)[0] || name

// Period-stamp (P# M:SS / OT M:SS) from elapsed seconds.
export function momentTime(s: number): string {
  const period = s < 3600 ? Math.floor(s / 1200) + 1 : 4
  const inP = s < 3600 ? s - (period - 1) * 1200 : s - 3600
  return `${period > 3 ? 'OT' : `P${period}`} ${Math.floor(inP / 60)}:${String(Math.floor(inP % 60)).padStart(2, '0')}`
}

// ── Figure 1 · the deserved score ────────────────────────────────────────────
// Terminal xG (matches head-to-head row one); falls back to team-detail xgf until
// the worm loads. leaderAbbrev / sharePct / leaderHd feed the header figure.
export interface TerminalXg {
  awayXg: number
  homeXg: number
  homeLeads: boolean
  leaderAbbrev: string
  sharePct: number
  leaderHd: number
}
export function terminalXg(game: GameDetailType, bundle: GameBundle): TerminalXg {
  const last = bundle.worm.length ? bundle.worm[bundle.worm.length - 1] : null
  const awayXg = last ? last.away_xg : (game.away_team.xgf ?? 0)
  const homeXg = last ? last.home_xg : (game.home_team.xgf ?? 0)
  const homeLeads = homeXg >= awayXg
  const leaderAbbrev = homeLeads ? game.home_team.team_abbrev : game.away_team.team_abbrev
  const total = awayXg + homeXg
  const sharePct = total > 0 ? Math.round((Math.max(awayXg, homeXg) / total) * 100) : 0
  const leaderHd = (homeLeads ? game.home_team.hdcf_per60 : game.away_team.hdcf_per60) ?? 0
  return { awayXg, homeXg, homeLeads, leaderAbbrev, sharePct, leaderHd }
}

// ── Figure 3 · the hinges ─────────────────────────────────────────────────────
// The largest win-probability swings, joined from the raw series to the goals
// feed. Top swing is index 0 — the header uses hinges(...)[0], the body maps the
// whole (already-sliced) list, so the two agree.
export interface Hinge {
  time: number
  scorer: string
  isHome: boolean
  ownWpSwing: number
  desc: string
  runningScore: string
}
export function hinges(game: GameDetailType, bundle: GameBundle): Hinge[] {
  const home = game.home_team
  const sorted = [...bundle.goals].sort((a, b) => a.game_time_seconds - b.game_time_seconds)
  let hs = 0, as = 0
  const withScore = sorted.map((g) => {
    const homeBefore = hs, awayBefore = as
    if (g.team_id === home.team_id) hs++; else as++
    return { g, homeBefore, awayBefore }
  })
  return withScore
    .map(({ g, homeBefore, awayBefore }) => {
      const before = bundle.series.filter((p) => p.elapsed_seconds < g.game_time_seconds).slice(-1)[0]
      const after = bundle.series.find((p) => p.elapsed_seconds >= g.game_time_seconds)
      if (!before || !after) return null
      const homeDelta = after.home_wp - before.home_wp
      const isHome = g.team_id === home.team_id
      const ownWpSwing = isHome ? homeDelta : -homeDelta
      const homeAfter = homeBefore + (isHome ? 1 : 0)
      const awayAfter = awayBefore + (isHome ? 0 : 1)
      return {
        time: g.game_time_seconds,
        scorer: g.scorer_name ?? 'Goal',
        isHome,
        ownWpSwing,
        desc: composeHinge({ scoringAbbrev: g.team_abbrev, homeBefore, awayBefore, isHome, strength: g.strength }),
        runningScore: `${awayAfter}–${homeAfter}`,
      }
    })
    .filter((m): m is Hinge => !!m && Math.abs(m.ownWpSwing) >= 0.05)
    .sort((a, b) => Math.abs(b.ownWpSwing) - Math.abs(a.ownWpSwing))
    .slice(0, 3)
}

// ── Figure 2 · the crease ─────────────────────────────────────────────────────
// `sorted` (GSAx-descending) drives the body table + its swing caption; `top` is
// the max-|GSAx| goalie (the header's "difference"), `other` is the goalie across
// the ice.
export interface CreaseData {
  sorted: GoalieDangerStat[]
  top: GoalieDangerStat | null
  other: GoalieDangerStat | null
}
export function crease(_game: GameDetailType, bundle: GameBundle): CreaseData {
  const sorted = [...bundle.goalieDanger].sort((a, b) => b.gsax - a.gsax)
  const byAbs = [...bundle.goalieDanger].sort((a, b) => Math.abs(b.gsax) - Math.abs(a.gsax))
  const top = byAbs[0] ?? null
  const other = byAbs.find((g) => g.player_id !== top?.player_id) ?? null
  return { sorted, top, other }
}
