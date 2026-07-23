import Shell from '../shell/Shell'
import Placeholder from './Placeholder'

/**
 * Power Ratings (§3.4). One table, all 32 teams, backed by the new GET /ratings
 * endpoint (Step 4). The stamp reads "DATA THROUGH <date>" (data recency from
 * MAX(game_date)), NOT "LAST RUN" — per the owner's correction.
 */
export default function Ratings() {
  return (
    <Shell>
      <Placeholder
        title="Power Ratings"
        step="Step 4 (Ratings)"
        note="Table + GET /ratings endpoint; stamp will read DATA THROUGH <date>."
      />
    </Shell>
  )
}
