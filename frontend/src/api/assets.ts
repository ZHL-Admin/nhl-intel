import { apiClient } from './client'
import { TradeableAsset, PlayerContract, TradeEvaluateRequest, TradeEvaluateResponse, ContractGrade } from './types'

/**
 * Trade tool access layer (P7). Searches the unified tradeable-asset layer (players, prospects,
 * picks — one WAR + dollar currency) and reads a single player's contract + surplus. The trade
 * BUILDER UI is intentionally out of scope here; these are the client functions a future builder
 * (or the PlayerPicker, when extended to assets) consumes.
 */

/** Search across players, prospects, and picks. Blank query returns the top assets of the filter. */
export async function searchAssets(
  opts: { q?: string; type?: 'player' | 'prospect' | 'pick'; org?: string; limit?: number } = {},
): Promise<TradeableAsset[]> {
  const r = await apiClient.get<TradeableAsset[]>('/assets/search', {
    params: { q: opts.q ?? '', type: opts.type, org: opts.org, limit: opts.limit ?? 25 },
  })
  return r.data
}

/** A player's parsed contract and present-valued surplus (with a confidence band). */
export async function getPlayerContract(playerId: number): Promise<PlayerContract> {
  const r = await apiClient.get<PlayerContract>(`/players/${playerId}/contract`)
  return r.data
}

/** Grade an actual or hypothetical contract (player + cap hit + term) as A–F good/fair/bad. */
export async function gradeContract(
  player_id: number, cap_hit: number, term_years: number, season?: string,
): Promise<ContractGrade> {
  const r = await apiClient.post<ContractGrade>('/tools/contract-grade', { player_id, cap_hit, term_years, season })
  return r.data
}

/** EFFICIENCY axis: players ranked by contract surplus — best value first, or 'overpaid' worst first. */
export async function getSurplusRankings(
  order: 'surplus' | 'overpaid' = 'surplus',
  limit = 25,
): Promise<TradeableAsset[]> {
  const r = await apiClient.get<TradeableAsset[]>('/rankings/surplus', { params: { order, limit } })
  return r.data
}

/** TALENT axis: assets ranked by projected on-ice value in dollars (a fairly paid star ranks high
 * here even with near-zero surplus). Optionally filter to player | prospect | pick.
 * (Path is /rankings/talent — /rankings/value is the separate GAR leaderboard.) */
export async function getTalentRankings(
  type?: 'player' | 'prospect' | 'pick',
  limit = 25,
): Promise<TradeableAsset[]> {
  const r = await apiClient.get<TradeableAsset[]>('/rankings/talent', { params: { type, limit } })
  return r.data
}

/** Evaluate a proposed multi-team trade -> per-team talent/surplus/fit/cap decomposition. */
export async function evaluateTrade(req: TradeEvaluateRequest): Promise<TradeEvaluateResponse> {
  const r = await apiClient.post<TradeEvaluateResponse>('/tools/trade-evaluate', req)
  return r.data
}
