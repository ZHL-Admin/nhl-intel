import { apiClient } from './client'
import { ArchetypeCard } from './types'

/** The discovered v2 archetypes (gallery): centroid radar, measured traits, real exemplars. */
export async function getArchetypes(pos?: 'F' | 'D'): Promise<ArchetypeCard[]> {
  const r = await apiClient.get<ArchetypeCard[]>('/archetypes', { params: pos ? { pos } : undefined })
  return r.data
}
// (The /archetypes/style-map endpoint + nhl_models.player_style_map table remain in place —
//  possibly reused later for a per-player similarity view — but the style-map view was dropped.)
