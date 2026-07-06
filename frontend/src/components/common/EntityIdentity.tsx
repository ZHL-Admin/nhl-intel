/**
 * EntityIdentity (Blueprint P2) — the ONE way to render a player or team, at three sizes. No surface
 * renders an entity any other way.
 *   Player S (rows):    rank? · name 14/500 · team mono · TierBadge · confidence dot. 44px.
 *   Player M (cards):   32 avatar · name · pos·team mono · TierBadge · confidence dot. 64px.
 *   Player L (header):  48 avatar · name display serif · pos·team·age·shoots mono · archetype chips.
 *   Team mirrors it with logo · record · power pill.
 */
import { Link } from 'react-router-dom'
import PlayerAvatar from './PlayerAvatar'
import TierBadge from './TierBadge'
import { getTeamLogoUrl, getTeamName } from '../../utils/teams'
import './EntityIdentity.css'

export interface PlayerIdentity {
  id: number
  name: string
  position?: string | null
  teamAbbrev?: string | null
  headshotUrl?: string | null
  age?: number | null
  shoots?: string | null
  archetypes?: string[]
  tier?: { label: string } | null
  confidenceTone?: 'high' | 'medium' | 'low' | null
}

export interface TeamIdentity {
  id: number
  abbrev: string
  name?: string | null
  record?: string | null
  powerRank?: number | null
}

type Size = 's' | 'm' | 'l'

type Props =
  | { kind: 'player'; size: Size; player: PlayerIdentity; rank?: number; link?: boolean }
  | { kind: 'team'; size: Size; team: TeamIdentity; rank?: number; link?: boolean }

const ConfidenceDot = ({ tone }: { tone?: 'high' | 'medium' | 'low' | null }) =>
  tone ? <span className={`entity__conf entity__conf--${tone}`} title={`${tone} confidence`} /> : null

const avatarPx: Record<Size, number> = { s: 0, m: 32, l: 48 }

export default function EntityIdentity(props: Props) {
  const { kind, size } = props
  const cls = `entity entity--${kind} entity--${size}`

  let inner: React.ReactNode
  let to: string

  if (props.kind === 'player') {
    const p = props.player
    to = `/players/${p.id}`
    const meta = [p.position, p.teamAbbrev].filter(Boolean).join(' · ')
    const longMeta = [p.position, p.teamAbbrev, p.age != null ? `age ${p.age}` : null, p.shoots ? `shoots ${p.shoots}` : null]
      .filter(Boolean).join(' · ')
    inner = (
      <>
        {props.rank != null && <span className="entity__rank mono">{props.rank}</span>}
        {size !== 's' && (
          <PlayerAvatar id={p.id} name={p.name} team={p.teamAbbrev ?? undefined} size={avatarPx[size]} />
        )}
        <span className="entity__body">
          <span className="entity__name">{p.name}</span>
          <span className="entity__meta mono">{size === 'l' ? longMeta : meta}</span>
          {size === 'l' && p.archetypes && p.archetypes.length > 0 && (
            <span className="entity__chips">
              {p.archetypes.map((a) => <span key={a} className="entity__chip">{a}</span>)}
            </span>
          )}
        </span>
        <span className="entity__tail">
          {p.tier && <TierBadge label={p.tier.label} confidence={p.confidenceTone ?? undefined} size={size === 's' ? 'sm' : 'md'} />}
          <ConfidenceDot tone={p.confidenceTone} />
        </span>
      </>
    )
  } else {
    const t = props.team
    to = `/teams/${t.id}`
    inner = (
      <>
        {props.rank != null && <span className="entity__rank mono">{props.rank}</span>}
        <img className="entity__logo" src={getTeamLogoUrl(t.abbrev)} alt=""
          style={{ width: size === 'l' ? 48 : size === 'm' ? 32 : 22, height: size === 'l' ? 48 : size === 'm' ? 32 : 22 }}
          onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
        <span className="entity__body">
          <span className="entity__name">{t.name ?? getTeamName(t.abbrev)}</span>
          {t.record && <span className="entity__meta mono">{t.record}</span>}
        </span>
        {t.powerRank != null && <span className="entity__power mono">#{t.powerRank}</span>}
      </>
    )
  }

  return props.link
    ? <Link to={to} className={`${cls} entity--link`}>{inner}</Link>
    : <div className={cls}>{inner}</div>
}
