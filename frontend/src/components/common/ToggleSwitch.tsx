import { useCallback, useEffect, useState } from 'react';
import './ToggleSwitch.css';

interface ToggleSwitchProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  /** Optional hover hint (e.g. what the adjustment does). */
  title?: string;
  id?: string;
}

/**
 * Shared on/off switch (Phase 2.3). Used for the "Adjusted" toggle on team trends and
 * stat panels; reusable for any binary view option. Defaults are owned by the caller.
 */
export default function ToggleSwitch({ checked, onChange, label, title, id }: ToggleSwitchProps) {
  return (
    <label className="toggle-switch" title={title} htmlFor={id}>
      <input
        id={id}
        type="checkbox"
        className="toggle-switch__input"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="toggle-switch__track" aria-hidden="true">
        <span className="toggle-switch__thumb" />
      </span>
      <span className="toggle-switch__label">{label}</span>
    </label>
  );
}

/**
 * Persisted "Adjusted" preference (localStorage `nhlintel.adjusted`), default OFF.
 * Persisting in localStorage is fine in this Vite app (it is not a sandboxed artifact).
 */
const ADJUSTED_KEY = 'nhlintel.adjusted';

export function useAdjustedToggle(): [boolean, (next: boolean) => void] {
  const [adjusted, setAdjusted] = useState<boolean>(() => {
    try {
      return localStorage.getItem(ADJUSTED_KEY) === 'true';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(ADJUSTED_KEY, String(adjusted));
    } catch {
      /* ignore storage failures */
    }
  }, [adjusted]);

  const set = useCallback((next: boolean) => setAdjusted(next), []);
  return [adjusted, set];
}
