/**
 * P3 redirect: every old /tools/* URL maps to its new /studio/* home, preserving path tail and query
 * string so deep links (a specific trade dossier, a prefilled fit search) keep working. Mounted on
 * `/tools` and `/tools/*` in App.tsx.
 */
import { Navigate, useLocation } from 'react-router-dom'

const EXACT: Record<string, string> = {
  '/tools': '/studio',
  '/tools/offseason': '/studio/offseason',
  '/tools/lineup-lab': '/studio/lineups/lines',
  '/tools/roster-builder': '/studio/lineups/roster',
  '/tools/trade-fit': '/studio/trades/fit',
  '/tools/trade-builder': '/studio/trades/build',
  '/tools/contract-grader': '/studio/contracts',
  '/tools/draft-value': '/studio/draft',
  '/tools/trade-outcomes': '/studio/trades/history',
}

export default function LegacyToolsRedirect() {
  const loc = useLocation()
  const path = loc.pathname.replace(/\/+$/, '') || '/tools'

  // Nested trade-outcomes param routes: /tools/trade-outcomes/<rest> -> /studio/trades/history/<rest>
  const OUTCOMES = '/tools/trade-outcomes/'
  if (path.startsWith(OUTCOMES)) {
    return <Navigate replace to={`/studio/trades/history/${path.slice(OUTCOMES.length)}${loc.search}`} />
  }

  const target = EXACT[path] ?? '/studio'
  return <Navigate replace to={`${target}${loc.search}`} />
}
