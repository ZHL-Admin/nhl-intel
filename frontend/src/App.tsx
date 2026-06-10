import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ErrorBoundary } from './components/common'
import GamesExplorer from './pages/GamesExplorer'
import GameDetail from './pages/GameDetail'
import TeamProfile from './pages/TeamProfile'
import PlayerProfile from './pages/PlayerProfile'
import DevComponents from './pages/DevComponents'

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <Routes>
          <Route path="/" element={<GamesExplorer />} />
          <Route path="/games/:gameId" element={<GameDetail />} />
          <Route path="/teams/:teamId" element={<TeamProfile />} />
          <Route path="/players/:playerId" element={<PlayerProfile />} />
          {import.meta.env.DEV && (
            <Route path="/dev/components" element={<DevComponents />} />
          )}
        </Routes>
      </Router>
    </ErrorBoundary>
  )
}

export default App
