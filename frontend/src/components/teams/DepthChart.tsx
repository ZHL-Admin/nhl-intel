/**
 * DepthChart (Blueprint 2.7) — the roster arranged the way the team deploys: forward lines F1–F4,
 * defence pairs D1–D3, and the goalie tandem, each slot a Player M identity block. Sorted by TOI/GP
 * as the deployment proxy. (Per-slot tier badges + the tier census need a batched assessment endpoint;
 * flagged — this v1 shows the deployment structure + archetype from the roster payload.)
 */
import { useEffect, useState } from 'react'
import { SkeletonLoader, EntityIdentity, type PlayerIdentity } from '../common'
import { getTeamRoster } from '../../api/teams'
import type { TeamRoster, RosterPlayer } from '../../api/types'
import './DepthChart.css'

const byTOI = (a: RosterPlayer, b: RosterPlayer) => (b.toi_per_gp ?? 0) - (a.toi_per_gp ?? 0)

function slot(p: RosterPlayer, teamAbbrev: string): PlayerIdentity {
  return {
    id: p.player_id, name: p.player_name, position: p.position, teamAbbrev,
    archetypes: p.archetype ? [p.archetype] : undefined,
  }
}

function Unit({ label, players, teamAbbrev }: { label: string; players: RosterPlayer[]; teamAbbrev: string }) {
  if (players.length === 0) return null
  return (
    <div className="depth-unit">
      <span className="depth-unit__label mono">{label}</span>
      <div className="depth-unit__slots">
        {players.map((p) => (
          <div key={p.player_id} className="depth-unit__slot">
            <EntityIdentity kind="player" size="m" player={slot(p, teamAbbrev)} link />
          </div>
        ))}
      </div>
    </div>
  )
}

export default function DepthChart({ teamId, teamAbbrev }: { teamId: number; teamAbbrev: string }) {
  const [roster, setRoster] = useState<TeamRoster | null>(null)
  useEffect(() => { getTeamRoster(teamId).then(setRoster).catch(() => setRoster(null)) }, [teamId])

  if (!roster) return <SkeletonLoader height={400} />

  const fwd = [...roster.forwards].sort(byTOI)
  const def = [...roster.defensemen].sort(byTOI)
  const lines = [fwd.slice(0, 3), fwd.slice(3, 6), fwd.slice(6, 9), fwd.slice(9, 12)]
  const pairs = [def.slice(0, 2), def.slice(2, 4), def.slice(4, 6)]

  return (
    <div className="depth-chart">
      <div className="depth-chart__group">
        <h3 className="page-region-title">Forwards</h3>
        {lines.map((ln, i) => <Unit key={i} label={`L${i + 1}`} players={ln} teamAbbrev={teamAbbrev} />)}
      </div>
      <div className="depth-chart__group">
        <h3 className="page-region-title">Defence</h3>
        {pairs.map((pr, i) => <Unit key={i} label={`D${i + 1}`} players={pr} teamAbbrev={teamAbbrev} />)}
      </div>
      <div className="depth-chart__group">
        <h3 className="page-region-title">Goaltending</h3>
        <Unit label="G" players={roster.goalies} teamAbbrev={teamAbbrev} />
      </div>
    </div>
  )
}
