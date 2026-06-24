/**
 * Single source of truth for metric naming on the frontend.
 *
 * Each metric declares its display label, value format, and (from Phase 6) its
 * glossary key exactly once. Components reference these helpers instead of
 * hardcoding stat strings, so renames and proxy labelling happen in one place.
 */
import type { PowerRatingRow, TeamDetail } from '../api/types'

export type MetricFormat =
  | 'percent' // 0..1 or 0..100 rendered as %
  | 'rate' // per-60 style decimals
  | 'count' // integers
  | 'decimal2' // two-decimal floats (e.g. xG)
  | 'plus_minus' // signed (e.g. GSAx)

export interface MetricMeta {
  key: string
  label: string
  format: MetricFormat
  /** Concept-card key, wired to the glossary in Phase 6. */
  glossaryKey?: string
  /** When true, the UI appends "(proxy)" to the label (derived, not observed). */
  proxy?: boolean
}

export const METRICS: Record<string, MetricMeta> = {
  cf_pct: { key: 'cf_pct', label: 'Corsi For %', format: 'percent', glossaryKey: 'corsi' },
  xgf_pct: { key: 'xgf_pct', label: 'Expected Goals %', format: 'percent', glossaryKey: 'xg' },
  hdcf_per60: { key: 'hdcf_per60', label: 'High-danger Chances /60', format: 'rate', glossaryKey: 'high_danger' },
  hdca_per60: { key: 'hdca_per60', label: 'High-danger Chances Against /60', format: 'rate', glossaryKey: 'high_danger' },
  ixg: { key: 'ixg', label: 'Individual xG', format: 'decimal2', glossaryKey: 'xg' },
  gsax: { key: 'gsax', label: 'GSAx', format: 'plus_minus', glossaryKey: 'gsax' },
  zone_entry_proxy_success_rate: {
    key: 'zone_entry_proxy_success_rate',
    label: 'Zone Entry Success',
    format: 'percent',
    proxy: true,
    glossaryKey: 'zone_entry_proxy',
  },
  hits: { key: 'hits', label: 'Hits', format: 'count', glossaryKey: 'scorer_bias' },
  giveaways: { key: 'giveaways', label: 'Giveaways', format: 'count', glossaryKey: 'scorer_bias' },
  takeaways: { key: 'takeaways', label: 'Takeaways', format: 'count', glossaryKey: 'scorer_bias' },
  cf_pct_score_adj: { key: 'cf_pct_score_adj', label: 'Corsi For % (score-adj)', format: 'percent', glossaryKey: 'score_adjustment' },
  xgf_pct_score_adj: { key: 'xgf_pct_score_adj', label: 'Expected Goals % (score-adj)', format: 'percent', glossaryKey: 'score_adjustment' },
}

/**
 * Glossary keys whose concept cards explain an adjustment (wired to ConceptTip in
 * Phase 6). `scorer_bias` covers the rink (arena) adjustment for hits/giveaways/takeaways;
 * `score_adjustment` covers the score-state weighting of possession/xG shares.
 */
export const ADJUSTMENT_GLOSSARY = {
  scorer_bias: {
    term: 'Scorer-bias adjustment',
    shortDef:
      'Home-arena scorekeepers record hits, giveaways, and takeaways at different rates. ' +
      'Adjusted values divide the raw count by the arena multiplier (measured from visiting teams).',
    methodologyHref: '/learn/methodology/scorer-bias',
  },
  score_adjustment: {
    term: 'Score-state adjustment',
    shortDef:
      'Trailing teams shoot more, inflating raw shot shares. Score-adjusted shares weight ' +
      'each event by the league-average rate for its score state so the score effect is removed.',
    methodologyHref: '/learn/methodology/score-state-adjustment',
  },
} as const

/**
 * Plain-language tooltips for the Rankings page columns (Phase 3.1). Keyed by column,
 * rendered via the shared Tooltip on table headers. All rating values are goals/game.
 */
