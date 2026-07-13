/**
 * Free-agent pool client (doc 19 §7 / doc 10 §4). Remaining UFAs, batch-scored nightly, with a
 * projected award {years, aav}, projected WAR, and per-team fit grades. Stub until the model output
 * lands (empty by default); `fixtures` requests review-only synthetic rows.
 */
import { apiClient } from './client'
import type { FreeAgentRow } from './types'

export async function getFreeAgents(params?: { limit?: number; fixtures?: boolean }): Promise<FreeAgentRow[]> {
  const res = await apiClient.get<FreeAgentRow[]>('/free-agents', {
    params: {
      limit: params?.limit,
      fixtures: params?.fixtures || undefined,
    },
  })
  return res.data
}
