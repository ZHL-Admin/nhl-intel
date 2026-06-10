import React from 'react'
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react'
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
    // Adding T00:00:00 ensures the date doesn't shift backwards due to timezone offsets
    const newDate = new Date(e.target.value + 'T00:00:00')
    if (!isNaN(newDate.getTime())) {
      onDateChange(newDate)
    }
  }

  const dateInputValue = currentDate.toISOString().split('T')[0]

  // Generates an array of 7 days centered on the currentDate
  const getVisibleDays = () => {
    const days = []
    for (let i = -3; i <= 3; i++) {
      const d = new Date(currentDate)
      d.setDate(d.getDate() + i)
      days.push(d)
    }
    return days
  }

  const visibleDays = getVisibleDays()

  return (
    <div className="date-navigation">
      <div className="date-navigation__container">
        
        <button
          className="date-navigation__arrow"
          onClick={onPreviousDay}
          aria-label="Previous day"
        >
          <ChevronLeft size={24} />
        </button>

        <div className="date-navigation__days">
          {visibleDays.map((date) => {
            // Check if this iteration matches the currently selected date
            const isCurrent = date.toDateString() === currentDate.toDateString()
            
            return (
              <button
                key={date.toISOString()}
                className={`date-navigation__day ${isCurrent ? 'is-active' : ''}`}
                onClick={() => onDateChange(date)}
              >
                <span className="date-navigation__day-name">
                  {date.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase()}
                </span>
                <span className="date-navigation__day-date">
                  {date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()}
                </span>
              </button>
            )
          })}
        </div>

        <button
          className="date-navigation__arrow"
          onClick={onNextDay}
          aria-label="Next day"
        >
          <ChevronRight size={24} />
        </button>

        <div className="date-navigation__picker-wrapper">
          <Calendar size={24} className="date-navigation__calendar-icon" />
          <input
            type="date"
            className="date-navigation__picker"
            value={dateInputValue}
            onChange={handleDateInputChange}
            aria-label="Select date"
          />
        </div>

      </div>

      {fallbackMessage && (
        <div className="date-navigation__message">{fallbackMessage}</div>
      )}
    </div>
  )
}

export default DateNavigation