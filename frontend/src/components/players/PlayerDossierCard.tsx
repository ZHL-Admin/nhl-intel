/**
 * PlayerDossierCard (07 v3 §5) — the expanded row detail on the Players board.
 *
 * Deliberately NOT PlayerRowExpansion: v3 §5.4 removes the radar (now on the full profile),
 * the season-stats table (now in the row), and all pill chips from this card. The card shows,
 * in order: header + actions, the verdict pull-quote, and a two-column body — GAR composition +
 * percentile pair on the left, the ±1 sd confidence band + season trend on the right.
 *
 * The GAR component split, GAR, WAR and ±sd all come from the row already loaded by the board;
 * only the verdict, percentiles, archetype, and bio need a per-player fetch.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, GitCompare } from 'lucide-react'
import PlayerAvatar from '../common/PlayerAvatar'
import EntityPicker from '../common/EntityPicker'
import Gauge from '../common/Gauge'
import SkeletonLoader from '../common/SkeletonLoader'
import { getPlayerDetail, getPlayerPreview, getPlayerVerdict } from '../../api/players'
import { getGoaliePreview } from '../../api/goalies'
import type { CompositeComponent, PlayerSearchResult } from '../../api/types'
import './PlayerDossierCard.css'

export interface DossierRow {
  id: number
  name?: string | null
  team?: string | null
  position?: string | null
  entityKind: 'skater' | 'goalie'
  /** The displayed WAR (reliability-shrunk point estimate). */
  war: number
  gar: number
  warSd?: number | null
  components: CompositeComponent[]
  tierLabel?: string | null
}

interface Supp {
  age: number | null
  hand: string | null            // shoots / catches
  archetype: string | null
  productionPct: number | null   // "what happened" — actual goals impact percentile (0..1)
  playDrivingPct: number | null  // "what tends to repeat" — RAPM composite percentile (0..1)
  verdict: string | null
}

const _cache = new Map<string, Supp>()

