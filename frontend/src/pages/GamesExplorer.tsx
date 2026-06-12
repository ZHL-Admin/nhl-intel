import { useState, useEffect } from 'react';
import { PageLayout } from '../components/common';
import DateStrip from '../components/common/DateStrip';
import GameOfTheNight from '../components/games/GameOfTheNight';
import GameCard from '../components/games/GameCard';
import GameCardSkeleton from '../components/games/GameCardSkeleton';
import { getGameDates, getGamesByDate } from '../api/games';
import { GameDate as GameDateType, Game } from '../api/types';
import { formatDateForAPI } from '../utils/teams';
import './GamesExplorer.css';

function GamesExplorer() {
  const [gameDates, setGameDates] = useState<GameDateType[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [todayDate, setTodayDate] = useState<string>('');
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [datesLoading, setDatesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = 'NHL Intel - Games';
    initializeDates();
  }, []);

  useEffect(() => {
    if (selectedDate) {
      fetchGames(selectedDate);
    }
  }, [selectedDate]);

  const initializeDates = async () => {
    setDatesLoading(true);
    const today = formatDateForAPI(new Date());
    setTodayDate(today);

    try {
      const dates = await getGameDates();

      if (dates.length === 0) {
        setError('No games found in the date range');
        setDatesLoading(false);
        return;
      }

      setGameDates(dates);

      // Set initial selected date: today if games exist, otherwise most recent
      const todayHasGames = dates.some(d => d.date === today);
      const initialDate = todayHasGames ? today : dates[0].date;
      setSelectedDate(initialDate);

    } catch (err) {
      console.error('Error fetching game dates:', err);
      setError('Failed to load game schedule');
    } finally {
      setDatesLoading(false);
    }
  };

  const fetchGames = async (date: string) => {
    setLoading(true);
    setError(null);

    try {
      const data = await getGamesByDate(date);

      // If no games on selected date (shouldn't happen with DateStrip disabled dates)
      // auto-redirect to nearest game date
      if (data.length === 0 && gameDates.length > 0) {
        const nearestDate = findNearestGameDate(date);
        if (nearestDate && nearestDate !== date) {
          setSelectedDate(nearestDate);
          return;
        }
      }

      setGames(data);
    } catch (err) {
      console.error('Error fetching games:', err);
      setError('Failed to load games');
      setGames([]);
    } finally {
      setLoading(false);
    }
  };

  const findNearestGameDate = (targetDate: string): string | null => {
    if (gameDates.length === 0) return null;

    const target = new Date(targetDate);

    // Search backward first
    for (let i = 0; i < gameDates.length; i++) {
      const gameDate = new Date(gameDates[i].date);
      if (gameDate < target) {
        return gameDates[i].date;
      }
    }

    // Search forward
    for (let i = gameDates.length - 1; i >= 0; i--) {
      const gameDate = new Date(gameDates[i].date);
      if (gameDate > target) {
        return gameDates[i].date;
      }
    }

    return gameDates[0]?.date || null;
  };

  const handleDateChange = (date: string) => {
    setSelectedDate(date);
  };

  // Sort games: Live → Final → Upcoming
  const sortedGames = [...games].sort((a, b) => {
    if (a.is_live && !b.is_live) return -1;
    if (!a.is_live && b.is_live) return 1;
    if (!a.is_preview && b.is_preview) return -1;
    if (a.is_preview && !b.is_preview) return 1;
    return 0;
  });

  // Select Game of the Night (for completed games)
  const selectGameOfTheNight = (): Game | null => {
    const completedGames = games.filter(g => !g.is_preview && !g.is_live);

    // No completed games - no featured game
    if (completedGames.length === 0) return null;

    // Single game on the date - always feature it
    if (completedGames.length === 1) return completedGames[0];

    // Multiple games - select based on heuristic
    // Priority: OT/SO games, then highest combined score
    const hasOT = completedGames.find(g => g.period && g.period.includes('OT'));
    if (hasOT) return hasOT;

    // Return the game with the highest combined score
    return completedGames.reduce((best, current) => {
      const bestTotal = (best.home_score || 0) + (best.away_score || 0);
      const currentTotal = (current.home_score || 0) + (current.away_score || 0);
      return currentTotal > bestTotal ? current : best;
    }, completedGames[0]);
  };

  const gameOfTheNight = selectGameOfTheNight();

  // Filter out Game of the Night from the regular grid
  const gridGames = gameOfTheNight
    ? sortedGames.filter(g => g.game_id !== gameOfTheNight.game_id)
    : sortedGames;

  if (datesLoading) {
    return (
      <PageLayout>
        <div style={{ padding: 'var(--space-8)', maxWidth: '1280px', margin: '0 auto' }}>
          <div style={{ height: '44px', background: 'var(--color-bg-elevated)', borderRadius: 'var(--radius-lg)', marginBottom: 'var(--space-6)' }} />
          <div className="games-explorer__grid">
            {[1, 2, 3].map((i) => (
              <GameCardSkeleton key={i} />
            ))}
          </div>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <DateStrip
          dates={gameDates}
          selectedDate={selectedDate}
          onDateChange={handleDateChange}
          todayDate={todayDate}
        />
      </div>

      <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 var(--space-8)' }}>
        {error && (
          <div className="games-explorer__error">
            <p className="games-explorer__error-message">{error}</p>
            <button
              className="games-explorer__retry-button"
              onClick={() => fetchGames(selectedDate)}
            >
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

        {!loading && !error && games.length > 0 && (
          <>
            {gameOfTheNight && <GameOfTheNight game={gameOfTheNight} />}

            <div className="games-explorer__grid">
              {gridGames.map((game) => (
                <GameCard key={game.game_id} game={game} />
              ))}
            </div>
          </>
        )}
      </div>
    </PageLayout>
  );
}

export default GamesExplorer;
