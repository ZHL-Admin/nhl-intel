/**
 * Single source for player-facing archetype labels (Part B6).
 *
 * Every surface that shows a player's label set reads it from here, derived from the one place the
 * labels live — nhl_models.player_radar (via GET /players/{id}/radar). `playerLabelsFromRadar`
 * is the pure derivation (used by PlayerProfile, which already holds the radar); `getPlayerLabels`
 * fetches + derives + caches for surfaces that only have a player id. This keeps the Overall /
 * offensive / defensive / descriptor labels from drifting across pages.
 */
import { getPlayerRadar } from './players'
import { PlayerRadar } from './types'

export interface PlayerLabels {
  overall?: string | null
  offensive?: string | null
  defensive?: string | null
  descriptor?: string | null
  season?: string
}

export function playerLabelsFromRadar(r: PlayerRadar): PlayerLabels {
  return {
    overall: r.overall_label,
    offensive: r.offensive_label,
    defensive: r.defensive_label,
    descriptor: r.descriptor,
    season: r.season,
  }
}

const _cache = new Map<string, PlayerLabels | null>()

/** Canonical labels for a player (cached). Returns null if the player has no radar row. */
export async function getPlayerLabels(
  playerId: number | string,
  season?: string,
): Promise<PlayerLabels | null> {
  const key = `${playerId}:${season ?? 'latest'}`
  if (_cache.has(key)) return _cache.get(key)!
  try {
    const labels = playerLabelsFromRadar(await getPlayerRadar(playerId, season))
    _cache.set(key, labels)
    return labels
  } catch {
    _cache.set(key, null)
    return null
  }
}
