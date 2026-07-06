import { getGameDates } from '../api/games'

// The freshness contract: the whole app makes ONE /games/dates call, cached 6h in a module singleton.
const TTL = 6 * 60 * 60 * 1000
let cached: { at: number; value: string | null } | null = null
let inflight: Promise<string | null> | null = null

/** "Jul 2" from the latest game date, or null while loading / on error. */
export async function getFreshnessLabel(): Promise<string | null> {
  const now = Date.now()
  if (cached && now - cached.at < TTL) return cached.value
  if (inflight) return inflight
  inflight = getGameDates()
    .then((dates) => {
      const max = dates.reduce((m, d) => (d.date > m ? d.date : m), '')   // ISO strings compare lexically
      const value = max ? new Date(`${max}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : null
      cached = { at: Date.now(), value }
      return value
    })
    .catch(() => { cached = { at: Date.now(), value: null }; return null })
    .finally(() => { inflight = null })
  return inflight
}
