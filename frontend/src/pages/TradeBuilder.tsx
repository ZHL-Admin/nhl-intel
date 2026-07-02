/**
 * Trade Builder (Tools) — construct and evaluate a real multi-team trade.
 *
 * Binds to the evaluation engine (POST /tools/trade-evaluate) and the unified asset search
 * (/assets/search). A trade is a set of teams, the assets each sends, the destination of each
 * asset, and any retention elections. Multi-team from the start (the engine is N-team). The
 * verdict is a per-team decomposition (talent / cost-efficiency / fit) — never a single grade.
 */
import { useEffect, useMemo, useState } from 'react'
import { Plus, RotateCcw, Loader2 } from 'lucide-react'
import { PageLayout, PageCard, TeamQuickJump, SkeletonLoader } from '../components/common'
import { TradeableAsset, TradeEvaluateRequest, TradeEvaluateResponse } from '../api/types'
import { DIVISIONS, getTeamName } from '../utils/teams'
import { evaluateTrade, searchAssets } from '../api/assets'
import TradeTeamPanel from '../components/trade/TradeTeamPanel'
import TradeSetup from '../components/trade/TradeSetup'
import { TradeSummaryBand, Domains } from '../components/trade/TradeVerdict'
import './TradeBuilder.css'

function computeDomains(res: TradeEvaluateResponse | null): Domains {
  let tD = 2, sD = 5_000_000
  for (const t of res?.teams ?? []) {
    tD = Math.max(tD, Math.abs(t.talent_delta_war ?? 0), Math.abs(t.talent_delta_war_low ?? 0), Math.abs(t.talent_delta_war_high ?? 0))
    sD = Math.max(sD, Math.abs(t.surplus_delta_dollars ?? 0), Math.abs(t.surplus_delta_dollars_low ?? 0), Math.abs(t.surplus_delta_dollars_high ?? 0))
  }
  return { talent: [-tD, tD], surplus: [-sD, sD] }
}

/** One asset placed into the trade: who sends it, where it goes, and any retained salary. */
export interface BuilderItem {
  asset: TradeableAsset
  fromTeam: number
  toTeam: number | null
  retainedPct?: number          // source-team salary retention (players only)
}

const ALL_TEAMS = DIVISIONS.flatMap((d) => d.teams).sort((a, b) => getTeamName(a.abbrev).localeCompare(getTeamName(b.abbrev)))
const ABBR_TO_ID = new Map(ALL_TEAMS.map((t) => [t.abbrev, t.id]))

/** An empty team slot — a dashed inset prompting the user to choose the next team from the same chip
 * grid used on the setup screen (no team preselected). */
function EmptyTeamSlot({ label, excludeAbbrevs, onPick }: {
  label: string
  excludeAbbrevs: string[]
  onPick: (id: number) => void
}) {
  return (
    <div className="trade-team-slot">
      <span className="trade-team-slot__label"><Plus size={14} /> {label}</span>
      <TeamQuickJump exclude={excludeAbbrevs} onPick={(ab) => { const id = ABBR_TO_ID.get(ab); if (id != null) onPick(id) }} />
    </div>
  )
}

