import Shell from '../shell/Shell'
import Placeholder from './Placeholder'

/**
 * Player Ratings (§3.4 sibling, new route /ratings/players).
 *
 * Full table lands with the Ratings step (Step 4). Same editorial treatment as
 * the team table: serif title, "DATA THROUGH <date>" stamp, short intro, ONE
 * table — columns RK, PLAYER, TEAM (dot), POS, VALUE, CONTRACT SURPLUS; at most
 * a position filter.
 *
 * HARD CONSTRAINT: backed entirely by the existing dormant endpoints
 * GET /rankings/talent (VALUE) and GET /rankings/surplus (CONTRACT SURPLUS),
 * read AS-IS. Zero backend changes for this page. If a payload can't support a
 * column, cut the column.
 */
export default function RatingsPlayers() {
  return (
    <Shell>
      <Placeholder
        title="Player Ratings"
        step="Step 4 (Ratings)"
        note="Table from /rankings/talent + /rankings/surplus, read as-is. No backend changes."
      />
    </Shell>
  )
}
