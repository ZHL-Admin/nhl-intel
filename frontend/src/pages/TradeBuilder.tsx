/**
 * Trade Builder (Tools) — construct and evaluate a real multi-team trade.
 *
 * Binds to the evaluation engine (POST /tools/trade-evaluate) and the unified asset search
 * (/assets/search). A trade is a set of teams, the assets each sends, the destination of each
 * asset, and any retention elections. Multi-team from the start (the engine is N-team). The
 * verdict is a per-team decomposition (talent / cost-efficiency / fit) — never a single grade.
 */
import { useMemo, useState } from 'react'
import { Plus } from 'lucide-react'
import { PageLayout, PageHeader, Select } from '../components/common'
import { TradeableAsset, TradeEvaluateRequest } from '../api/types'
import { DIVISIONS, getTeamName } from '../utils/teams'
import TradeTeamPanel from '../components/trade/TradeTeamPanel'
import './TradeBuilder.css'

/** One asset placed into the trade: who sends it, where it goes, and any retained salary. */
export interface BuilderItem {
  asset: TradeableAsset
  fromTeam: number
  toTeam: number | null
  retainedPct?: number          // source-team salary retention (players only)
}

const ALL_TEAMS = DIVISIONS.flatMap((d) => d.teams).sort((a, b) => getTeamName(a.abbrev).localeCompare(getTeamName(b.abbrev)))

export default function TradeBuilder() {
  // Start with two teams (the common case); the engine and UI both support N.
  const [teams, setTeams] = useState<number[]>([ALL_TEAMS[0].id, ALL_TEAMS[1].id])
  const [items, setItems] = useState<BuilderItem[]>([])

  const addTeam = (id: number) => setTeams((t) => (t.includes(id) ? t : [...t, id]))
  const removeTeam = (id: number) => {
    setTeams((t) => t.filter((x) => x !== id))
    // drop that team's sent assets, and clear destinations pointing at it
    setItems((its) => its
      .filter((i) => i.fromTeam !== id)
      .map((i) => (i.toTeam === id ? { ...i, toTeam: null } : i)))
  }

  const addItem = (fromTeam: number, asset: TradeableAsset) =>
    setItems((its) => its.some((i) => i.asset.asset_id === asset.asset_id)
      ? its
      : [...its, { asset, fromTeam, toTeam: teams.find((t) => t !== fromTeam) ?? null }])
  const removeItem = (assetId: string) => setItems((its) => its.filter((i) => i.asset.asset_id !== assetId))
  const setDestination = (assetId: string, toTeam: number) =>
    setItems((its) => its.map((i) => (i.asset.asset_id === assetId ? { ...i, toTeam } : i)))
  const setRetention = (assetId: string, pct: number | undefined) =>
    setItems((its) => its.map((i) => (i.asset.asset_id === assetId ? { ...i, retainedPct: pct } : i)))

  // assets already in the trade (so the picker can exclude them)
  const usedIds = useMemo(() => new Set(items.map((i) => i.asset.asset_id)), [items])

  // derive the engine request from the builder state
  const request = useMemo<TradeEvaluateRequest>(() => ({
    team_ids: teams,
    movements: items
      .filter((i) => i.toTeam != null)
      .map((i) => ({ asset_id: i.asset.asset_id, from_team_id: i.fromTeam, to_team_id: i.toTeam as number })),
    retentions: items
      .filter((i) => i.retainedPct && i.asset.asset_type === 'player' && i.asset.player_id != null)
      .map((i) => ({ player_id: i.asset.player_id as number, retaining_team_id: i.fromTeam, retained_pct: i.retainedPct as number })),
  }), [teams, items])

  const availableToAdd = ALL_TEAMS.filter((t) => !teams.includes(t.id))
  const hasMovements = request.movements.length > 0

  return (
    <PageLayout>
      <div className="trade-builder">
        <PageHeader
          title="Trade Builder"
          subtitle="Construct a trade across two or more teams, elect salary retention, and read each side as a decomposition — talent, cost-efficiency, and fit — never a single grade."
        />

        <div className="trade-builder__toolbar">
          {availableToAdd.length > 0 && (
            <div className="trade-builder__add-team">
              <Plus size={15} />
              <Select
                ariaLabel="Add a team to the trade"
                value=""
                options={[{ value: '', label: 'Add team…' },
                          ...availableToAdd.map((t) => ({ value: String(t.id), label: getTeamName(t.abbrev) }))]}
                onChange={(v) => v && addTeam(Number(v))}
              />
            </div>
          )}
          <span className="trade-builder__teamcount">{teams.length} teams</span>
        </div>

        <div className="trade-builder__panels" data-count={teams.length}>
          {teams.map((tid) => (
            <TradeTeamPanel
              key={tid}
              teamId={tid}
              teams={teams}
              items={items.filter((i) => i.fromTeam === tid)}
              usedIds={usedIds}
              canRemove={teams.length > 2}
              onRemoveTeam={() => removeTeam(tid)}
              onAddAsset={(asset) => addItem(tid, asset)}
              onRemoveAsset={removeItem}
              onSetDestination={setDestination}
              onSetRetention={setRetention}
            />
          ))}
        </div>

        {!hasMovements && (
          <p className="trade-builder__hint">
            Add assets to each team and assign where they go. The verdict appears here as soon as the
            first asset has a destination.
          </p>
        )}
      </div>
    </PageLayout>
  )
}
