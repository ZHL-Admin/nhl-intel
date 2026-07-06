import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { ErrorBoundary, SkeletonLoader } from './components/common'
import BottomTabBar from './components/common/BottomTabBar'
import Today from './pages/Today'
import GamesExplorer from './pages/GamesExplorer'
import AssessmentBandDemo from './pages/AssessmentBandDemo'
import PlayersIndexDemo from './pages/PlayersIndexDemo'
import GameDetail from './pages/GameDetail'
import Teams from './pages/Teams'
import TeamProfile from './pages/TeamProfile'
import Players from './pages/Players'
import PlayerProfile from './pages/PlayerProfile'
import PlayerCompare from './pages/PlayerCompare'
import StudioShell from './components/studio/StudioShell'
import LegacyToolsRedirect from './components/studio/LegacyToolsRedirect'

// Studio (P3) — the hub + tool pages are lazy-loaded: they pull in the tool UIs only when visited.
const StudioHub = lazy(() => import('./pages/StudioHub'))
const Offseason = lazy(() => import('./pages/Offseason'))
const LineupLab = lazy(() => import('./pages/LineupLab'))
const TradeFit = lazy(() => import('./pages/TradeFit'))
const TradeBuilder = lazy(() => import('./pages/TradeBuilder'))
const ContractGrader = lazy(() => import('./pages/ContractGrader'))
const RosterBuilder = lazy(() => import('./pages/RosterBuilder'))
const DraftValue = lazy(() => import('./pages/DraftValue'))
const TradeOutcomes = lazy(() => import('./pages/TradeOutcomes'))
// Learn section (lazy). Methods/Writing pull in react-markdown, so they stay in their own chunks.
const Learn = lazy(() => import('./pages/Learn'))
const Methods = lazy(() => import('./pages/Methods'))
const Writing = lazy(() => import('./pages/Writing'))
const ArchetypeExplorer = lazy(() => import('./pages/ArchetypeExplorer'))
// DS2 acceptance surface: the component gallery, mounted only in dev builds.
const DevComponents = lazy(() => import('./pages/DevComponents'))
// Playoff bracket predictor (lazy): pulls scipy-shaped odds only when visited.
const Playoffs = lazy(() => import('./pages/Playoffs'))

const TRADES_TABS = [
  { label: 'Build Trade', to: '/studio/trades/build' },
  { label: 'Player Fit', to: '/studio/trades/fit' },
  { label: 'Trade History', to: '/studio/trades/history' },
]
const LINEUPS_TABS = [
  { label: 'Line Builder', to: '/studio/lineups/lines' },
  { label: 'Team Builder', to: '/studio/lineups/roster' },
]

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <Suspense fallback={<div style={{ padding: 40 }}><SkeletonLoader /></div>}>
          <Routes>
            {/* P1 flip: / is now Today; the games list lives at /games. */}
            <Route path="/" element={<Today />} />
            <Route path="/games" element={<GamesExplorer />} />
            <Route path="/demo/assessment" element={<AssessmentBandDemo />} />
            <Route path="/demo/index" element={<PlayersIndexDemo />} />
            <Route path="/games/:gameId" element={<GameDetail />} />
            {/* P2: Rankings absorbed into Teams. Preserve deep links. */}
            <Route path="/rankings" element={<Navigate replace to="/teams?view=power" />} />
            <Route path="/playoffs" element={<Playoffs />} />
            <Route path="/teams" element={<Teams />} />
            <Route path="/teams/:teamId" element={<TeamProfile />} />
            <Route path="/players" element={<Players />} />
            {/* B2: player compare (2.5.1) — static segment before :playerId. */}
            <Route path="/players/compare" element={<PlayerCompare />} />
            <Route path="/players/:playerId" element={<PlayerProfile />} />
            {/* P3: Studio consolidation. Three areas are shells (mode tabs over existing pages);
                contracts/draft/offseason are direct. Every old /tools/* URL redirects below. */}
            <Route path="/studio" element={<StudioHub />} />
            <Route path="/studio/trades" element={<StudioShell area="Trades" tabs={TRADES_TABS} />}>
              <Route index element={<Navigate replace to="/studio/trades/build" />} />
              <Route path="build" element={<TradeBuilder />} />
              <Route path="fit" element={<TradeFit />} />
              <Route path="history" element={<TradeOutcomes />} />
              <Route path="history/trade/:tradeId" element={<TradeOutcomes />} />
              <Route path="history/:kind/:id" element={<TradeOutcomes />} />
            </Route>
            <Route path="/studio/lineups" element={<StudioShell area="Lineups" tabs={LINEUPS_TABS} />}>
              <Route index element={<Navigate replace to="/studio/lineups/lines" />} />
              <Route path="lines" element={<LineupLab />} />
              <Route path="roster" element={<RosterBuilder />} />
            </Route>
            <Route path="/studio/contracts" element={<ContractGrader />} />
            <Route path="/studio/draft" element={<DraftValue />} />
            <Route path="/studio/offseason" element={<Offseason />} />
            {/* Legacy tool URLs → new Studio homes (path tail + query preserved). */}
            <Route path="/tools" element={<LegacyToolsRedirect />} />
            <Route path="/tools/*" element={<LegacyToolsRedirect />} />
            {/* P4: Learn — hub + methods library + writing (markdown rendered on-site). */}
            <Route path="/learn" element={<Learn />} />
            <Route path="/learn/archetypes" element={<ArchetypeExplorer />} />
            <Route path="/learn/methods" element={<Methods />} />
            <Route path="/learn/methods/:slug" element={<Methods />} />
            <Route path="/learn/writing" element={<Writing />} />
            <Route path="/learn/writing/:slug" element={<Writing />} />
            {import.meta.env.DEV && <Route path="/dev/components" element={<DevComponents />} />}
          </Routes>
        </Suspense>
        <BottomTabBar />
      </Router>
    </ErrorBoundary>
  )
}

export default App
