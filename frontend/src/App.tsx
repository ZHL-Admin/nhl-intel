import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ErrorBoundary } from './components/common'
import GamesExplorer from './pages/GamesExplorer'
import GameDetail from './pages/GameDetail'
import Teams from './pages/Teams'
import TeamProfile from './pages/TeamProfile'
import Players from './pages/Players'
import PlayerProfile from './pages/PlayerProfile'
import Rankings from './pages/Rankings'

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <Routes>
          <Route path="/" element={<GamesExplorer />} />
          <Route path="/games/:gameId" element={<GameDetail />} />
          <Route path="/rankings" element={<Rankings />} />
          <Route path="/teams" element={<Teams />} />
          <Route path="/teams/:teamId" element={<TeamProfile />} />
          <Route path="/players" element={<Players />} />
          <Route path="/players/:playerId" element={<PlayerProfile />} />
        </Routes>
      </Router>
    </ErrorBoundary>
  )
}

export default App
