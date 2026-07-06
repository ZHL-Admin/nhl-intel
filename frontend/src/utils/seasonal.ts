// Seasonal surfacing (D20). Playoffs nav + Today's "The race" module show only Mar 1 → Jun 30
// (playoff run, hardcoded Jun 30 outer bound). The offseason Today module shows Jul 1 → Sep 30.
// Deep links (/playoffs, /studio/offseason) always work; only visibility is gated.

function monthDay(d = new Date()): number {
  return (d.getMonth() + 1) * 100 + d.getDate()   // e.g. Jul 5 -> 705
}

/** True Mar 1 through Jun 30 — the playoff run window (D20). */
export function inPlayoffWindow(d = new Date()): boolean {
  const md = monthDay(d)
  return md >= 301 && md <= 630
}

/** True Jul 1 through Sep 30 — the offseason window (Today's offseason board). */
export function inOffseasonWindow(d = new Date()): boolean {
  const md = monthDay(d)
  return md >= 701 && md <= 930
}
