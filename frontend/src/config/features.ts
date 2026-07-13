/**
 * Feature flags — the single on/off switches for site sections.
 *
 * GAMES_ENABLED gates the entire Games section (the games index, game detail, the nav entries,
 * and every inbound link into a game page). Nothing is deleted when it is false; the routes
 * redirect home and inbound links render as plain, non-navigating content. Flip to true to
 * restore the section exactly as before — that is the only change required.
 */
export const GAMES_ENABLED = false
