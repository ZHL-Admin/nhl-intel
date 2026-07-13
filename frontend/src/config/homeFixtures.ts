/**
 * Review-only fixtures for the Home page (doc 19). Used ONLY when isFixtureMode() is true (DEV +
 * `?fixtures` in the URL) so the offseason layout — the Lead, the populated Ledger, Still available,
 * the movers/end-of-season rails — can be reviewed before the real feeds exist. Clearly synthetic;
 * never rendered in production. Mirrors the backend stub fixtures in routers/moves.py + free_agents.py.
 */
import type { MoveRow, FreeAgentRow, RosterForecastRow, PowerRatingRow } from '../api/types'

const isoDaysAgo = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export const FIXTURE_MOVES: MoveRow[] = [
  { id: 'fx-1', date: isoDaysAgo(1), type: 'extension', teams: ['OTT'], players: [{ player_id: 8482116, name: 'Tim Stützle', pos: 'C' }], terms: { years: 8, aav: 8_350_000 }, verdict: { grade: 'A-' } },
  { id: 'fx-2', date: isoDaysAgo(1), type: 'trade', teams: ['DET', 'BUF'], players: [{ player_id: 8478406, name: 'JJ Peterka', pos: 'RW' }], verdict: { edge: 'DET', margin: 1.4 } },
  { id: 'fx-3', date: isoDaysAgo(2), type: 'signing', teams: ['LAK'], players: [{ player_id: 8471685, name: 'Nikolaj Ehlers', pos: 'LW' }], terms: { years: 6, aav: 7_000_000 }, verdict: { grade: 'B+' } },
  { id: 'fx-4', date: isoDaysAgo(3), type: 'signing', teams: ['NSH'], players: [{ player_id: 8475791, name: 'Sam Reinhart', pos: 'C' }], terms: { years: 7, aav: 8_600_000 }, verdict: { grade: 'C' } },
  { id: 'fx-5', date: isoDaysAgo(4), type: 'trade', teams: ['MTL', 'CGY'], players: [{ player_id: 8480018, name: 'Noah Dobson', pos: 'D' }], verdict: { edge: 'MTL', margin: 0.6 } },
  { id: 'fx-6', date: isoDaysAgo(4), type: 'signing', teams: ['UTA'], players: [{ player_id: 8477939, name: 'Brock Boeser', pos: 'RW' }], terms: { years: 5, aav: 7_250_000 }, verdict: { grade: 'B' } },
  { id: 'fx-7', date: isoDaysAgo(6), type: 'extension', teams: ['NJD'], players: [{ player_id: 8480002, name: 'Luke Hughes', pos: 'D' }], terms: { years: 7, aav: 9_000_000 }, verdict: { grade: 'A' } },
  // An ungraded signing — the DAG hasn't scored it yet; the Ledger renders a blank verdict cell.
  { id: 'fx-8', date: isoDaysAgo(7), type: 'signing', teams: ['SEA'], players: [{ player_id: 8479580, name: 'Jake Walman', pos: 'D' }], terms: { years: 4, aav: 5_500_000 }, verdict: null },
]

export const FIXTURE_FREE_AGENTS: FreeAgentRow[] = [
  { player_id: 8478550, name: 'Mikko Rantanen', pos: 'RW', age: 28, status: 'UFA', projected_award: { years: 8, aav: 11_500_000 }, projected_war: 3.1, fits: { COL: 'A', CAR: 'A-' } },
  { player_id: 8477500, name: 'Dylan Larkin', pos: 'C', age: 29, status: 'UFA', projected_award: { years: 6, aav: 8_100_000 }, projected_war: 2.4, fits: { DET: 'A-', NYR: 'B' } },
  { player_id: 8471214, name: 'Alex Ovechkin', pos: 'LW', age: 39, status: 'UFA', projected_award: { years: 1, aav: 8_000_000 }, projected_war: 1.9, fits: { WSH: 'A', EDM: 'B+' } },
  { player_id: 8474564, name: 'Steven Stamkos', pos: 'C', age: 35, status: 'UFA', projected_award: { years: 3, aav: 7_100_000 }, projected_war: 1.7, fits: { TBL: 'B', NSH: 'B-' } },
  { player_id: 8480069, name: 'Bowen Byram', pos: 'D', age: 24, status: 'RFA', projected_war: 1.6, fits: { BUF: 'A-', NJD: 'B+' } },
]

// RosterForecastRow has many required fields; a factory keeps the fixtures readable.
const forecast = (
  team_id: number, team_abbrev: string, net_delta_war: number, points_delta: number,
  projected_rank: number, base_rank: number,
): RosterForecastRow => ({
  team_id, team_abbrev, transition: 'offseason',
  base_rating: 0, projected_rating: net_delta_war, delta: net_delta_war,
  band_low: net_delta_war - 1, band_high: net_delta_war + 1, band_goals: 0.3,
  base_points: 92, projected_points: 92 + points_delta,
  points_low: 84 + points_delta, points_high: 100 + points_delta, points_delta,
  net_delta_war, base_rank, projected_rank, projected_rank_delta: base_rank - projected_rank,
  n_moves: 4, negligible: false,
})

export const FIXTURE_OFFSEASON_BOARD: RosterForecastRow[] = [
  forecast(26, 'LAK', 3.4, 7, 1, 9),
  forecast(19, 'STL', 2.6, 5, 6, 12),
  forecast(9, 'OTT', 2.1, 4, 11, 15),
  forecast(2, 'NYI', -1.5, -3, 21, 17),
  forecast(24, 'ANA', -1.8, -4, 24, 20),
  forecast(29, 'CBJ', -2.7, -6, 28, 22),
]

const power = (team_id: number, team_abbrev: string, total_rating: number): PowerRatingRow => ({
  team_id, team_abbrev, season: '20252026', games_played: 82, total_rating,
  play_5v5: total_rating * 0.6, finishing: total_rating * 0.15, goaltending: total_rating * 0.15, special_teams: total_rating * 0.1,
  contrib_play_5v5: total_rating * 0.6, contrib_finishing: total_rating * 0.15, contrib_goaltending: total_rating * 0.15, contrib_special_teams: total_rating * 0.1,
})

export const FIXTURE_POWER: PowerRatingRow[] = [
  power(21, 'COL', 6.9),
  power(6, 'BOS', 6.1),
  power(26, 'LAK', 5.7),
  power(22, 'EDM', 5.2),
  power(13, 'FLA', 4.8),
]