export default function TradeBuilder() {
  // No teams are preselected — the board starts empty and the user chooses each side.
  const [teams, setTeams] = useState<number[]>([])
  const [items, setItems] = useState<BuilderItem[]>([])
  const [addingTeam, setAddingTeam] = useState(false)   // an extra empty column the user opened

  const addTeam = (id: number) => { setTeams((t) => (t.includes(id) ? t : [...t, id])); setAddingTeam(false) }
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

  // Setup-state actions (shown until both sides have a team)
  // Start from a player: select their team as a side and queue them as the first asset to move.
  const startFromPlayer = (asset: TradeableAsset) => {
    const tid = asset.org_team ? ABBR_TO_ID.get(asset.org_team) : undefined
    if (tid == null) return
    addTeam(tid)
    addItem(tid, asset)
  }
  // Load a ready example: a two-team swap of each side's top tradeable player (live data, no hardcoding).
  const loadExample = async () => {
    const a = { id: 22, abbrev: 'EDM' }, b = { id: 10, abbrev: 'TOR' }
    setItems([])
    setTeams([a.id, b.id])
    setAddingTeam(false)
    try {
      const [as, bs] = await Promise.all([
        searchAssets({ org: a.abbrev, type: 'player', limit: 5 }),
        searchAssets({ org: b.abbrev, type: 'player', limit: 5 }),
      ])
      const pick = (arr: TradeableAsset[], abbr: string) => arr.find((x) => x.org_team === abbr) ?? arr[0]
      const aAsset = pick(as, a.abbrev), bAsset = pick(bs, b.abbrev)
      const next: BuilderItem[] = []
      if (aAsset) next.push({ asset: aAsset, fromTeam: a.id, toTeam: b.id })
      if (bAsset) next.push({ asset: bAsset, fromTeam: b.id, toTeam: a.id })
      setItems(next)
    } catch { /* leave the two teams selected so the user can build from there */ }
  }

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

  // with exactly two teams the destination is unambiguous — keep every asset pointed at the other side
  useEffect(() => {
    if (teams.length !== 2) return
    setItems((its) => {
      let changed = false
      const next = its.map((i) => {
        const other = teams.find((t) => t !== i.fromTeam) ?? null
        if (i.toTeam !== other) { changed = true; return { ...i, toTeam: other } }
        return i
      })
      return changed ? next : its
    })
  }, [teams])

  const availableToAdd = ALL_TEAMS.filter((t) => !teams.includes(t.id))
  const pickedAbbrevs = teams.map((id) => ALL_TEAMS.find((t) => t.id === id)?.abbrev).filter(Boolean) as string[]
  const hasMovements = request.movements.length > 0
  // empty team slots only fill UP TO the required two; a 3rd+ column is added on demand via a button
  const slotCount = Math.min(Math.max(2 - teams.length, 0) + (addingTeam ? 1 : 0), availableToAdd.length)

  // re-evaluate on any change to the trade (debounced); the verdict updates live
  const [result, setResult] = useState<TradeEvaluateResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!hasMovements) { setResult(null); setError(null); return }
    let cancel = false
    setLoading(true)
    const t = setTimeout(async () => {
      try {
        const res = await evaluateTrade(request)
        if (!cancel) { setResult(res); setError(null) }
      } catch (e: unknown) {
        const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        if (!cancel) { setResult(null); setError(detail ?? 'Could not evaluate this trade.') }
      } finally {
        if (!cancel) setLoading(false)
      }
    }, 280)
    return () => { cancel = true; clearTimeout(t) }
  }, [request, hasMovements])

  const domains = useMemo(() => computeDomains(result), [result])
  const resultByTeam = useMemo(() => {
    const m = new Map<number, TradeEvaluateResponse['teams'][number]>()
    for (const t of result?.teams ?? []) m.set(t.team_id, t)
    return m
  }, [result])

  return (
    <PageLayout>
      <div className="trade-builder">
        <PageCard
          title="Trade Builder"
          subtitle="Construct a trade across two or more teams, elect salary retention, and read each side as a decomposition — talent, cost-efficiency, and fit — never a single grade."
          controls={
            <div className="trade-builder__toolbar">
              <span className="trade-builder__teamcount">{teams.length} teams · {items.length} assets</span>
              {loading && result && (
                <span className="trade-builder__updating"><Loader2 size={13} className="spin" /> Evaluating…</span>
              )}
              {teams.length >= 2 && availableToAdd.length > 0 && !addingTeam && (
                <button className="trade-builder__addteam" onClick={() => setAddingTeam(true)}>
                  <Plus size={14} /> Add team
                </button>
              )}
              {(items.length > 0 || teams.length > 0 || addingTeam) && (
                <button className="trade-builder__reset" onClick={() => { setItems([]); setTeams([]); setAddingTeam(false) }}>
                  <RotateCcw size={14} /> Reset
                </button>
              )}
            </div>
          }
          bodyClassName="trade-builder__body"
        >
          {teams.length === 0 ? (
            <TradeSetup
              teams={teams}
              onPickTeam={addTeam}
              onStartFromPlayer={startFromPlayer}
              onLoadExample={loadExample}
            />
          ) : (
            <>
              {error && <p className="trade-builder__error">{error}</p>}
              {hasMovements && loading && !result && <SkeletonLoader />}
              {result && <TradeSummaryBand teams={result.teams} />}

              <div className="trade-builder__panels" data-count={teams.length + slotCount}>
                {teams.map((tid) => (
                  <TradeTeamPanel
                    key={tid}
                    teamId={tid}
                    teams={teams}
                    items={items.filter((i) => i.fromTeam === tid)}
                    usedIds={usedIds}
                    canRemove={true}
                    result={resultByTeam.get(tid)}
                    domains={result ? domains : null}
                    onRemoveTeam={() => removeTeam(tid)}
                    onAddAsset={(asset) => addItem(tid, asset)}
                    onRemoveAsset={removeItem}
                    onSetDestination={setDestination}
                    onSetRetention={setRetention}
                  />
                ))}
                {/* prompt for the next team — fills up to two sides, plus an on-demand 3rd+ column */}
                {Array.from({ length: slotCount }).map((_, i) => (
                  <EmptyTeamSlot key={`slot-${i}`}
                    label={teams.length < 2 ? 'Choose the other side' : 'Add a team'}
                    excludeAbbrevs={pickedAbbrevs} onPick={addTeam} />
                ))}
              </div>

              {!hasMovements && (
                <p className="trade-builder__hint">
                  {teams.length < 2
                    ? 'Add the other side to complete the trade, then assign each asset a destination.'
                    : 'Add assets to each team and assign where they go. The verdict appears here as soon as the first asset has a destination.'}
                </p>
              )}
              {result?.dollar_basis && (
                <p className="trade-builder__basis">{result.dollar_basis}</p>
              )}
            </>
          )}
        </PageCard>
      </div>
    </PageLayout>
  )
}
