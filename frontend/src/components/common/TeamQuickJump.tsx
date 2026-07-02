/**
 * TeamQuickJump — the shared 32-team chip row (logo + abbreviation pills). Used by the Trade Outcomes
 * landing and the Trade Builder setup so both pick teams with identical styling. `onPick` receives the
 * team abbreviation; pass `exclude` to hide teams already chosen.
 */
import { DIVISIONS, getTeamColor, getTeamLogoUrl, getTeamName } from '../../utils/teams'
import './TeamQuickJump.css'

const TEAMS = DIVISIONS.flatMap((d) => d.teams).map((t) => t.abbrev).sort()

export default function TeamQuickJump({ onPick, exclude, active }: {
  onPick: (abbrev: string) => void
  exclude?: string[]
  /** Highlight this team (in its color) — for selectors where one team is the current choice. */
  active?: string
}) {
  const ex = new Set(exclude ?? [])
  return (
    <div className="team-quickjump">
      {TEAMS.filter((ab) => !ex.has(ab)).map((ab) => (
        <button key={ab} className={`team-quickjump__chip ${ab === active ? 'is-active' : ''}`}
                style={ab === active ? { '--tqj-active': getTeamColor(ab) } as React.CSSProperties : undefined}
                onClick={() => onPick(ab)} title={getTeamName(ab)}>
          <img src={getTeamLogoUrl(ab)} alt="" className="team-quickjump__logo" loading="lazy" />
          <span className="mono">{ab}</span>
        </button>
      ))}
    </div>
  )
}
