import { useEffect, useRef } from 'react';
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react';
import './DateStrip.css';

export interface GameDate {
  date: string;
  gameCount: number;
  label?: string;
}

interface DateStripProps {
  dates: GameDate[];
  selectedDate: string;
  onDateChange: (date: string) => void;
  todayDate: string;
}

export default function DateStrip({
  dates,
  selectedDate,
  onDateChange,
  todayDate
}: DateStripProps) {
  const selectedDateRef = useRef<HTMLButtonElement>(null);

  // Auto-scroll to keep selected date centered
  useEffect(() => {
    if (selectedDateRef.current) {
      selectedDateRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
        inline: 'center'
      });
    }
  }, [selectedDate]);

  const formatDateLabel = (dateStr: string): string => {
    const date = new Date(dateStr);
    const weekday = date.toLocaleDateString('en-US', { weekday: 'short' });
    const month = date.toLocaleDateString('en-US', { month: 'short' });
    const day = date.getDate();
    return `${weekday} · ${month} ${day}`;
  };

  const pageLeft = () => {
    const currentIndex = dates.findIndex(d => d.date === selectedDate);
    if (currentIndex > 0) {
      onDateChange(dates[currentIndex - 1].date);
    }
  };

  const pageRight = () => {
    const currentIndex = dates.findIndex(d => d.date === selectedDate);
    if (currentIndex < dates.length - 1) {
      onDateChange(dates[currentIndex + 1].date);
    }
  };

  const showTodayButton = selectedDate !== todayDate && dates.some(d => d.date === todayDate);

  return (
    <div className="date-strip">
      <button
        className="date-strip__arrow"
        onClick={pageLeft}
        disabled={dates.findIndex(d => d.date === selectedDate) === 0}
      >
        <ChevronLeft size={20} />
      </button>

      <div className="date-strip__dates">
        {dates.map(date => (
          <button
            key={date.date}
            ref={selectedDate === date.date ? selectedDateRef : null}
            className={`date-strip__pill ${selectedDate === date.date ? 'date-strip__pill--selected' : ''}`}
            onClick={() => onDateChange(date.date)}
          >
            <span className="date-strip__pill-label">{formatDateLabel(date.date)}</span>
            {date.gameCount > 1 && (
              <span className="date-strip__pill-count">{date.gameCount}</span>
            )}
            {date.label && (
              <span className="date-strip__pill-badge">{date.label}</span>
            )}
          </button>
        ))}
      </div>

      <button
        className="date-strip__arrow"
        onClick={pageRight}
        disabled={dates.findIndex(d => d.date === selectedDate) === dates.length - 1}
      >
        <ChevronRight size={20} />
      </button>

      <button className="date-strip__calendar">
        <Calendar size={18} />
      </button>

      {showTodayButton && (
        <button
          className="date-strip__today"
          onClick={() => onDateChange(todayDate)}
        >
          Today
        </button>
      )}
    </div>
  );
}
