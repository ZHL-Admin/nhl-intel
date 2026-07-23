import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

// RINK THEORY rebuild (§2 site map). The old dashboard routes are archived on the
// `legacy-dashboard` branch/tag; this is the whole public surface now.
import Home from './rink/pages/Home'
import NotesIndex from './rink/pages/NotesIndex'
import Note from './rink/pages/Note'
import Ratings from './rink/pages/Ratings'
import RatingsPlayers from './rink/pages/RatingsPlayers'
import Tools from './rink/pages/Tools'
import TradeLedger from './rink/pages/tools/TradeLedger'
import DraftValueTool from './rink/pages/tools/DraftValueTool'
import LineupLabTool from './rink/pages/tools/LineupLabTool'
import ContractGraderTool from './rink/pages/tools/ContractGraderTool'

export default function App() {
  return (
    <BrowserRouter>
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

        {/* Old-path redirects (Studio/tools deep links → new homes) are owned by
            the tool-port step (Step 5), where they can be done comprehensively and
            with param preservation. Until then the catch-all lands old URLs on Home. */}
        <Route path="*" element={<Navigate replace to="/" />} />
      </Routes>
    </BrowserRouter>
  )
}
