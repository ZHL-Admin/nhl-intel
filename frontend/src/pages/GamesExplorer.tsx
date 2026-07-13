import { useState, useEffect, useMemo, ReactNode } from 'react';
import { PageLayout } from '../components/common';
import DateStrip from '../components/common/DateStrip';
import GameRow from '../components/games/GameRow';
import UpcomingRow from '../components/games/UpcomingRow';
import FeaturedGame from '../components/games/FeaturedGame';
import RecentResults from '../components/games/RecentResults';
import { getGameDates, getGamesByDate } from '../api/games';
import { GameDate as GameDateType, Game } from '../api/types';
import { formatDateForAPI } from '../utils/teams';
import { usePageTitle } from '../hooks/usePageTitle';
import './GamesExplorer.css';

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

      // Land on today if it has games; otherwise the most recent played slate (deep-offseason
      // default, §2 — never an empty today). Dates come back ascending, so the last is newest.
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
      setGames(data);
    } catch (err) {
      console.error('Error fetching games:', err);
      setError('Failed to load games');
      setGames([]);
    } finally {
      setLoading(false);
    }
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

  // Calendar picker: load the slate of game dates around any chosen date so the user can jump to
  // arbitrary periods, not just the default window. Selects the exact date if it had games, else
  // the nearest one.
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

  // Jump to the most recent played slate (Full schedule / empty-state fallback).
  const goToMostRecent = () => {
    if (gameDates.length === 0) return;
    const prior = gameDates.map(d => d.date).filter(d => d <= todayDate);
    const target = (prior.length ? prior : gameDates.map(d => d.date))
      .sort((a, b) => (a < b ? 1 : -1))[0];
    if (target) setSelectedDate(target);
  };

  // Slate partition (§3/§4): live, then finals, then upcoming.
  const live = useMemo(() => games.filter(g => g.is_live), [games]);
  const finals = useMemo(() => games.filter(g => !g.is_preview && !g.is_live), [games]);
  const upcoming = useMemo(() => games.filter(g => g.is_preview && !g.is_live), [games]);

  const byTime = (a: Game, b: Game) => (a.game_time || '').localeCompare(b.game_time || '');
  const liveSorted = [...live].sort(byTime);
  const upcomingSorted = [...upcoming].sort(byTime);
  // Finals by end time descending — proxied by game_id descending (no end-time field on the list).
  const finalsSorted = [...finals].sort((a, b) => b.game_id - a.game_id);

  const n = games.length;
  const dense = n >= 4;

  // Masthead title: the selected date as a serif line ("Tuesday, January 12").
  const humanDate = selectedDate
    ? new Date(`${selectedDate}T00:00:00`).toLocaleDateString('en-US', {
        weekday: 'long', month: 'long', day: 'numeric',
      })
    : 'Games';

  // Empty-state pointer to the nearest real slate (§3).
  const nextSlate = useMemo(() => {
    if (n !== 0 || gameDates.length === 0) return null;
    const dates = gameDates.map(d => d.date);
    const after = dates.filter(d => d > selectedDate).sort()[0];
    const before = dates.filter(d => d < selectedDate).sort((a, b) => (a < b ? 1 : -1))[0];
    const target = after || before;
    if (!target) return null;
    const label = new Date(`${target}T00:00:00`).toLocaleDateString('en-US', {
      weekday: 'short', month: 'short', day: 'numeric',
    });
    return { date: target, label: `${after ? 'Next slate' : 'Most recent'}: ${label}` };
  }, [n, gameDates, selectedDate]);

  const skeletonHeights = [56, 56, 56, 56, 56];

  return (
    <PageLayout>
      <div className="games-fade" key={selectedDate}>
        {/* Masthead (§1): one row — serif date title left, date strip right. */}
        <header className="games-masthead">
          <h1 className="games-masthead__title">{humanDate}</h1>
          {!datesLoading && (
            <div className="games-masthead__strip">
              <DateStrip
                dates={gameDates}
                selectedDate={selectedDate}
                onDateChange={handleDateChange}
                onPickDate={handlePickDate}
                todayDate={todayDate}
              />
            </div>
          )}
        </header>

        {error && (
          <div className="error-state">
            <p className="error-state__msg">{error}</p>
            <div className="error-state__action">
              <button className="btn btn--secondary" onClick={() => fetchGames(selectedDate)}>Retry</button>
            </div>
          </div>
        )}

        {loading && !error && (
          <div className="games-rows">
            {skeletonHeights.map((h, i) => (
              <div key={i} className="skeleton games-skeleton" style={{ height: h }} />
            ))}
          </div>
        )}

        {!loading && !error && (
          <>
            {/* Dense list (§4): three sections, anatomy A for scored, anatomy B for upcoming. */}
            {dense && (
              <div className="games-sections">
                {liveSorted.length > 0 && (
                  <Section eyebrow="In progress" count={liveSorted.length} live first>
                    {liveSorted.map(g => <GameRow key={g.game_id} game={g} />)}
                  </Section>
                )}
                {finalsSorted.length > 0 && (
                  <Section eyebrow="Final" count={finalsSorted.length} first={liveSorted.length === 0}>
                    {finalsSorted.map(g => <GameRow key={g.game_id} game={g} />)}
                  </Section>
                )}
                {upcomingSorted.length > 0 && (
                  <Section eyebrow="Tonight" count={upcomingSorted.length}
                    first={liveSorted.length === 0 && finalsSorted.length === 0}>
                    {upcomingSorted.map(g => <UpcomingRow key={g.game_id} game={g} />)}
                  </Section>
                )}
              </div>
            )}

            {/* Featured treatment (§5): 1-3 games. Scored games keep anatomy A; upcoming become
                featured tiles. */}
            {!dense && n > 0 && (
              <div className="games-sections">
                {liveSorted.length > 0 && (
                  <Section eyebrow="In progress" count={liveSorted.length} live first>
                    {liveSorted.map(g => <GameRow key={g.game_id} game={g} />)}
                  </Section>
                )}
                {finalsSorted.length > 0 && (
                  <Section eyebrow="Final" count={finalsSorted.length} first={liveSorted.length === 0}>
                    {finalsSorted.map(g => <GameRow key={g.game_id} game={g} />)}
                  </Section>
                )}
                {upcomingSorted.length > 0 && (
                  <Section eyebrow="Tonight" count={upcomingSorted.length}
                    first={liveSorted.length === 0 && finalsSorted.length === 0}>
                    {upcomingSorted.map(g => <FeaturedGame key={g.game_id} game={g} />)}
                  </Section>
                )}
              </div>
            )}

            {/* Empty slate (§3). */}
            {n === 0 && (
              <div className="games-empty">
                <p className="games-empty__line">No games today.</p>
                {nextSlate && (
                  <button type="button" className="games-empty__link"
                    onClick={() => setSelectedDate(nextSlate.date)}>
                    {nextSlate.label}
                  </button>
                )}
              </div>
            )}

            {/* Recent results backfill (§6): sparse and empty slates only. */}
            {n <= 3 && (
              <RecentResults
                gameDates={gameDates}
                selectedDate={selectedDate}
                onFullSchedule={goToMostRecent}
              />
            )}
          </>
        )}
      </div>
    </PageLayout>
  );
}

// A dense-list section: a module-header eyebrow carrying its count, an optional pulsing live dot,
// and a top rule on every section but the first (§4).
function Section({ eyebrow, count, live, first, children }: {
  eyebrow: string; count: number; live?: boolean; first?: boolean; children: ReactNode;
}) {
  return (
    <section className={`games-section ${first ? 'games-section--first' : ''}`}>
      <h2 className="games-section__eyebrow">
        {live && <span className="live-dot" />}
        {eyebrow} <span className="games-section__count num">· {count}</span>
      </h2>
      <div className="games-rows">{children}</div>
    </section>
  );
}

export default GamesExplorer;
