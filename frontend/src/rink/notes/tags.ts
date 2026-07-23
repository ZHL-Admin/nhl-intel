// Tag colors (§6) — applied only to the tag word in meta lines (and its matching
// thumbnail). Keyed by the lowercased tag.
const TAG_COLORS: Record<string, string> = {
  teams: 'var(--tag-teams)',
  players: 'var(--tag-players)',
  goaltending: 'var(--tag-goaltending)',
  trades: 'var(--tag-trades)',
  draft: 'var(--tag-draft)',
}

export function tagColor(tag: string): string {
  return TAG_COLORS[tag.toLowerCase()] ?? 'var(--muted)'
}

/** "Jul 18, 2026" from an ISO date, in the mono meta voice (uppercased by CSS). */
export function fmtDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[(m ?? 1) - 1]} ${d}, ${y}`
}
