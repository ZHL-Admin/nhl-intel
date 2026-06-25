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
