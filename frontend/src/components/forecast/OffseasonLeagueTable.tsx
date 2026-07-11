import { RosterForecastRow } from '../../api/types'
import { getTeamLogoUrl, getTeamName } from '../../utils/teams'

const fmtWar = (v: number) => (v >= 0 ? '+' : '') + v.toFixed(1)

/**
 * §S2 — the offseason as one diverging chart: 32 rosters balanced on a shared center-zero axis.
 * Each row's net WAR change fills a 3px track from a common center — blue right for improvement,
 * red left for decline — on a single fixed domain so the column reads top-to-bottom as one figure.
 * A faint 1px zero line runs behind every row (the tracks are contiguous, so it reads continuous).
 * The forecast's unsettled portion (uncertainty band → pending/unsigned spots) renders as a dashed
 * extension beyond the solid point estimate, obeying the solid=observed / dashed=projected law.
 */
export default function OffseasonLeagueTable({ rows, onSelect }: {
  rows: RosterForecastRow[]; onSelect: (teamId: number) => void
}) {
  // Ordered by net change so the diverging column reads cleanly from most-improved to most-declined.
  const ordered = [...rows].sort((a, b) => b.net_delta_war - a.net_delta_war)

  // One shared, fixed domain for all 32 bars (symmetric around zero), padded for the dashed band.
  const bandMax = Math.max(1e-6, ...rows.map((r) => r.band_goals ?? 0))
  const domain = Math.max(0.1, ...rows.map((r) => Math.abs(r.net_delta_war))) * 1.12
  // The dashed uncertainty whisker is a visual cue for unresolved roster spots; scale the largest
  // band to ~16% of the half-track so it reads as an extension, not a competing bar.
  const dashScale = (domain * 0.16) / bandMax

  const pct = (v: number) => 50 + (v / domain) * 50 // 0..100 along the track

  return (
    <div className="olb">
      <div className="olb__rows">
        {ordered.map((r, i) => {
          const up = r.net_delta_war >= 0
          const end = pct(r.net_delta_war)
          const fillLeft = up ? 50 : end
          const fillWidth = Math.abs(end - 50)
          const dash = (r.band_goals ?? 0) * dashScale // half-width in track %
          return (
            <div
              key={r.team_id}
              className="olb__row"
              role="button"
              tabIndex={0}
              onClick={() => onSelect(r.team_id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(r.team_id) } }}
            >
              <span className="olb__rank num">{r.projected_rank ?? i + 1}</span>
              <img className="olb__logo" src={getTeamLogoUrl(r.team_abbrev ?? '')} alt="" aria-hidden
                onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
              <span className="olb__name">{getTeamName(r.team_abbrev ?? '')}</span>
              <span className="olb__track">
                {/* dashed extension = unresolved / uncertain portion, centered on the bar end */}
                {dash > 0.4 && (
                  <span
                    className={`olb__dash ${up ? 'is-up' : 'is-down'}`}
                    style={{ left: `${Math.max(0, end - dash)}%`, width: `${Math.min(100, 2 * dash)}%` }}
                  />
                )}
                <span
                  className={`olb__fill ${up ? 'is-up' : 'is-down'}`}
                  style={{ left: `${fillLeft}%`, width: `${fillWidth}%` }}
                />
              </span>
              <span className={`olb__val num ${up ? 'is-up' : 'is-down'}`}>{fmtWar(r.net_delta_war)}</span>
            </div>
          )
        })}
      </div>
      <p className="olb__legend">dashed = unresolved roster spots</p>
    </div>
  )
}