export const RATINGS_GLOSSARY = {
  power_rating: {
    term: 'Power rating',
    shortDef:
      'Overall team strength in net goals per game, the sum of four components: 5v5 play, ' +
      'finishing, goaltending, and special teams. Component weights are fit by how well ' +
      'they predict game results.',
    methodologyHref: '/learn/methodology/power-ratings',
  },
  play_5v5: {
    term: '5v5 play',
    shortDef:
      'Score- and opponent-adjusted even-strength chance creation minus suppression, in ' +
      'goals per game. The most repeatable component.',
    methodologyHref: '/learn/methodology/power-ratings',
  },
  finishing: {
    term: 'Finishing',
    shortDef:
      'Goals scored above expected at 5v5, regressed hard toward zero because team ' +
      'finishing is mostly noise year to year.',
    methodologyHref: '/learn/methodology/power-ratings',
  },
  goaltending: {
    term: 'Goaltending',
    shortDef:
      'Even-strength goals saved above expected (GSAx), regressed toward zero by shot volume.',
    methodologyHref: '/learn/methodology/power-ratings',
  },
  special_teams: {
    term: 'Special teams',
    shortDef: 'Power-play plus penalty-kill goals above expected, per game.',
    methodologyHref: '/learn/methodology/power-ratings',
  },
  trajectory: {
    term: 'Trajectory',
    shortDef: 'Change in total rating versus 15 days ago (rising or falling form).',
    methodologyHref: '/learn/methodology/power-ratings',
  },
  uncertainty: {
    term: 'Uncertainty',
    shortDef:
      'Standard error of the rating from resampling the team’s games. Smaller late in ' +
      'the season as the sample grows.',
    methodologyHref: '/learn/methodology/power-ratings',
  },
  deserved_points: {
    term: 'Deserved points',
    shortDef:
      'Average standings points across 10,000 replays of the season where each game’s ' +
      'goals are random draws from the chances created (expected goals). Luck delta = ' +
      'actual minus deserved.',
    methodologyHref: '/learn/methodology/power-ratings',
  },
} as const

/**
 * Power-rating component palette (Phase 3.1) — key -> glossary key, response field, label,
 * colour. Single source shared by the Rankings power stack bars and their legend, mirroring
 * how COMPOSITE_COMPONENTS / VALUE_COMPONENTS drive the player stacks.
 */
export const RATINGS_COMPONENTS: {
  key: keyof typeof RATINGS_GLOSSARY
  contrib: keyof PowerRatingRow
  label: string
  color: string
}[] = [
  { key: 'play_5v5', contrib: 'contrib_play_5v5', label: '5v5 play', color: '#3b82f6' },
  { key: 'finishing', contrib: 'contrib_finishing', label: 'Finishing', color: '#22c55e' },
  { key: 'goaltending', contrib: 'contrib_goaltending', label: 'Goaltending', color: '#a855f7' },
  { key: 'special_teams', contrib: 'contrib_special_teams', label: 'Special teams', color: '#f59e0b' },
]

/**
 * Team identity fingerprint metrics (Phase 3.2), grouped for display. Each entry's `key`
 * matches a metric from /teams/{id}/identity; `label` is the single-sourced display name.
 * Percentiles are shown as-is (higher percentile = higher raw value); for "allowed"
 * metrics a higher value is worse, flagged with `inverse` so the UI can note it.
 */
export interface FingerprintMetric {
  key: string
  label: string
  inverse?: boolean // higher raw value is "worse" (e.g. chances allowed)
}
export const FINGERPRINT_GROUPS: { title: string; metrics: FingerprintMetric[] }[] = [
  {
    title: 'Offense mix',
    metrics: [
      { key: 'rush_share_for', label: 'Rush' },
      { key: 'forecheck_share_for', label: 'Forecheck' },
      { key: 'cycle_share_for', label: 'Cycle' },
      { key: 'point_shot_share_for', label: 'Point shots' },
      { key: 'rebound_share_for', label: 'Rebounds' },
    ],
  },
  {
    title: 'Defense (chances allowed)',
    metrics: [
      { key: 'rush_share_against', label: 'Rush allowed', inverse: true },
      { key: 'forecheck_share_against', label: 'Forecheck allowed', inverse: true },
      { key: 'cycle_share_against', label: 'Cycle allowed', inverse: true },
      { key: 'point_shot_share_against', label: 'Point shots allowed', inverse: true },
      { key: 'rebound_share_against', label: 'Rebounds allowed', inverse: true },
    ],
  },
  {
    title: 'Play style',
    metrics: [
      { key: 'pace', label: 'Pace' },
      { key: 'shot_quality', label: 'Shot quality (xG/attempt)' },
      { key: 'shot_volume_per60', label: 'Shot volume /60' },
      { key: 'hits_per60', label: 'Hitting /60' },
      { key: 'penalties_taken_per60', label: 'Penalties taken /60', inverse: true },
      { key: 'penalties_drawn_per60', label: 'Penalties drawn /60' },
    ],
  },
  {
    title: 'Special teams & territory',
    metrics: [
      { key: 'pp_point_shot_share', label: 'PP point-shot structure' },
      { key: 'oz_time_pct', label: 'O-zone time' },
      { key: 'dz_time_pct', label: 'D-zone time', inverse: true },
      { key: 'oz_conversion', label: 'Territory-to-danger conversion' },
    ],
  },
]

/**
 * Player archetypes (Phase 4.2), grouped by position for the Players-index selector. Order
 * roughly elite -> depth. Mirrors models_ml/config.ARCHETYPE_NAMES.
 */
