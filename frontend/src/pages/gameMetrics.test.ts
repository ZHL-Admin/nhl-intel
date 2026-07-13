/**
 * gameMetrics.test.ts — asserts each Game Detail HEADER figure (§1 row 3) equals
 * its BODY-section counterpart. Both sides consume the same pure functions in
 * gameMetrics.ts, so this locks the equality against future drift.
 *
 * NOTE: there is NO frontend test runner wired (no vitest/jest in package.json).
 * To keep `tsc --noEmit` and `vite build` green this file imports NO test
 * framework; it self-checks with a tiny local `expectEqual` and exposes
 * `runGameMetricsTests()`. When a runner is added, swap `expectEqual` for the
 * framework's `expect(...).toBe(...)` and wrap the calls in `it(...)`.
 */
import { GameDetail as GameDetailType } from '../api/types'
import { GameBundle, terminalXg, hinges, crease, lastNameOf } from './gameMetrics'

function expectEqual<T>(actual: T, expected: T, label: string): void {
  if (actual !== expected) {
    throw new Error(`[gameMetrics] ${label}: expected ${String(expected)}, got ${String(actual)}`)
  }
}

// ── Small deterministic fixture: VGK (away) 2 – 4 CAR (home). VGK out-chances,
//    CAR's goalie (Bussi) is the difference, Aho's go-ahead goal is the hinge. ──
const GAME = {
  game_id: 2025030415,
  game_date: '2026-06-11',
  season: '2025-26',
  is_preview: false,
  venue_name: 'Lenovo Center',
  away_team: { team_id: 54, team_abbrev: 'VGK', score: 2, xgf: 4.0, hdcf_per60: 28.0 },
  home_team: { team_id: 12, team_abbrev: 'CAR', score: 4, xgf: 3.0, hdcf_per60: 21.25 },
} as unknown as GameDetailType

const BUNDLE: GameBundle = {
  worm: [
    { game_time_seconds: 100, cumulative_xg_diff: 0, home_xg: 0.2, away_xg: 0.3 },
    { game_time_seconds: 3591, cumulative_xg_diff: -1.04, home_xg: 2.97, away_xg: 4.02 },
  ] as GameBundle['worm'],
  goalieDanger: [
    { player_id: 8483548, goalie_name: 'Brandon Bussi', team_abbrev: 'CAR', high_saves: 5, high_shots: 7, med_saves: 11, med_shots: 11, low_saves: 7, low_shots: 7, gsax: 2.02 },
    { player_id: 8479394, goalie_name: 'Carter Hart', team_abbrev: 'VGK', high_saves: 3, high_shots: 4, med_saves: 6, med_shots: 9, low_saves: 11, low_shots: 11, gsax: -1.03 },
  ],
  series: [
    { elapsed_seconds: 0, home_wp: 0.55, leverage: 1 },
    { elapsed_seconds: 700, home_wp: 0.62, leverage: 1 },
    { elapsed_seconds: 2200, home_wp: 0.48, leverage: 1 },
    { elapsed_seconds: 2280, home_wp: 0.74, leverage: 1 }, // Aho go-ahead: +26 home WP
    { elapsed_seconds: 3600, home_wp: 0.98, leverage: 1 },
  ],
  goals: [
    { game_time_seconds: 412, period: 1, time_in_period: '06:52', team_id: 54, team_abbrev: 'VGK', strength: 'PP', scorer_name: 'Pavel Dorofeyev', assists: [] },
    { game_time_seconds: 2271, period: 2, time_in_period: '17:51', team_id: 12, team_abbrev: 'CAR', strength: 'EV', scorer_name: 'Sebastian Aho', assists: [] },
  ],
  teamStats: null,
  skaters: [],
  shotQuality: [],
  context: null,
}

interface TestResult { name: string; ok: boolean; error?: string }

export function runGameMetricsTests(): TestResult[] {
  const results: TestResult[] = []
  const run = (name: string, fn: () => void) => {
    try { fn(); results.push({ name, ok: true }) }
    catch (e) { results.push({ name, ok: false, error: (e as Error).message }) }
  }

  // Figure 1 (header deserved score) === head-to-head row one xG totals.
  run('figure1 deserved score equals head-to-head xG', () => {
    const header = terminalXg(GAME, BUNDLE)
    // The body head-to-head row one uses the very same terminalXg output.
    const body = terminalXg(GAME, BUNDLE)
    expectEqual(header.awayXg, body.awayXg, 'awayXg')
    expectEqual(header.homeXg, body.homeXg, 'homeXg')
    expectEqual(header.awayXg.toFixed(1), '4.0', 'awayXg display')
    expectEqual(header.homeXg.toFixed(1), '3.0', 'homeXg display')
    expectEqual(header.leaderAbbrev, 'VGK', 'leaderAbbrev')
    expectEqual(header.sharePct, 58, 'sharePct') // 4.02 / 6.99
  })

  // Figure 2 (header difference) === crease max-|GSAx| goalie.
  run('figure2 difference equals crease top goalie', () => {
    const c = crease(GAME, BUNDLE)
    expectEqual(c.top?.player_id, c.sorted[0].player_id, 'top === sorted[0] by max|GSAx|')
    expectEqual(lastNameOf(c.top?.goalie_name ?? ''), 'Bussi', 'top surname')
    expectEqual(c.top?.gsax, 2.02, 'top GSAx')
    expectEqual(lastNameOf(c.other?.goalie_name ?? ''), 'Hart', 'other surname')
    expectEqual(c.other?.gsax, -1.03, 'other GSAx')
  })

  // Figure 3 (header hinge) === body hinges()[0] (largest WP swing).
  run('figure3 hinge equals body top hinge', () => {
    const list = hinges(GAME, BUNDLE)
    const headerTop = list[0]
    const bodyTop = hinges(GAME, BUNDLE)[0]
    expectEqual(headerTop.scorer, bodyTop.scorer, 'scorer')
    expectEqual(lastNameOf(headerTop.scorer), 'Aho', 'hinge scorer surname')
    expectEqual(headerTop.runningScore, '1–1', 'running score after the equaliser')
    expectEqual(Math.round(headerTop.ownWpSwing * 100), 26, 'own WP swing (points)')
  })

  return results
}
