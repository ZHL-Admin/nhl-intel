import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { ErrorBoundary, SkeletonLoader } from './components/common'
import GamesExplorer from './pages/GamesExplorer'
import GameDetail from './pages/GameDetail'
import Teams from './pages/Teams'
import TeamProfile from './pages/TeamProfile'
import Players from './pages/Players'
import PlayerProfile from './pages/PlayerProfile'
import Rankings from './pages/Rankings'

// Tools routes are lazy-loaded (Phase 5.2): they pull in the line-fit UI only when visited.
const Tools = lazy(() => import('./pages/Tools'))
const LineupLab = lazy(() => import('./pages/LineupLab'))
const TradeFit = lazy(() => import('./pages/TradeFit'))
const TradeBuilder = lazy(() => import('./pages/TradeBuilder'))
// Learn section (lazy): the archetype explainer is the first page.
const ArchetypeExplorer = lazy(() => import('./pages/ArchetypeExplorer'))

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <Suspense fallback={<div style={{ padding: 40 }}><SkeletonLoader /></div>}>
          <Routes>
            <Route path="/" element={<GamesExplorer />} />
            <Route path="/games/:gameId" element={<GameDetail />} />
            <Route path="/rankings" element={<Rankings />} />
            <Route path="/teams" element={<Teams />} />
            <Route path="/teams/:teamId" element={<TeamProfile />} />
            <Route path="/players" element={<Players />} />
            <Route path="/players/:playerId" element={<PlayerProfile />} />
            <Route path="/tools" element={<Tools />} />
            <Route path="/tools/lineup-lab" element={<LineupLab />} />
            <Route path="/tools/trade-fit" element={<TradeFit />} />
            <Route path="/tools/trade-builder" element={<TradeBuilder />} />
            <Route path="/learn/archetypes" element={<ArchetypeExplorer />} />
          </Routes>
        </Suspense>
      </Router>
    </ErrorBoundary>
  )
}

export default App
