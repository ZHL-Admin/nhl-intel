/**
 * Draft Value tool API (Handoff 5): empirical pick-value curve, the "85%" theory-test summary,
 * the steal/bust board, and a per-player draft block. All values are realized 7-year-window pWAR in
 * the same WAR units as the rest of the value stack — a wide-band estimate for pre-2021 seasons.
 */
import { apiClient } from './client'

export interface PickValueCurveRow {
  overall_pick: number
  n: number
  ev_mean: number
  ev_median: number
  ev_mean_smooth: number
  ev_median_smooth: number
  p10: number
  p25: number
  p75: number
  p90: number
  share_never_nhl: number
  share_regular: number
}

export interface DraftTheorySummaryRow {
  pick_range: string
  picks: number
  share_below_mean: number
  share_below_median: number
  share_never_nhl: number
  share_became_regular: number
  mean_realized: number
  median_realized: number
}

export interface DraftBoardRow {
  overall_pick: number
  draft_year: number
  full_name: string | null
  pos_group: string | null
  draft_team_abbrev: string | null
  resolved_player_id: number | null
  realized_value: number
  expected_mean: number
  value_above_slot: number
  became_regular: boolean
  made_nhl: boolean
}

export interface DraftPlayerBlock {
  overall_pick: number
  draft_year: number
  round: number
  draft_team_abbrev: string | null
  realized_pwar: number
  realized_value: number
  expected_mean: number
  value_above_slot: number
  pct_within_range: number
  became_regular: boolean
  is_censored: boolean
  is_estimate: boolean
}

export async function getPickValueCurve(): Promise<PickValueCurveRow[]> {
  const { data } = await apiClient.get<PickValueCurveRow[]>('/draft/pick-value-curve')
  return data
}

export async function getDraftTheorySummary(): Promise<DraftTheorySummaryRow[]> {
  const { data } = await apiClient.get<DraftTheorySummaryRow[]>('/draft/theory-summary')
  return data
}

export async function getDraftBoard(
  type: 'steals' | 'busts', pos?: string, limit = 25,
): Promise<DraftBoardRow[]> {
  const { data } = await apiClient.get<DraftBoardRow[]>('/draft/board', {
    params: { type, limit, ...(pos ? { pos } : {}) },
  })
  return data
}

/** A player's draft line; null when the player was undrafted. */
export async function getPlayerDraft(playerId: number): Promise<DraftPlayerBlock | null> {
  const { data } = await apiClient.get<DraftPlayerBlock | null>(`/draft/player/${playerId}`)
  return data
}
