/**
 * Reusable player card (Phase 5.2 Lineup Lab redesign): headshot with initials fallback,
 * team-colour accent ring, team logo badge, name + position/stat line. Supports click,
 * drag-and-drop, a remove button, a "taken/disabled" state, and three sizes.
 *
 * Headshots come from the API `headshot_url` when present, otherwise constructed from the
 * NHL mugs URL pattern via getPlayerHeadshotUrl (player id + team abbreviation).
 */
import { useState } from 'react'
import { X } from 'lucide-react'
import { getPlayerHeadshotUrl, getTeamColor, getTeamLogoUrl } from '../../utils/teams'
import './PlayerCard.css'

export interface PlayerCardData {
  player_id: number
  name?: string | null
  team_abbrev?: string | null
  position?: string | null
  headshot_url?: string | null
  archetype?: string | null
}

interface PlayerCardProps {
  player: PlayerCardData
  size?: 'sm' | 'md' | 'lg'
  onClick?: () => void
  onRemove?: () => void
  draggable?: boolean
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: (e: React.DragEvent) => void
  /** Currently-targeted/active styling. */
  selected?: boolean
  /** Already used elsewhere — dim and ignore interaction. */
  disabled?: boolean
  /** Optional stat shown under the name instead of the archetype chip. */
  stat?: { label: string; value: string } | null
}

function initials(name?: string | null): string {
  if (!name) return '—'
  const parts = name.trim().split(/\s+/)
  const first = parts[0]?.[0] ?? ''
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase() || '—'
}

const POS_FULL: Record<string, string> = {
  C: 'Center', L: 'Left Wing', R: 'Right Wing', D: 'Defense', G: 'Goalie',
}

export default function PlayerCard({
  player, size = 'md', onClick, onRemove, draggable, onDragStart, onDragEnd,
  selected, disabled, stat,
}: PlayerCardProps) {
  const [imgError, setImgError] = useState(false)
  const abbrev = player.team_abbrev ?? ''
  const headshot = !imgError
    ? (player.headshot_url || (abbrev ? getPlayerHeadshotUrl(player.player_id, abbrev) : ''))
    : ''
  const accent = abbrev ? getTeamColor(abbrev) : 'var(--color-border-strong)'
  const interactive = !!onClick && !disabled

  return (
    <div
      className={[
        'player-card', `player-card--${size}`,
        interactive ? 'player-card--clickable' : '',
        selected ? 'player-card--selected' : '',
        disabled ? 'player-card--disabled' : '',
      ].join(' ').trim()}
      style={{ '--pc-accent': accent } as React.CSSProperties}
      onClick={interactive ? onClick : undefined}
      draggable={draggable && !disabled}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={interactive ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick!() } } : undefined}
      title={player.name ?? undefined}
    >
      <div className="player-card__media">
        {headshot ? (
          <img
            className="player-card__headshot"
            src={headshot}
            alt=""
            draggable={false}
            onError={() => setImgError(true)}
          />
        ) : (
          <span className="player-card__initials">{initials(player.name)}</span>
        )}
        {abbrev && (
          <img
            className="player-card__logo"
            src={getTeamLogoUrl(abbrev)}
            alt={abbrev}
            draggable={false}
            onError={(e) => ((e.currentTarget.style.display = 'none'))}
          />
        )}
        {disabled && <span className="player-card__taken">In lineup</span>}
      </div>

      <div className="player-card__body">
        <span className="player-card__name">{player.name ?? `#${player.player_id}`}</span>
        <span className="player-card__meta">
          <span className="player-card__pos">{POS_FULL[player.position ?? ''] ?? player.position ?? ''}</span>
          {stat
            ? <span className="player-card__stat">{stat.value}<small> {stat.label}</small></span>
            : player.archetype && <span className="player-card__chip">{player.archetype}</span>}
        </span>
      </div>

      {onRemove && !disabled && (
        <button
          className="player-card__remove"
          onClick={(e) => { e.stopPropagation(); onRemove() }}
          aria-label={`Remove ${player.name ?? 'player'}`}
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}
