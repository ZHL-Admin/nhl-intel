/**
 * Trade-outcome retrospective API (Handoff 5, Phase D). Realized WAR, wide bands, two lenses:
 * slot-expectation (headline; isolates the trade) and actual-player-taken (secondary; conflates the
 * trade with the drafting). A retrospective on outcomes, never a grade of the decision at the time.
 */
import { apiClient } from './client'

export interface TradeOutcomeRow {
  trade_id: string
  season: string
  trade_date: string
  team: string
  team_count: number
  net_war_slot: number
  net_war_slot_low: number
  net_war_slot_high: number
  net_war_actual: number
  net_war_actual_low: number
  net_war_actual_high: number
  received_count: number
  sent_count: number
  has_pick: boolean
  has_unresolved: boolean
  actual_censored: boolean
  horizon_incomplete: boolean
  confidence: string
}

export interface TradeLedgerEntry {
  asset: string
  type: string
  direction: string
  player_id: number | null
  became_player_id: number | null
  became_player_name: string | null
  slot_war: number
  actual_war: number
  conditional: boolean
  own_pick_assumed: boolean
  actual_unresolved: boolean
}

export interface TradeDetailTeam extends TradeOutcomeRow {
  received: TradeLedgerEntry[]
  sent: TradeLedgerEntry[]
}

export interface TradeDetail {
  trade_id: string
  season: string
  trade_date: string
  teams: TradeDetailTeam[]
  caveat: string
}

export interface TeamTradeLedger {
  team_id: number
  team_abbrev: string
  n_trades: number
  total_net_slot: number
  total_net_actual: number
  trades: TradeOutcomeRow[]
  caveat: string
}

export async function getTradeOutcomes(params: {
  lens?: 'slot' | 'actual'
  order?: 'winners' | 'losers'
  team?: string
  season?: string
  include_incomplete?: boolean
  limit?: number
} = {}): Promise<TradeOutcomeRow[]> {
  const { data } = await apiClient.get<TradeOutcomeRow[]>('/trades/outcomes', { params })
  return data
}

export async function getTradeDetail(tradeId: string): Promise<TradeDetail> {
  const { data } = await apiClient.get<TradeDetail>(`/trades/detail/${encodeURIComponent(tradeId)}`)
  return data
}

export async function getTeamTradeLedger(teamId: number): Promise<TeamTradeLedger> {
  const { data } = await apiClient.get<TeamTradeLedger>(`/teams/${teamId}/trade-ledger`)
  return data
}


// --- Handoff 6: entity-first board + GM layer ---
export interface TradeBoardAsset {
  asset_type: string
  label: string
  war_slot: number
  war_actual: number | null
  resolved: boolean
  player_id: number | null
  became_player_id: number | null
  became_player_name: string | null
  conditional: boolean
}

export interface TradeBoardSide {
  team_id: number | null
  team_abbrev: string
  gm_id: string | null
  gm_name: string | null
  gm_transition: boolean
  slot_war_received: number
  actual_war_received: number | null
  net_war_slot: number
  net_war_actual: number | null
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
  margin_actual: number | null
  band_hw_actual: number | null
  winner_team_id: number | null
  winner_gm_id: string | null
  verdict: 'decisive' | 'lean' | 'too_close'
  incomplete: boolean
  realized_year: number
  is_player_for_picks: boolean
  archetype: string
  confidence: string
}

export interface TraderRecord {
  decisive_wins: number; leans: number; too_close: number; losses: number
}

export interface ValueMapPoint {
  kind: string; id: string; label: string; team_abbrev_for_color: string
  given_up_war: number; gained_war: number; net_war: number; net_band_hw: number
  trade_count: number; record: TraderRecord
}

export interface DossierTenure { team_abbrev: string; start_date: string; end_date: string | null; title: string | null }
export interface DossierTimelinePoint { date: string; cumulative_net_war: number; trade_id: string; regime_key: string }
export interface TraderDossier {
  kind: string; id: string; label: string
  tenures: DossierTenure[]
  net_war: number; net_band_hw: number; trade_count: number; record: TraderRecord
  timeline: DossierTimelinePoint[]
  best: string[]; worst: string[]; deals: string[]
  deal_items: TradeBoardItem[]
  caveat: string
}

export interface ArchetypeAgg {
  archetype: string; label: string; trade_count: number
  split: Record<string, number>
  exemplars: Record<string, string>
}

export async function getTradeBoard(params: {
  sort?: 'lopsided' | 'recent' | 'closest'; lens?: 'slot' | 'actual'; archetype?: string
  include_incomplete?: boolean; season_from?: string; season_to?: string; limit?: number; offset?: number
} = {}): Promise<TradeBoardItem[]> {
  const { data } = await apiClient.get<TradeBoardItem[]>('/trades/board', { params })
  return data
}

export async function getBoardItem(tradeId: string): Promise<TradeBoardItem> {
  const { data } = await apiClient.get<TradeBoardItem>(`/trades/board/${encodeURIComponent(tradeId)}`)
  return data
}

export async function getValueMap(kind: 'team' | 'gm', lens: 'slot' | 'actual' = 'slot'): Promise<ValueMapPoint[]> {
  const { data } = await apiClient.get<ValueMapPoint[]>('/traders/value-map', { params: { kind, lens } })
  return data
}

export async function getDossier(kind: 'team' | 'gm', id: string, lens: 'slot' | 'actual' = 'slot'): Promise<TraderDossier> {
  const { data } = await apiClient.get<TraderDossier>(`/traders/${kind}/${encodeURIComponent(id)}/dossier`, { params: { lens } })
  return data
}

export async function getArchetypes(lens: 'slot' | 'actual' = 'slot'): Promise<ArchetypeAgg[]> {
  const { data } = await apiClient.get<ArchetypeAgg[]>('/trades/archetypes', { params: { lens } })
  return data
}
