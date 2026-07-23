import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

// RINK THEORY rebuild (§2 site map). The old dashboard routes are archived on the
// `legacy-dashboard` branch/tag; this is the whole public surface now.
import Home from './rink/pages/Home'
import NotesIndex from './rink/pages/NotesIndex'
import Note from './rink/pages/Note'
import Ratings from './rink/pages/Ratings'
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
        <Route path="/tools" element={<Tools />} />

        {/* Trade Ledger keeps its deep-link param routes (§2). */}
        <Route path="/tools/trade-ledger" element={<TradeLedger />} />
        <Route path="/tools/trade-ledger/trade/:tradeId" element={<TradeLedger />} />
        <Route path="/tools/trade-ledger/:kind/:id" element={<TradeLedger />} />
        <Route path="/tools/draft-value" element={<DraftValueTool />} />
        <Route path="/tools/lineup-lab" element={<LineupLabTool />} />
        <Route path="/tools/contract-grader" element={<ContractGraderTool />} />

        {/* Legacy tool-home redirects (old Studio paths → new tool routes). */}
        <Route path="/studio/trades/history" element={<Navigate replace to="/tools/trade-ledger" />} />
        <Route path="/studio/lineups/lines" element={<Navigate replace to="/tools/lineup-lab" />} />
        <Route path="/studio/contracts" element={<Navigate replace to="/tools/contract-grader" />} />
        <Route path="/studio/draft" element={<Navigate replace to="/tools/draft-value" />} />

        {/* Everything else (removed dashboard surface) → Home. */}
        <Route path="*" element={<Navigate replace to="/" />} />
      </Routes>
    </BrowserRouter>
  )
}
