/**
 * Trade-outcome retrospective API (Handoff 5, Phase D). One value-based verdict in realized WAR with
 * wide bands: players at realized tenure pWAR, picks at the slot's empirical expectation (the round
 * midpoint on pick_value_curve, career-extrapolated). A retrospective on outcomes, never a grade of the
 * decision at the time. ("What the pick actually became" is a separate, deferred asset-lineage tool.)
 */
import { apiClient } from './client'


// --- Handoff 6: entity-first board + GM layer ---
export interface TradeBoardAsset {
  asset_type: string
  label: string
  war_slot: number
  player_id: number | null
  conditional: boolean
  retention: boolean
  retained_pct: number | null
  unvaluable: boolean        // a pick we cannot value (missing round, or draft year < trade season)
}

export interface TradeBoardSide {
  team_id: number | null
  team_abbrev: string
  gm_id: string | null
  gm_name: string | null
  gm_transition: boolean
  slot_war_received: number
  net_war_slot: number
  assets: TradeBoardAsset[]
}

export interface TradeBoardItem {
  trade_id: string
  date: string
  season: string
  team_count: number
  sides: TradeBoardSide[]
  margin_slot: number
  band_hw_slot: number
  winner_team_id: number | null
  winner_gm_id: string | null
  verdict: 'decisive' | 'edge' | 'even'
  incomplete: boolean
  realized_year: number
  window_progress: number   // seasons of the horizon observed (k in "still maturing — year k of H")
  is_player_for_picks: boolean
  archetype: string
  confidence: string
}

export interface TraderRecord {
  decisive_wins: number; edge: number; even: number; losses: number
}

export interface ValueMapPoint {
  kind: string; id: string; label: string; team_abbrev_for_color: string
  given_up_war: number; gained_war: number; net_war: number; net_band_hw: number
  trade_count: number; settled_count: number; maturing_count: number; record: TraderRecord
  rank_value: number; z: number; separation: 'clear' | 'leans' | 'noise'; low_n: boolean
}

export interface DossierTenure { team_abbrev: string; start_date: string; end_date: string | null; title: string | null }
export interface DossierTimelinePoint { date: string; cumulative_net_war: number; trade_id: string; regime_key: string; incomplete: boolean }
export interface TraderDossier {
  kind: string; id: string; label: string
  tenures: DossierTenure[]
  net_war: number; net_band_hw: number; trade_count: number
  settled_count: number; maturing_count: number; record: TraderRecord
  timeline: DossierTimelinePoint[]
  best: string[]; worst: string[]; deals: string[]
  deal_items: TradeBoardItem[]
  partners: DossierPartner[]
  caveat: string
}

export interface ArchetypeAgg {
  archetype: string; label: string; trade_count: number
  settled_count: number; maturing_count: number
  split: Record<string, number>
  exemplars: { label: string; trade_id: string }[]
  timing: { bucket: string; count: number; decisive_pct: number }[]
}

export interface DossierPartner { opponent: string; kind: string; trade_count: number; net_war: number; band_hw: number }

export interface ThesisSummary {
  trades_graded: number; settled_count: number; maturing_count: number
  decisive_count: number; edge_count: number; even_count: number; directional_count: number
  decisive_pct: number; edge_pct: number; even_pct: number; directional_pct: number
  biggest_fleece: { trade_id: string; winner: string | null; margin: number; date: string }
  player_for_picks: { trade_count: number; player_side_won_pct: number; pick_side_won_pct: number; even_pct: number }
  caveat: string
}

export async function getTradeBoard(params: {
  sort?: 'lopsided' | 'recent' | 'closest'; archetype?: string
  season_from?: string; season_to?: string; limit?: number; offset?: number
} = {}): Promise<TradeBoardItem[]> {
  const { data } = await apiClient.get<TradeBoardItem[]>('/trades/board', { params })
  return data
}

export async function getBoardItem(tradeId: string): Promise<TradeBoardItem> {
  const { data } = await apiClient.get<TradeBoardItem>(`/trades/board/${encodeURIComponent(tradeId)}`)
  return data
}

export async function getValueMap(kind: 'team' | 'gm'): Promise<ValueMapPoint[]> {
  const { data } = await apiClient.get<ValueMapPoint[]>('/traders/value-map', { params: { kind } })
  return data
}

export async function getDossier(kind: 'team' | 'gm', id: string): Promise<TraderDossier> {
  const { data } = await apiClient.get<TraderDossier>(`/traders/${kind}/${encodeURIComponent(id)}/dossier`)
  return data
}

export async function getArchetypes(): Promise<ArchetypeAgg[]> {
  const { data } = await apiClient.get<ArchetypeAgg[]>('/trades/archetypes')
  return data
}

export async function getThesisSummary(): Promise<ThesisSummary> {
  const { data } = await apiClient.get<ThesisSummary>('/trades/thesis-summary')
  return data
}
