/**
 * Review-only fixture mode. In DEV builds, visiting a page with `?fixtures` in the URL renders it
 * from local fixtures so layout can be reviewed before real backend feeds exist. Never active in a
 * production build (guarded by import.meta.env.DEV), so the shipped default is always the real data
 * (and, for stubbed feeds, the honest empty state).
 */
export function isFixtureMode(): boolean {
  if (!import.meta.env.DEV) return false
  try {
    return new URLSearchParams(window.location.search).has('fixtures')
  } catch {
    return false
  }
}
