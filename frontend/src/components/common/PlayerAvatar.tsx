/**
 * PlayerAvatar — a round headshot with a team-logo badge and an initials fallback. One shared
 * implementation reused by the Players leaderboard rows, the divergence board, and the row
 * expansion preview (size-scalable via the --pav var). Replaces the per-surface copies.
 */
import { useState } from 'react'
import { getPlayerHeadshotUrl, getTeamLogoUrl } from '../../utils/teams'
import './PlayerAvatar.css'

function initials(name?: string | null): string {
  if (!name) return '—'
  const p = name.trim().split(/\s+/)
  return ((p[0]?.[0] ?? '') + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase() || '—'
}

interface Props {
  id: number
  team?: string | null
  name?: string | null
  size?: number
}

export default function PlayerAvatar({ id, team, name, size = 40 }: Props) {
  const [err, setErr] = useState(false)
  const src = !err && team ? getPlayerHeadshotUrl(id, team) : ''
  return (
    <span className="pav" style={{ ['--pav' as string]: `${size}px` } as React.CSSProperties}>
      {src
        ? <img className="pav__img" src={src} alt="" onError={() => setErr(true)} />
        : <span className="pav__ini">{initials(name)}</span>}
      {team && (
        <img className="pav__logo" src={getTeamLogoUrl(team)} alt=""
          onError={(e) => ((e.currentTarget.style.display = 'none'))} />
      )}
    </span>
  )
}
