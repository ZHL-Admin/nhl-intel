/**
 * Theme management utilities for light/dark mode switching.
 */

const THEME_KEY = 'nhl-intel-theme';

export type Theme = 'light' | 'dark';

export function getTheme(): Theme {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === 'light' || stored === 'dark') return stored;
  // Default to light theme
  return 'light';
}

export function setTheme(theme: Theme): void {
  localStorage.setItem(THEME_KEY, theme);
  document.documentElement.setAttribute('data-theme', theme === 'dark' ? 'dark' : '');
}

export function toggleTheme(): Theme {
  const current = getTheme();
  const next = current === 'light' ? 'dark' : 'light';
  setTheme(next);
  return next;
}

export function initTheme(): void {
  // Apply stored theme on page load before first render to prevent flash
  const theme = getTheme();
  document.documentElement.setAttribute('data-theme', theme === 'dark' ? 'dark' : '');
}