const fmtSigned = (v: number, d = 1) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}`

/** Position-group dot colour (site tokens): forwards, defense, goalies. */
function posDotColor(pos?: string | null): string {
  if (pos === 'G') return 'var(--pos-goalie)'
  if (pos === 'D') return 'var(--pos-defense)'
  return 'var(--pos-forward)'
}

/** The fixed 0→+6 WAR domain shared with the row micro-bands (§5.3). */
const WAR_DOMAIN_HI = 6
const clampWar = (v: number) => Math.max(0, Math.min(WAR_DOMAIN_HI, v))
const warPct = (v: number) => (clampWar(v) / WAR_DOMAIN_HI) * 100

export default function PlayerDossierCard({
  row, season, onCompare,
}: {
  row: DossierRow
  season: string
  /** Optional external compare handler; falls back to the built-in picker → /players/compare. */
  onCompare?: () => void
}) {
  const navigate = useNavigate()
  const [supp, setSupp] = useState<Supp | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const mounted = useRef(true)
  const cacheKey = `${row.entityKind}:${row.id}:${season}`

  useEffect(() => {
    mounted.current = true
    const cached = _cache.get(cacheKey)
    if (cached) { setSupp(cached); return }
    setSupp(null)
    const verdictP = getPlayerVerdict(row.id, season)
    const run = row.entityKind === 'goalie'
      ? Promise.allSettled([getGoaliePreview(row.id, season), verdictP]).then(([p, v]): Supp => ({
          age: p.status === 'fulfilled' ? p.value.age ?? null : null,
          hand: p.status === 'fulfilled' ? p.value.catches ?? null : null,
          archetype: null,
          // TODO(data): goalie production/play-driving percentiles are not served on the value row;
          // GoalieValue exposes only war_percentile (a single lens), so the pair is omitted for goalies.
          productionPct: null,
          playDrivingPct: null,
          verdict: v.status === 'fulfilled' && v.value ? (v.value.long || v.value.short || null) : null,
        }))
      : Promise.allSettled([getPlayerDetail(row.id, season), getPlayerPreview(row.id, season), verdictP])
          .then(([d, p, v]): Supp => {
            const detail = d.status === 'fulfilled' ? d.value : null
            const val = detail?.value ?? null
            let verdict: string | null = v.status === 'fulfilled' && v.value ? (v.value.long || v.value.short || null) : null
            if (!verdict && val?.read) verdict = `${val.read.headline} ${val.read.body}`
            return {
              age: p.status === 'fulfilled' ? p.value.age ?? null : null,
              hand: p.status === 'fulfilled' ? p.value.shoots ?? null : null,
              archetype: detail?.durable_archetype ?? detail?.primary_archetype ?? null,
              productionPct: val?.impact_percentile ?? null,
              playDrivingPct: val?.value_percentile ?? null,
              verdict,
            }
          })
    run.then((res) => { _cache.set(cacheKey, res); if (mounted.current) setSupp(res) })
    return () => { mounted.current = false }
  }, [cacheKey, row.id, row.entityKind, season])

  const goProfile = () => navigate(`/players/${row.id}`)
  const goCompare = (b: PlayerSearchResult) => navigate(`/players/compare?a=${row.id}&b=${b.player_id}`)
  const handleCompare = () => { if (onCompare) onCompare(); else setPickerOpen(true) }

  if (!supp) {
    return <div className="pdc"><div className="pdc__loading"><SkeletonLoader /></div></div>
  }

  // Meta line: "C · EDM · Age 28 · Shoots L · {tier} · {archetype}"
  const handWord = row.entityKind === 'goalie' ? 'Catches' : 'Shoots'
  const metaParts = [
    row.position, row.team,
    supp.age != null ? `Age ${supp.age}` : null,
    supp.hand ? `${handWord} ${supp.hand}` : null,
    row.tierLabel ?? null,
    supp.archetype ?? null,
  ].filter(Boolean) as string[]

  // GAR composition — bars scale to the largest absolute component.
  const comps = row.components ?? []
  const maxAbs = comps.reduce((m, c) => Math.max(m, Math.abs(c.value)), 0.0001)

  const sd = row.warSd ?? 0
  const bandLo = warPct(row.war - sd)
  const bandHi = warPct(row.war + sd)

  return (
    <div className="pdc">
      {/* 5.1 header */}
      <div className="pdc__head">
        <div className="pdc__id">
          <PlayerAvatar id={row.id} team={row.team} name={row.name} size={36} />
          <div className="pdc__idtext">
            <div className="pdc__name">{row.name ?? row.id}</div>
            <div className="pdc__meta">
              <span className="pdc__meta-dot" aria-hidden="true">
                <span style={{
                  width: 7, height: 7, borderRadius: '50%', display: 'inline-block',
                  background: posDotColor(row.position),
                }} />
              </span>
              {metaParts.join(' · ')}
            </div>
          </div>
        </div>
        <div className="pdc__actions">
          <button className="pdc__btn pdc__btn--primary" onClick={goProfile}>
            View full profile <ArrowRight size={14} />
          </button>
          <button className="pdc__btn pdc__btn--secondary" onClick={handleCompare}>
            <GitCompare size={14} /> Compare with…
          </button>
        </div>
      </div>

      {/* 5.2 verdict pull-quote (omitted entirely when none is served) */}
      {supp.verdict && <p className="pdc__verdict">{supp.verdict}</p>}

      {/* 5.3 two-column body */}
      <div className="pdc__body">
        {/* LEFT — where the value comes from */}
        <div className="pdc__col">
          <div className="pdc__coltitle">Where the value comes from · GAR</div>
          {comps.length > 0 ? (
            <div className="pdc__comp">
              {comps.map((c) => {
                const pos = c.value >= 0
                const w = (Math.abs(c.value) / maxAbs) * 50   // half-width max; bar grows from zero
                return (
                  <div key={c.key}>
                    <div className="pdc__comp-row">
                      <span className="pdc__comp-label">{c.label}</span>
                      <span className={`pdc__comp-val${pos ? '' : ' pdc__comp-val--neg'}`}>{fmtSigned(c.value)}</span>
                    </div>
                    <div className="pdc__comp-bar">
                      <span className="pdc__comp-zero" style={{ left: '50%' }} />
                      <span className={`pdc__comp-fill pdc__comp-fill--${pos ? 'pos' : 'neg'}`}
                        style={pos ? { left: '50%', width: `${w}%` } : { left: `${50 - w}%`, width: `${w}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            // TODO(data): per-component GAR not served for this row — /rankings/value.components empty.
            <p className="pdc__note">Component breakdown not available.</p>
          )}

          <p className="pdc__total">
            Total <b>{fmtSigned(row.gar)} GAR</b> → <b>{fmtSigned(row.war)} WAR</b> after reliability shrinkage
          </p>

          {(supp.productionPct != null || supp.playDrivingPct != null) && (
            <div className="pdc__pctpair">
              {supp.productionPct != null && (
                <div>
                  <div className="pdc__pct-label">Production</div>
                  <Gauge value={supp.productionPct} valueLabel={Math.round(supp.productionPct * 100).toString()} />
                </div>
              )}
              {supp.playDrivingPct != null && (
                <div>
                  <div className="pdc__pct-label">Play-driving</div>
                  <Gauge value={supp.playDrivingPct} valueLabel={Math.round(supp.playDrivingPct * 100).toString()} />
                </div>
              )}
            </div>
          )}
        </div>

        {/* RIGHT — confidence + trend */}
        <div className="pdc__col">
          <div className="pdc__coltitle">Confidence range · ±1 sd</div>
          <div className="pdc__band">
            <span className="pdc__band-track" />
            <span className="pdc__band-zero" style={{ left: '0%' }} />
            {sd > 0 && (
              <span className="pdc__band-range" style={{ left: `${bandLo}%`, width: `${Math.max(0, bandHi - bandLo)}%` }} />
            )}
            <span className="pdc__band-point" style={{ left: `${warPct(row.war)}%` }} />
          </div>
          <div className="pdc__band-scale"><span>0</span><span>+6</span></div>
          <p className="pdc__band-caption">
            WAR is shrunk toward league average until the sample earns it. A wider band means a softer
            rank; when two bands overlap, the order between them is soft.
          </p>

          {/* Season by season — WAR-by-season history is not served yet. */}
          {/* TODO(data): needs a WAR-by-season history endpoint (per §7); trend omitted until served. */}
          <div className="pdc__trend">
            <div className="pdc__coltitle">Season by season</div>
            <p className="pdc__note">Season-by-season WAR history is not available yet.</p>
          </div>
        </div>
      </div>

      <EntityPicker open={pickerOpen} onClose={() => setPickerOpen(false)} onSelect={goCompare}
        title={`Compare ${row.name ?? 'player'} with…`} season={season} />
    </div>
  )
}
