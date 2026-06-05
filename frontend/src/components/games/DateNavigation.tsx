import React from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { formatGameDate } from '../../utils/teams'
import './DateNavigation.css'

interface DateNavigationProps {
  currentDate: Date
  onPreviousDay: () => void
  onNextDay: () => void
  onDateChange: (date: Date) => void
  fallbackMessage?: string
}

function DateNavigation({
  currentDate,
  onPreviousDay,
  onNextDay,
  onDateChange,
  fallbackMessage,
}: DateNavigationProps) {
  const handleDateInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = new Date(e.target.value)
    if (!isNaN(newDate.getTime())) {
      onDateChange(newDate)
    }
  }

  const dateInputValue = currentDate.toISOString().split('T')[0]

  return (
    <div className="date-navigation">
      <div className="date-navigation__container">
        <button
          className="date-navigation__arrow"
          onClick={onPreviousDay}
          aria-label="Previous day"
        >
          <ChevronLeft size={20} />
        </button>

        <div className="date-navigation__date">
          <span className="date-navigation__label">{formatGameDate(dateInputValue)}</span>
          <input
            type="date"
            className="date-navigation__picker"
            value={dateInputValue}
            onChange={handleDateInputChange}
            aria-label="Select date"
          />
        </div>

        <button
          className="date-navigation__arrow"
          onClick={onNextDay}
          aria-label="Next day"
        >
          <ChevronRight size={20} />
        </button>
      </div>

      {fallbackMessage && (
        <div className="date-navigation__message">{fallbackMessage}</div>
      )}
    </div>
  )
}

export default DateNavigation
