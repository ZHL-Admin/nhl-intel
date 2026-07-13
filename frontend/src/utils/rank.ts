/**
 * Team-rank value coloring (06 v2 §0.2). The player value-color rule translated to a 32-team
 * league: the best six ranks read blue, the worst six (25-32 in a 32-team league) read red,
 * everything else stays ink. Applies to ranks and rank-like values only — never raw stats.
 */
export function rankColor(rank: number, leagueSize = 32): string | undefined {
  if (rank <= 6) return 'var(--line-blue)'
  if (rank >= leagueSize - 6) return 'var(--line-red)'
  return undefined // ink (inherit)
}
