/**
 * Moves feed client (doc 19 §5 / doc 10). One dated, global, newest-first source with two consumers
 * (Home Ledger, Offseason Forecast). The backend is a stub until the nightly DAG writes verdicts, so
 * the default response is an empty page; the UI renders its empty state. `fixtures` requests
 * review-only synthetic rows from the stub. Verdicts are server-precomputed — never graded here.
 */
import { apiClient } from './client'
import type { MovesPage } from './types'

export async function getMoves(params?: { limit?: number; offset?: number; fixtures?: boolean }): Promise<MovesPage> {
  const res = await apiClient.get<MovesPage>('/moves', {
    params: {
      limit: params?.limit,
      offset: params?.offset,
      fixtures: params?.fixtures || undefined,
    },
  })
  return res.data
}
