/**
 * Shared styled select — a pill button + popover menu matching the app's controls (the
 * season selector / Tools dropdown family). Use where a native <select> would otherwise sit.
 */
import { useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import './Select.css'

export interface SelectOption { value: string; label: string }

export default function Select({ value, options, onChange, ariaLabel }: {
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  ariaLabel?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])
  const current = options.find((o) => o.value === value)
  return (
    <div className="ui-select" ref={ref}>
      <button className="ui-select__btn" onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox" aria-expanded={open} aria-label={ariaLabel}>
        <span className="ui-select__value">{current?.label ?? value}</span>
        <ChevronDown size={15} className={open ? 'ui-select__chev ui-select__chev--open' : 'ui-select__chev'} />
      </button>
      {open && (
        <ul className="ui-select__menu" role="listbox">
          {options.map((o) => (
            <li key={o.value}>
              <button role="option" aria-selected={o.value === value}
                className={`ui-select__opt${o.value === value ? ' ui-select__opt--active' : ''}`}
                onClick={() => { onChange(o.value); setOpen(false) }}>
                {o.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
