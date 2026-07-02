import { RadarSpoke } from '../api/types'

// Radar spokes grouped into families. Reordering by family makes the radar read as regions, and the
// contiguous runs become the arc-group labels. Skater keys and goalie keys never overlap, so a single
// map/order serves both: a skater simply matches no goalie family (and vice-versa).
const SPOKE_FAMILY: Record<string, string> = {
  // Skater families (skating / offense / defense / deployment)
  finishing: 'Offense', shot_volume: 'Offense', shot_danger: 'Offense', rush_offense: 'Offense',
  cycle_forecheck: 'Offense', playmaking: 'Offense', ev_off_impact: 'Offense',
  ev_def_impact: 'Defense', penalty_diff: 'Defense', physicality: 'Defense',
  pp_value: 'Deployment', pk_role: 'Deployment', def_deployment: 'Deployment',
  burst: 'Skating',
  // Goalie families (saves / workload / consistency / context) — same simplified arc-label treatment
  gsax: 'Saves', hd_gsax: 'Saves', midlow_gsax: 'Saves',
  workload: 'Workload',
  consistency: 'Consistency',
  edge_save: 'Context', quality_faced: 'Context',
}
// Clockwise from the top. Skater order first (skating, offense, defense, deployment), then goalie
// order (saves, workload, consistency, context) — only one set ever applies to a given radar.
const FAMILY_ORDER = ['Skating', 'Offense', 'Defense', 'Deployment', 'Saves', 'Workload', 'Consistency', 'Context']

/** Reorder spokes by family so the radar shape reads as regions, and emit arc-group labels over the
 *  contiguous runs. Spokes without a family mapping pass through ungrouped. */
export function familyRadar(spokes: RadarSpoke[]): { spokes: RadarSpoke[]; arcGroups: { label: string; startKey: string }[] } {
  const present = spokes.filter((s) => s.percentile != null)
  const ordered: RadarSpoke[] = []
  const arcGroups: { label: string; startKey: string }[] = []
  for (const fam of FAMILY_ORDER) {
    const inFam = present.filter((s) => SPOKE_FAMILY[s.key] === fam)
    if (inFam.length) { arcGroups.push({ label: fam, startKey: inFam[0].key }); ordered.push(...inFam) }
  }
  const mapped = new Set(ordered.map((s) => s.key))
  ordered.push(...present.filter((s) => !mapped.has(s.key)))
  return { spokes: ordered.length ? ordered : present, arcGroups }
}
