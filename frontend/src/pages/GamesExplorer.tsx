import { useState, useEffect } from 'react'
import { PageLayout } from '../components/common'
import GameCard from '../components/games/GameCard'
import GameCardSkeleton from '../components/games/GameCardSkeleton'
import DateNavigation from '../components/games/DateNavigation'
import { getGamesByDate } from '../api/games'
import { Game } from '../api/types'
import { getTodayDate, formatDateForAPI, formatGameDate } from '../utils/teams'
import './GamesExplorer.css'

function GamesExplorer() {
  const [currentDate, setCurrentDate] = useState<Date>(getTodayDate())
  const [games, setGames] = useState<Game[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fallbackMessage, setFallbackMessage] = useState<string>('')
  const [isInitialMount, setIsInitialMount] = useState(true)

  useEffect(() => {
    document.title = 'NHL Intel - Games'
  }, [])

  useEffect(() => {
    fetchGames(currentDate, isInitialMount)
    if (isInitialMount) {
      setIsInitialMount(false)
    }
  }, [currentDate])

  const fetchGames = async (date: Date, isInitialLoad = false) => {
    setLoading(true)
    setError(null)
    setFallbackMessage('')

    try {
      const dateStr = formatDateForAPI(date)
      const data = await getGamesByDate(dateStr)

      if (data.length === 0 && isInitialLoad) {
        await findMostRecentGameDate(date)
      } else {
        setGames(data)
      }
    } catch (err) {
      console.error('Error fetching games:', err)
      setError('Failed to load games. Please try again.')
      setGames([])
    } finally {
      setLoading(false)
    }
  }

  const findMostRecentGameDate = async (startDate: Date) => {
    let searchDate = new Date(startDate)
    let attempts = 0
    const maxAttempts = 30

    while (attempts < maxAttempts) {
      searchDate.setDate(searchDate.getDate() - 1)
      attempts++

      try {
        const dateStr = formatDateForAPI(searchDate)
        const data = await getGamesByDate(dateStr)

        if (data.length > 0) {
          setCurrentDate(searchDate)
          setGames(data)
          setFallbackMessage(
            `No games today - showing most recent games (${formatGameDate(dateStr)})`
          )
          return
        }
      } catch (err) {
        console.error('Error searching for games:', err)
      }
    }

    setError('No recent games found')
  }

  const handlePreviousDay = () => {
    const newDate = new Date(currentDate)
    newDate.setDate(newDate.getDate() - 1)
    setCurrentDate(newDate)
  }

  const handleNextDay = () => {
    const newDate = new Date(currentDate)
    newDate.setDate(newDate.getDate() + 1)
    setCurrentDate(newDate)
  }

  const handleDateChange = (date: Date) => {
    setCurrentDate(date)
  }

  const handleRetry = () => {
    fetchGames(currentDate)
  }

  return (
    <PageLayout>
      <DateNavigation
        currentDate={currentDate}
        onPreviousDay={handlePreviousDay}
        onNextDay={handleNextDay}
        onDateChange={handleDateChange}
        fallbackMessage={fallbackMessage}
      />

      {error && (
        <div className="games-explorer__error">
          <p className="games-explorer__error-message">{error}</p>
          <button className="games-explorer__retry-button" onClick={handleRetry}>
            Retry
          </button>
        </div>
      )}

      {loading && !error && (
        <div className="games-explorer__grid">
          {[1, 2, 3].map((i) => (
            <GameCardSkeleton key={i} />
          ))}
        </div>
      )}

      {!loading && !error && games.length === 0 && (
        <div className="games-explorer__empty">
          <p className="games-explorer__empty-message">
            No games scheduled for {formatGameDate(formatDateForAPI(currentDate))}
          </p>
          <p className="games-explorer__empty-hint">
            Use the date navigation above to find games on other dates
          </p>
        </div>
      )}

      {!loading && !error && games.length > 0 && (
        <div className="games-explorer__grid">
          {games.map((game) => (
            <GameCard key={game.game_id} game={game} />
          ))}
        </div>
      )}
    </PageLayout>
  )
}

export default GamesExplorer
