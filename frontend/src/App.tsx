import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useParams, useLocation } from 'react-router-dom'

// RINK THEORY rebuild (§2 site map). The old dashboard routes are archived on the
// `legacy-dashboard` branch/tag; this is the whole public surface now.
import Home from './rink/pages/Home'
import NotesIndex from './rink/pages/NotesIndex'
import Note from './rink/pages/Note'
import Ratings from './rink/pages/Ratings'
import RatingsPlayers from './rink/pages/RatingsPlayers'
import Tools from './rink/pages/Tools'

// Tools are lazy-loaded so the salvaged tool code AND the legacy design-system CSS
// they pull in ship only when a tool route is visited — never on Home/Notes/Ratings.
const TradeLedger = lazy(() => import('./rink/pages/tools/TradeLedger'))
const DraftValueTool = lazy(() => import('./rink/pages/tools/DraftValueTool'))
const LineupLabTool = lazy(() => import('./rink/pages/tools/LineupLabTool'))
const ContractGraderTool = lazy(() => import('./rink/pages/tools/ContractGraderTool'))

/** Redirect that substitutes route params into the target and preserves the query string. */
function LegacyRedirect({ build }: { build: (p: Readonly<Record<string, string | undefined>>) => string }) {
  const params = useParams()
  const { search } = useLocation()
  return <Navigate replace to={build(params) + search} />
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={null}>
      <Routes>
        {/* §2 site map */}
        <Route path="/" element={<Home />} />
        <Route path="/notes" element={<NotesIndex />} />
        <Route path="/notes/:slug" element={<Note />} />
        <Route path="/ratings" element={<Ratings />} />
        <Route path="/ratings/players" element={<RatingsPlayers />} />
        {/* /tools stays reachable by URL as a plain index; the nav skips it (§2 amended). */}
        <Route path="/tools" element={<Tools />} />

        {/* Trade Ledger keeps its deep-link param routes (§2). */}
        <Route path="/tools/trade-ledger" element={<TradeLedger />} />
        <Route path="/tools/trade-ledger/trade/:tradeId" element={<TradeLedger />} />
        <Route path="/tools/trade-ledger/:kind/:id" element={<TradeLedger />} />
        <Route path="/tools/draft-value" element={<DraftValueTool />} />
        <Route path="/tools/lineup-lab" element={<LineupLabTool />} />
        <Route path="/tools/contract-grader" element={<ContractGraderTool />} />

        {/* Legacy Studio deep-link redirects (Step 5, A6) — param- and query-preserving.
            React-router ranks by specificity, so the static-segment routes win over the
            :kind/:id and splat patterns. Kept tools redirect to their new homes; removed
            Studio tools (build/fit/roster/offseason/hub) fall to the Tools shelf. */}
        <Route path="/studio/trades/history/trade/:tradeId"
               element={<LegacyRedirect build={(p) => `/tools/trade-ledger/trade/${p.tradeId}`} />} />
        <Route path="/studio/trades/history/:kind/:id"
               element={<LegacyRedirect build={(p) => `/tools/trade-ledger/${p.kind}/${p.id}`} />} />
        <Route path="/studio/trades/history" element={<Navigate replace to="/tools/trade-ledger" />} />
        <Route path="/studio/lineups/lines" element={<Navigate replace to="/tools/lineup-lab" />} />
        <Route path="/studio/contracts" element={<Navigate replace to="/tools/contract-grader" />} />
        <Route path="/studio/draft" element={<Navigate replace to="/tools/draft-value" />} />
        {/* Removed Studio surface (TradeBuilder/TradeFit/RosterBuilder/Offseason/hub) → Tools shelf. */}
        <Route path="/studio/*" element={<Navigate replace to="/tools" />} />
        <Route path="/studio" element={<Navigate replace to="/tools" />} />

        {/* Everything else (removed dashboard surface) → Home. */}
        <Route path="*" element={<Navigate replace to="/" />} />
      </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