export const ARCHETYPES: { F: string[]; D: string[] } = {
  F: [
    'Elite Offensive Driver', 'Top-Six Playmaker', 'Perimeter Scorer', 'Secondary Scorer',
    'Inside Scorer', 'North-South Forward', 'Two-Way Forward', 'Middle-Six Forward',
    'Physical Energy Forward', 'Checking Forward', 'Penalty-Kill Forward', 'Fourth-Line Forward',
  ],
  D: [
    'Elite Offensive D', 'Power-Play Quarterback', 'Puck-Moving D', 'Attacking D',
    'Two-Way Top-Four D', 'Point-Shot D', 'Sheltered Offensive D', 'Penalty-Kill D',
    'Stay-Home Defenseman', 'Physical Defenseman', 'Depth Defenseman',
  ],
}

/** Composite component key -> colour, shared by the composite ComponentStackBar everywhere. */
export const COMPOSITE_COMPONENTS: { key: string; label: string; color: string }[] = [
  { key: 'ev_offense', label: 'EV Offense', color: '#3b82f6' },
  { key: 'ev_defense', label: 'EV Defense', color: '#06b6d4' },
  { key: 'pp', label: 'Power Play', color: '#f59e0b' },
  { key: 'pk', label: 'Penalty Kill', color: '#a855f7' },
  { key: 'finishing', label: 'Finishing', color: '#22c55e' },
  { key: 'penalty_diff', label: 'Penalties', color: '#64748b' },
  { key: 'goalie_gsax', label: 'Goaltending', color: '#ec4899' },
]

/** GAR value-component key -> colour (the Value/GAR stack). Shares colours with COMPOSITE_*
 * where keys overlap, so the two lenses read consistently. */
export const VALUE_COMPONENTS: { key: string; label: string; color: string }[] = [
  { key: 'ev_offense', label: 'EV Offense', color: '#3b82f6' },
  { key: 'pp', label: 'Power Play', color: '#f59e0b' },
  { key: 'ev_defense', label: 'EV Defense', color: '#06b6d4' },
  { key: 'pk', label: 'Penalty Kill', color: '#a855f7' },
  { key: 'penalty', label: 'Penalties', color: '#64748b' },
  { key: 'faceoff', label: 'Faceoffs', color: '#ec4899' },
]

/** Goalie GAR value-component key -> colour (goals saved above a backup). A DISTINCT save-tier
 * palette (green ramp + indigo PK) so goalie rows on the mixed leaderboard read as a different
 * vocabulary from skaters; matches schemas.GOALIE_GAR_LABELS / config.GOALIE_GAR_COMPONENTS. */
export const GOALIE_VALUE_COMPONENTS: { key: string; label: string; color: string }[] = [
  { key: 'hd_saves', label: 'High-Danger Saves', color: '#16a34a' },
  { key: 'md_saves', label: 'Mid-Danger Saves', color: '#34d399' },
  { key: 'ld_saves', label: 'Low-Danger Saves', color: '#a7f3d0' },
  { key: 'pk_goaltending', label: 'Penalty-Kill', color: '#6366f1' },
]

/**
 * Short 1–2 word radar spoke labels for the COMPACT small-multiple radars (archetype gallery cards).
 * Keyed by spoke key; the full label is still shown on hover and in the expanded detail radar.
 */
export const SHORT_SPOKE_LABELS: Record<string, string> = {
  finishing: 'Finish', shot_volume: 'Volume', shot_danger: 'Danger', rush_offense: 'Rush',
  cycle_forecheck: 'Cycle', playmaking: 'Playmk', ev_off_impact: 'EV O', pp_value: 'PP',
  burst: 'Speed', ev_def_impact: 'EV D', pk_role: 'PK', def_deployment: 'Deploy',
  penalty_diff: 'Pen Diff', physicality: 'Hits',
}

/**
 * Arc-group labels drawn outside the compact radar ring so neighborhoods read at a glance. Each
 * group is the contiguous run of spokes (in ring order) STARTING at `startKey` up to the next group.
 * Order matches the shipped radar spoke order (offense block, then ST/defense, then style).
 */
export const RADAR_ARC_GROUPS: { label: string; startKey: string }[] = [
  { label: 'Offense', startKey: 'finishing' },
  { label: 'Special teams & defense', startKey: 'pp_value' },
  { label: 'Style', startKey: 'penalty_diff' },
]

/* ============================================================================
   Team Overview "Season snapshot" — config-driven StatCard groups (TeamProfile Overview)
   ============================================================================ */
