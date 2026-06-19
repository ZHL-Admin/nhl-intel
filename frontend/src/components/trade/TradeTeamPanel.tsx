/**
 * One team's panel in the Trade Builder: the team header (with remove when >2 teams), an asset
 * picker for what this team SENDS, and a chip per sent asset showing its value (WAR + band), its
 * surplus, its cost, a destination selector, and (P3) a retention control. Reuses PlayerAvatar.
 */
import { ArrowRight, X } from 'lucide-react'
import { PlayerAvatar, Select } from '../common'
import { TradeableAsset } from '../../api/types'
import { getTeamName, getTeamLogoUrl, getTeamAbbrev } from '../../utils/teams'
import { fmtWar, fmtWarBand, fmtDollarsM, CAP_DOLLAR_TAG } from '../../utils/format'
import AssetPicker from './AssetPicker'
import type { BuilderItem } from '../../pages/TradeBuilder'
import './TradeTeamPanel.css'

function AssetChip({ item, teams, onRemove, onSetDestination }: {
  item: BuilderItem
  teams: number[]
  onRemove: (id: string) => void
  onSetDestination: (id: string, to: number) => void
}) {
  const a = item.asset
  const dests = teams.filter((t) => t !== item.fromTeam)
  const band = fmtWarBand(a.value_war_low, a.value_war_high)
  return (
    <div className={`asset-chip asset-chip--${a.asset_type}`}>
      <div className="asset-chip__id">
        {a.asset_type === 'player' && a.player_id
          ? <PlayerAvatar id={a.player_id} team={a.org_team} name={a.label} size={30} />
          : <span className={`asset-chip__badge asset-chip__badge--${a.asset_type}`}>{a.asset_type === 'pick' ? 'PK' : 'PR'}</span>}
        <div className="asset-chip__meta">
          <span className="asset-chip__name">{a.label}</span>
          <span className="asset-chip__slot">{a.pos_or_slot}</span>
        </div>
        <button className="asset-chip__remove" onClick={() => onRemove(a.asset_id)} aria-label={`Remove ${a.label}`}>
          <X size={14} />
        </button>
      </div>

      <div className="asset-chip__nums">
        <span className="asset-chip__num">
          <span className="asset-chip__num-val">{fmtWar(a.value_war)}</span>
          <span className="asset-chip__num-lbl">WAR{band ? ` · ${band}` : ''}</span>
        </span>
        <span className="asset-chip__num">
          <span className="asset-chip__num-val" title={CAP_DOLLAR_TAG}>{fmtDollarsM(a.surplus_dollars, true)}</span>
          <span className="asset-chip__num-lbl">surplus</span>
        </span>
        {a.cap_hit != null && (
          <span className="asset-chip__num">
            <span className="asset-chip__num-val">{fmtDollarsM(a.cap_hit)}</span>
            <span className="asset-chip__num-lbl">cap · {a.remaining_years}y</span>
          </span>
        )}
      </div>

      <div className="asset-chip__dest">
        <ArrowRight size={14} className="asset-chip__dest-arrow" />
        <Select
          ariaLabel={`Destination for ${a.label}`}
          value={item.toTeam != null ? String(item.toTeam) : ''}
          options={[{ value: '', label: 'Send to…' },
                    ...dests.map((t) => ({ value: String(t), label: getTeamName(getTeamAbbrev(t)) }))]}
          onChange={(v) => v && onSetDestination(a.asset_id, Number(v))}
        />
      </div>
    </div>
  )
}

export default function TradeTeamPanel({
  teamId, teams, items, usedIds, canRemove, onRemoveTeam, onAddAsset, onRemoveAsset, onSetDestination,
}: {
  teamId: number
  teams: number[]
  items: BuilderItem[]
  usedIds: Set<string>
  canRemove: boolean
  onRemoveTeam: () => void
  onAddAsset: (asset: TradeableAsset) => void
  onRemoveAsset: (assetId: string) => void
  onSetDestination: (assetId: string, to: number) => void
  onSetRetention: (assetId: string, pct: number | undefined) => void
}) {
  const abbrev = getTeamAbbrev(teamId)
  return (
    <section className="trade-team-panel">
      <header className="trade-team-panel__head">
        <img className="trade-team-panel__logo" src={getTeamLogoUrl(abbrev)} alt=""
             onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
        <h2 className="trade-team-panel__name">{getTeamName(abbrev)}</h2>
        {canRemove && (
          <button className="trade-team-panel__remove" onClick={onRemoveTeam} aria-label={`Remove ${abbrev}`}>
            <X size={15} />
          </button>
        )}
      </header>

      <AssetPicker orgTeam={abbrev} usedIds={usedIds} onAdd={onAddAsset} />

      <div className="trade-team-panel__sends">
        <span className="trade-team-panel__sends-label">{abbrev} sends</span>
        {items.length === 0
          ? <p className="trade-team-panel__none">Nothing yet — search above to add an asset {abbrev} would trade.</p>
          : items.map((it) => (
              <AssetChip key={it.asset.asset_id} item={it} teams={teams}
                         onRemove={onRemoveAsset} onSetDestination={onSetDestination} />
            ))}
      </div>
    </section>
  )
}
