import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { PageLayout, PageHeader } from '../components/common';
import DateStrip from '../components/common/DateStrip';
import GameRow from '../components/games/GameRow';
import { getGameDates, getGamesByDate } from '../api/games';
import { GameDate as GameDateType, Game } from '../api/types';
import { formatDateForAPI } from '../utils/teams';
import { usePageTitle } from '../hooks/usePageTitle';
import './GamesExplorer.css';

// §01: status groups read as eyebrow dividers, not boxes.
const GROUP_LABEL: Record<string, string> = { live: 'In progress', upcoming: 'Tonight', final: 'Final' };

function GamesExplorer() {
  const [gameDates, setGameDates] = useState<GameDateType[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [todayDate, setTodayDate] = useState<string>('');
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [datesLoading, setDatesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  usePageTitle('Games');

  useEffect(() => {
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

      // Set initial selected date: today if games exist, otherwise the most recent
      // game date. Dates come back in ascending order, so the last entry is newest.
      const todayHasGames = dates.some(d => d.date === today);
      const initialDate = todayHasGames ? today : dates[dates.length - 1].date;
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

  // Shift a YYYY-MM-DD string by N days using local date parts (tz-safe)
  const offsetDate = (dateStr: string, days: number): string => {
    const [y, m, d] = dateStr.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    dt.setDate(dt.getDate() + days);
    return formatDateForAPI(dt);
  };

  const closestDate = (list: GameDateType[], target: string): string => {
    const t = new Date(target).getTime();
    return list.reduce((best, cur) =>
      Math.abs(new Date(cur.date).getTime() - t) < Math.abs(new Date(best.date).getTime() - t)
        ? cur : best
    ).date;
  };

  // Calendar picker: load the slate of game dates around any chosen date so the user
  // can jump to arbitrary periods (e.g. weeks/months/seasons back), not just the
  // default window. Selects the exact date if it had games, else the nearest one.
  const handlePickDate = async (date: string) => {
    try {
      const newDates = await getGameDates(offsetDate(date, -45), offsetDate(date, 15));
      if (newDates.length === 0) {
        setError(`No games found near ${date}`);
        return;
      }
      setError(null);
      setGameDates(newDates);
      const exact = newDates.find(d => d.date === date);
      setSelectedDate(exact ? date : closestDate(newDates, date));
    } catch (err) {
      console.error('Error loading games for picked date:', err);
      setError('Failed to load games for that date');
    }
  };

  // Status-grouped sections (§01): live first, then tonight, then final.
  const sections: { key: string; games: Game[] }[] = [
    { key: 'live', games: games.filter(g => g.is_live) },
    { key: 'upcoming', games: games.filter(g => g.is_preview && !g.is_live) },
    { key: 'final', games: games.filter(g => !g.is_preview && !g.is_live) },
  ].filter(s => s.games.length > 0);

  // Sheet header: the serif human date is the page title (the signature moment).
  const humanDate = selectedDate
    ? new Date(`${selectedDate}T00:00:00`).toLocaleDateString('en-US', {
        weekday: 'long', month: 'long', day: 'numeric',
      })
    : 'Games';
  const liveCount = games.filter(g => g.is_live).length;
  const dek = datesLoading
    ? 'Loading the slate…'
    : games.length === 0
      ? 'No games on this date.'
      : `${games.length} game${games.length > 1 ? 's' : ''}${liveCount ? ` · ${liveCount} live now` : ''}`;

  return (
    <PageLayout>
      <PageHeader
        eyebrow="Games"
        title={humanDate}
        subtitle={dek}
      >
        {!datesLoading && (
          <DateStrip
            dates={gameDates}
            selectedDate={selectedDate}
            onDateChange={handleDateChange}
            onPickDate={handlePickDate}
            todayDate={todayDate}
          />
        )}
      </PageHeader>

      {error && (
        <div className="error-state">
          <p className="error-state__msg">{error}</p>
          <div className="error-state__action">
            <button className="btn btn--secondary" onClick={() => fetchGames(selectedDate)}>Retry</button>
          </div>
        </div>
      )}

      {loading && !error && (
        <div className="games-explorer__rows">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="game-row-skeleton skeleton" />
          ))}
        </div>
      )}

      {!loading && !error && games.length === 0 && (
        <div className="empty-state">
          <p className="empty-state__line">No games on this date. The board wakes up at puck drop.</p>
          <div className="empty-state__action">
            <Link to="/" className="btn btn--quiet">Back to Today →</Link>
          </div>
        </div>
      )}

      {!loading && !error && games.length > 0 && (
        <div className="games-explorer__sections">
          {sections.map((s) => (
            <section key={s.key} className="games-explorer__section">
              <h2 className="games-explorer__group">{GROUP_LABEL[s.key]}</h2>
              <div className="games-explorer__rows">
                {s.games.map((game) => <GameRow key={game.game_id} game={game} />)}
              </div>
            </section>
          ))}
        </div>
      )}
    </PageLayout>
  );
}

export default GamesExplorer;
