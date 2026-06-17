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
 * Team full names mapping.
 */
const TEAM_NAMES: Record<string, string> = {
  ANA: 'Anaheim Ducks',
  ARI: 'Arizona Coyotes',
  BOS: 'Boston Bruins',
  BUF: 'Buffalo Sabres',
  CGY: 'Calgary Flames',
  CAR: 'Carolina Hurricanes',
  CHI: 'Chicago Blackhawks',
  COL: 'Colorado Avalanche',
  CBJ: 'Columbus Blue Jackets',
  DAL: 'Dallas Stars',
  DET: 'Detroit Red Wings',
  EDM: 'Edmonton Oilers',
  FLA: 'Florida Panthers',
  LAK: 'Los Angeles Kings',
  MIN: 'Minnesota Wild',
  MTL: 'Montreal Canadiens',
  NSH: 'Nashville Predators',
  NJD: 'New Jersey Devils',
  NYI: 'New York Islanders',
  NYR: 'New York Rangers',
  OTT: 'Ottawa Senators',
  PHI: 'Philadelphia Flyers',
  PIT: 'Pittsburgh Penguins',
  SEA: 'Seattle Kraken',
  SJS: 'San Jose Sharks',
  STL: 'St. Louis Blues',
  TBL: 'Tampa Bay Lightning',
  TOR: 'Toronto Maple Leafs',
  VAN: 'Vancouver Canucks',
  VGK: 'Vegas Golden Knights',
  WSH: 'Washington Capitals',
  WPG: 'Winnipeg Jets',
}

/**
 * Get team full name from abbreviation.
 */
export function getTeamName(teamAbbrev: string): string {
  return TEAM_NAMES[teamAbbrev] || teamAbbrev
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
  CAR: '#CE1126',
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
/**
 * NHL division alignment (2025-26) for the Teams nav mega-menu. Team ids are the stable
 * franchise ids; names come from getTeamName. Teams are alphabetical within each division.
 */
export interface DivisionTeam { id: number; abbrev: string }
export const DIVISIONS: { name: string; teams: DivisionTeam[] }[] = [
  { name: 'Atlantic', teams: [
    { id: 6, abbrev: 'BOS' }, { id: 7, abbrev: 'BUF' }, { id: 17, abbrev: 'DET' },
    { id: 13, abbrev: 'FLA' }, { id: 8, abbrev: 'MTL' }, { id: 9, abbrev: 'OTT' },
    { id: 14, abbrev: 'TBL' }, { id: 10, abbrev: 'TOR' },
  ] },
  { name: 'Metropolitan', teams: [
    { id: 12, abbrev: 'CAR' }, { id: 29, abbrev: 'CBJ' }, { id: 1, abbrev: 'NJD' },
    { id: 2, abbrev: 'NYI' }, { id: 3, abbrev: 'NYR' }, { id: 4, abbrev: 'PHI' },
    { id: 5, abbrev: 'PIT' }, { id: 15, abbrev: 'WSH' },
  ] },
  { name: 'Central', teams: [
    { id: 16, abbrev: 'CHI' }, { id: 21, abbrev: 'COL' }, { id: 25, abbrev: 'DAL' },
    { id: 30, abbrev: 'MIN' }, { id: 18, abbrev: 'NSH' }, { id: 19, abbrev: 'STL' },
    { id: 68, abbrev: 'UTA' }, { id: 52, abbrev: 'WPG' },
  ] },
  { name: 'Pacific', teams: [
    { id: 24, abbrev: 'ANA' }, { id: 20, abbrev: 'CGY' }, { id: 22, abbrev: 'EDM' },
    { id: 26, abbrev: 'LAK' }, { id: 28, abbrev: 'SJS' }, { id: 55, abbrev: 'SEA' },
    { id: 23, abbrev: 'VAN' }, { id: 54, abbrev: 'VGK' },
  ] },
]

export function getTeamColor(teamAbbrev: string): string {
  return TEAM_COLORS[teamAbbrev] || 'var(--color-accent)'
}

/**
 * Get team color with wash treatment for large background areas.
 * Uses 10% team color mixed with page background for subtle tints.
 */
export function getTeamColorWash(teamAbbrev: string): string {
  const teamColor = getTeamColor(teamAbbrev)
  return `color-mix(in srgb, ${teamColor} 10%, var(--color-bg-base))`
}

/**
 * Get team color with accent treatment for smaller elements.
 * Uses 50% team color mixed with background for muted, readable color.
 */
export function getTeamColorAccent(teamAbbrev: string): string {
  const teamColor = getTeamColor(teamAbbrev)
  return `color-mix(in srgb, ${teamColor} 50%, var(--color-bg-base))`
}

/**
 * Set the --color-team-primary CSS variable on the document root.
 * This allows team-specific colors to be applied throughout the page.
 */
export function setTeamPrimaryColor(teamColor: string): void {
  document.documentElement.style.setProperty('--color-team-primary', teamColor)
}

/**
 * Clear the --color-team-primary CSS variable, resetting to default.
 */
export function clearTeamPrimaryColor(): void {
  document.documentElement.style.setProperty('--color-team-primary', 'var(--color-accent)')
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

/**
 * Get the current NHL season ID in YYYYZZZZ format.
 * Season runs from October to June, so the season year is based on the start year.
 * For example: 2025-26 season = 20252026
 */
export function getCurrentSeasonId(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth() // 0-11

  // NHL season typically starts in October (month 9)
  // If current month is Jan-Sep, we're in the latter half of the season
  const seasonStartYear = month >= 9 ? year : year - 1
  const seasonEndYear = seasonStartYear + 1

  return `${seasonStartYear}${seasonEndYear}`
}

/**
 * Get player headshot URL from NHL assets.
 * Format: https://assets.nhle.com/mugs/nhl/{seasonid}/{teamabbrv}/{playerid}.png
 * Example: https://assets.nhle.com/mugs/nhl/20252026/VGK/8478403.png
 */
export function getPlayerHeadshotUrl(
  playerId: number,
  teamAbbrev: string,
  seasonId?: string
): string {
  const season = seasonId || getCurrentSeasonId()
  return `https://assets.nhle.com/mugs/nhl/${season}/${teamAbbrev}/${playerId}.png`
}
