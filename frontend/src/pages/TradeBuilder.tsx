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
import { PageLayout, PageHeader, Select, SkeletonLoader } from '../components/common'
import { TradeableAsset, TradeEvaluateRequest, TradeEvaluateResponse } from '../api/types'
import { DIVISIONS, getTeamName } from '../utils/teams'
import { evaluateTrade } from '../api/assets'
import TradeTeamPanel from '../components/trade/TradeTeamPanel'
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
          <span className="trade-builder__teamcount">{teams.length} teams · {items.length} assets</span>
          {loading && result && (
            <span className="trade-builder__updating"><Loader2 size={13} className="spin" /> Evaluating…</span>
          )}
          {(items.length > 0 || teams.length > 2) && (
            <button className="trade-builder__reset" onClick={() => { setItems([]); setTeams([ALL_TEAMS[0].id, ALL_TEAMS[1].id]) }}>
              <RotateCcw size={14} /> Reset
            </button>
          )}
        </div>

        {error && <p className="trade-builder__error">{error}</p>}
        {hasMovements && loading && !result && <SkeletonLoader />}
        {result && <TradeSummaryBand summary={result.summary} />}

        <div className="trade-builder__panels" data-count={teams.length}>
          {teams.map((tid) => (
            <TradeTeamPanel
              key={tid}
              teamId={tid}
              teams={teams}
              items={items.filter((i) => i.fromTeam === tid)}
              usedIds={usedIds}
              canRemove={teams.length > 2}
              result={resultByTeam.get(tid)}
              domains={result ? domains : null}
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
        {result?.dollar_basis && (
          <p className="trade-builder__basis">{result.dollar_basis}</p>
        )}
      </div>
    </PageLayout>
  )
}
