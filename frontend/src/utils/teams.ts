/**
 * Team utilities for logos and colors.
 */

/**
 * Get the NHL team logo URL.
 */
export function getTeamLogoUrl(teamAbbrev: string): string {
  return `https://assets.nhle.com/logos/nhl/svg/${teamAbbrev}_light.svg`
}

/**
 * Team primary colors for visualizations.
 * Using standard NHL team colors.
 */
const TEAM_COLORS: Record<string, string> = {
  ANA: '#F47A38',
  ARI: '#8C2633',
  BOS: '#FFB81C',
  BUF: '#002654',
  CGY: '#C8102E',
  CAR: '#CC0000',
  CHI: '#CF0A2C',
  COL: '#6F263D',
  CBJ: '#002654',
  DAL: '#006847',
  DET: '#CE1126',
  EDM: '#041E42',
  FLA: '#041E42',
  LAK: '#111111',
  MIN: '#154734',
  MTL: '#AF1E2D',
  NSH: '#FFB81C',
  NJD: '#CE1126',
  NYI: '#00539B',
  NYR: '#0038A8',
  OTT: '#C52032',
  PHI: '#F74902',
  PIT: '#000000',
  SEA: '#001628',
  SJS: '#006D75',
  STL: '#002F87',
  TBL: '#002868',
  TOR: '#00205B',
  VAN: '#00205B',
  VGK: '#B4975A',
  WSH: '#041E42',
  WPG: '#041E42',
}

/**
 * Get team primary color.
 * Falls back to accent color if team not found.
 */
export function getTeamColor(teamAbbrev: string): string {
  return TEAM_COLORS[teamAbbrev] || 'var(--color-accent)'
}

/**
 * Format date to display string.
 */
export function formatGameDate(dateString: string): string {
  const date = new Date(dateString)
  const options: Intl.DateTimeFormatOptions = {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  }
  return date.toLocaleDateString('en-US', options)
}

/**
 * Format date to API format (YYYY-MM-DD).
 */
export function formatDateForAPI(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Get today's date at midnight local time.
 */
export function getTodayDate(): Date {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return today
}