export interface SnapshotStat {
  key: string                              // field on TeamDetail, or a derived key resolved below
  label: string
  format: 'pct' | 'rate' | 'decimal2'
  rankKey: string                          // TeamDetail league-rank field; absent on the team -> no chip
  higherIsBetter: boolean                  // documents direction; the chip tier comes from the rank itself
  glossaryKey?: string                     // -> SNAPSHOT_TOOLTIPS
}
export interface SnapshotGroup { id: string; label: string; stats: SnapshotStat[] }

export const TEAM_SNAPSHOT_GROUPS: SnapshotGroup[] = [
  { id: 'offense', label: 'Offense', stats: [
    { key: 'gf_per_gp',  label: 'GF / GP',   format: 'decimal2', rankKey: 'gf_per_gp_rank',  higherIsBetter: true,  glossaryKey: 'gf_per_gp' },
    { key: 'xgf_pct',    label: 'xGF %',     format: 'pct',      rankKey: 'xgf_pct_rank',    higherIsBetter: true,  glossaryKey: 'xgf_pct' },
    { key: 'hdcf_per60', label: 'HDCF / 60', format: 'rate',     rankKey: 'hdcf_per60_rank', higherIsBetter: true,  glossaryKey: 'hdcf' },
  ]},
  { id: 'defense', label: 'Defense', stats: [
    { key: 'ga_per_gp',  label: 'GA / GP',   format: 'decimal2', rankKey: 'ga_per_gp_rank',  higherIsBetter: false, glossaryKey: 'ga_per_gp' },
    { key: 'hdca_per60', label: 'HDCA / 60', format: 'rate',     rankKey: 'hdca_per60_rank', higherIsBetter: false, glossaryKey: 'hdca' },
    { key: 'xga_per60',  label: 'xGA / 60',  format: 'rate',     rankKey: 'xga_per60_rank',  higherIsBetter: false, glossaryKey: 'xga' },
  ]},
  { id: 'possession', label: 'Possession & special teams', stats: [
    { key: 'cf_pct',                        label: 'CF %',         format: 'pct', rankKey: 'cf_pct_rank',                        higherIsBetter: true, glossaryKey: 'cf_pct' },
    { key: 'zone_entry_proxy_success_rate', label: 'Zone entry %', format: 'pct', rankKey: 'zone_entry_proxy_success_rate_rank', higherIsBetter: true, glossaryKey: 'zone_entry_proxy' },
    { key: 'faceoff_win_pct',               label: 'Faceoff %',    format: 'pct', rankKey: 'faceoff_win_pct_rank',               higherIsBetter: true, glossaryKey: 'faceoff_pct' },
  ]},
]

export const SNAPSHOT_TOOLTIPS: Record<string, string> = {
  gf_per_gp: 'Goals for per game played.',
  ga_per_gp: 'Goals against per game played (lower is better).',
  xgf_pct: 'Expected-goals share at 5v5.',
  hdcf: 'High-danger chances FOR per 60 minutes.',
  hdca: 'High-danger chances AGAINST per 60 (lower is better).',
  xga: 'Expected goals against per 60 (lower is better).',
  cf_pct: 'Corsi For % — share of shot attempts at 5v5.',
  zone_entry_proxy: 'Derived proxy: inferred from consecutive event zone codes, not measured entries.',
  faceoff_pct: 'Share of faceoffs won (all situations).',
}

/** One snapshot tile's view model from TeamDetail (handles derived keys + formatting). Config-driven. */
export function snapshotStatView(t: TeamDetail, stat: SnapshotStat): { value: string; rank?: number; tooltip?: string } {
  const gp = Math.max(1, t.games_played)
  const raw: number | null | undefined =
    stat.key === 'gf_per_gp' ? t.total_goals_for / gp
    : stat.key === 'ga_per_gp' ? t.total_goals_against / gp
    : stat.key === 'xgf_pct' ? (t.xgf_per60 + t.xga_per60 > 0 ? t.xgf_per60 / (t.xgf_per60 + t.xga_per60) : null)
    : (t as unknown as Record<string, number | null | undefined>)[stat.key]
  let value = '—'
  if (raw != null) {
    value = stat.format === 'pct' ? `${(raw * 100).toFixed(1)}%`
      : stat.format === 'rate' ? raw.toFixed(1)
      : raw.toFixed(2)
  }
  const rankVal = (t as unknown as Record<string, unknown>)[stat.rankKey]
  const rank = typeof rankVal === 'number' ? rankVal : undefined
  return { value, rank, tooltip: stat.glossaryKey ? SNAPSHOT_TOOLTIPS[stat.glossaryKey] : undefined }
}

/** Display label for a metric, appending "(proxy)" for derived metrics. */
export function metricLabel(key: string): string {
  const m = METRICS[key]
  if (!m) return key
  return m.proxy ? `${m.label} (proxy)` : m.label
}
