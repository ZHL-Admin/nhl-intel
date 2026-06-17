/**
 * Players index (Phase 4.2 / 4.3). Leaderboard ranks skaters by total value — overall by default,
 * filterable by position and archetype — with a top-3 hero and ranked list (composite breakdown).
 * The Divergence Board visualises where coaching trust and isolated value most disagree. A search
 * jumps to any player's profile. Controls live in one contained toolbar.
 */
import { useState, useEffect, useMemo, Fragment } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronDown, ArrowRight } from 'lucide-react'
import {
  PageLayout, PageHeader, ComponentStackBar, SkeletonLoader, Tabs, Select, PlayerPicker,
} from '../components/common'
import type { StackSegment, SelectOption } from '../components/common'
import { getOverallLeaders, getArchetypeRanking, getDivergenceBoard,
  getPlayerRadar, getPlayerSummary } from '../api/players'
import { getValueRankings } from '../api/rankings'
import { ArchetypeRankRow, DivergenceBoardRow, PlayerRadar, PlayerSummary, ValueRankingRow } from '../api/types'
import { playerLabelsFromRadar } from '../api/labels'
import SkillRadar from '../components/visualizations/SkillRadar'
import { ARCHETYPES, COMPOSITE_COMPONENTS, VALUE_COMPONENTS } from '../config/metrics'
import { getPlayerHeadshotUrl, getTeamLogoUrl } from '../utils/teams'
import './Players.css'

type Pos = 'ALL' | 'F' | 'D'
const archGroup = (a: string): 'F' | 'D' => (ARCHETYPES.F.includes(a) ? 'F' : 'D')
// seasons with composite + archetype data (newest first)
const SEASONS = ['2025-26', '2024-25', '2023-24', '2022-23', '2021-22']

/** Round value-axis ticks across a domain (a scale for the leaderboard bars). */
function niceTicks([lo, hi]: [number, number]): number[] {
  const range = hi - lo
  const step = range > 40 ? 10 : range > 16 ? 5 : range > 6 ? 2 : 1
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(Math.round(v))
  return out
}
const tickPct = (v: number, [lo, hi]: [number, number]) => ((v - lo) / ((hi - lo) || 1)) * 100

function initials(name?: string | null): string {
  if (!name) return '—'
  const p = name.trim().split(/\s+/)
  return ((p[0]?.[0] ?? '') + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase() || '—'
}

/** Round headshot with a team-logo badge and initials fallback. */
function Avatar({ id, team, name, size = 40 }: { id: number; team?: string | null; name?: string | null; size?: number }) {
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

const fmt = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}`

// The leaderboard shows two lenses on the same UI: Impact (RAPM-based composite value — "what
// repeats") and Value (GAR — actual goals above replacement, "what happened"). Both normalize
// to LeaderRow so the podium / rows / expansion are shared.
type Metric = 'impact' | 'value'
type Palette = { key: string; label: string; color: string }[]
const paletteFor = (m: Metric): Palette => (m === 'value' ? VALUE_COMPONENTS : COMPOSITE_COMPONENTS)

interface LeaderRow {
  player_id: number; player_name?: string | null; team_abbrev?: string | null; position?: string | null
  total: number; total_sd?: number | null; war?: number | null
  components: { key: string; value: number }[]
  sublabel: string
}

function mapImpact(r: ArchetypeRankRow, overall: boolean): LeaderRow {
  const base = `${r.position ?? ''}${r.team_abbrev ? ` · ${r.team_abbrev}` : ''}`
  const sublabel = overall
    ? (r.primary_archetype ? `${base} · ${r.primary_archetype}` : base)
    : `${base} · ${(r.archetype_weight * 100).toFixed(0)}% match`
  return {
    player_id: r.player_id, player_name: r.player_name, team_abbrev: r.team_abbrev, position: r.position,
    total: r.composite_total, total_sd: r.composite_total_sd ?? null, components: r.components, sublabel,
  }
}
function mapValue(r: ValueRankingRow): LeaderRow {
  const base = `${r.position ?? ''}${r.team_abbrev ? ` · ${r.team_abbrev}` : ''}`
  return {
    player_id: r.player_id, player_name: r.player_name, team_abbrev: r.team_abbrev, position: r.position,
    total: r.gar, total_sd: r.gar_sd ?? null, war: r.war, components: r.components,
    sublabel: `${base} · ${r.war >= 0 ? '+' : ''}${r.war.toFixed(1)} WAR`,
  }
}
function segmentsFor(row: LeaderRow, palette: Palette): StackSegment[] {
  const m = new Map(row.components.map((c) => [c.key, c.value]))
  return palette.map((c) => ({ key: c.key, label: c.label, value: m.get(c.key) ?? 0, color: c.color }))
}

/* ============================================================================
   Expandable player card — middle-ground overview between the row and the full page
   ============================================================================ */

/** One RAPM impact bar (per-60, centred at 0) with an uncertainty whisker + percentile. */
function RapmBar({ label, value, sd, pctl }: { label: string; value: number; sd?: number | null; pctl?: number | null }) {
  const D = 0.6                                    // ± domain for EV impact /60
  const x = (v: number) => ((Math.max(-D, Math.min(D, v)) + D) / (2 * D)) * 100
  const zero = x(0)
  return (
    <div className="pexp-rapm__row">
      <span className="pexp-rapm__label">{label}</span>
      <span className="pexp-rapm__track">
        <span className="pexp-rapm__zero" style={{ left: `${zero}%` }} />
        {sd != null && (
          <span className="pexp-rapm__sd" style={{ left: `${x(value - sd)}%`, width: `${Math.max(0, x(value + sd) - x(value - sd))}%` }} />
        )}
        <span className={`pexp-rapm__bar ${value >= 0 ? 'pexp-rapm__bar--pos' : 'pexp-rapm__bar--neg'}`}
          style={{ left: `${Math.min(zero, x(value))}%`, width: `${Math.abs(x(value) - zero)}%` }} />
      </span>
      <span className="pexp-rapm__val">{value >= 0 ? '+' : ''}{value.toFixed(2)}{pctl != null && <small> · {Math.round(pctl)}th</small>}</span>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="pexp-stat"><span className="pexp-stat__v">{value}</span><span className="pexp-stat__l">{label}</span></div>
}

/** Inline expansion: basics + stats + RAPM + skill radar + link to full page. */
function PlayerExpansion({ row, season, onCollapse }: { row: LeaderRow; season: string; onCollapse?: () => void }) {
  const [radar, setRadar] = useState<PlayerRadar | null>(null)
  const [summary, setSummary] = useState<PlayerSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true); setRadar(null); setSummary(null)
    Promise.allSettled([getPlayerRadar(row.player_id, season), getPlayerSummary(row.player_id, season)])
      .then(([r, s]) => {
        if (!active) return
        if (r.status === 'fulfilled') setRadar(r.value)
        if (s.status === 'fulfilled') setSummary(s.value)
        setLoading(false)
      })
    return () => { active = false }
  }, [row.player_id, season])

  const labels = radar ? playerLabelsFromRadar(radar) : null
  const offSpoke = radar?.spokes.find((s) => s.key === 'ev_off_impact')
  const defSpoke = radar?.spokes.find((s) => s.key === 'ev_def_impact')

  return (
    <div className="pexp">
      {onCollapse && (
        <button className="pexp__collapse" onClick={onCollapse} aria-label="Collapse">
          <ChevronDown size={16} /> Collapse
        </button>
      )}
      <div className="pexp__main">
        {/* basics + stats + RAPM */}
        <div className="pexp__col">
          <div className="pexp__header">
            <div className="pexp__head">
              <Avatar id={row.player_id} team={row.team_abbrev} name={row.player_name} size={56} />
              <div className="pexp__id">
                <span className="pexp__name">{row.player_name ?? row.player_id}</span>
                <span className="pexp__meta">{row.position}{row.team_abbrev ? ` · ${row.team_abbrev}` : ''}{labels?.overall ? ` · ${labels.overall}` : ''}</span>
                {labels && (
                  <div className="pexp__chips">
                    {labels.offensive && <span className="pexp__chip">{labels.offensive}</span>}
                    {labels.defensive && <span className="pexp__chip pexp__chip--def">{labels.defensive}</span>}
                  </div>
                )}
              </div>
            </div>
            {labels?.descriptor && <p className="pexp__descriptor">{labels.descriptor}</p>}
          </div>

          {loading && !summary ? <SkeletonLoader /> : summary && (
            <div className="pexp__statwrap">
            <div className="pexp__stats">
              <Stat label="GP" value={`${summary.games_played}`} />
              <Stat label="5v5 TOI" value={summary.toi_per_gp != null ? summary.toi_per_gp.toFixed(1) : '—'} />
              <Stat label="G/60" value={summary.goals_per60 != null ? summary.goals_per60.toFixed(2) : '—'} />
              <Stat label="A/60" value={summary.assists_per60 != null ? summary.assists_per60.toFixed(2) : '—'} />
              <Stat label="P/60" value={summary.points_per60 != null ? summary.points_per60.toFixed(2) : '—'} />
              <Stat label="xGF%" value={summary.xgf_pct != null ? (summary.xgf_pct * 100).toFixed(1) : '—'} />
            </div>
            <div className="pexp__stats-note">Season totals · 5v5 rates</div>
            </div>
          )}

          {(offSpoke || defSpoke) && (
            <div className="pexp__block">
              <div className="pexp__block-title">Isolated impact (RAPM, xG/60)</div>
              {offSpoke && <RapmBar label="EV Offense" value={offSpoke.value} sd={offSpoke.sd} pctl={offSpoke.percentile} />}
              {defSpoke && <RapmBar label="EV Defense" value={defSpoke.value} sd={defSpoke.sd} pctl={defSpoke.percentile} />}
            </div>
          )}

          <Link className="pexp__link" to={`/players/${row.player_id}`}>
            View full profile <ArrowRight size={15} />
          </Link>
        </div>

        {/* skill radar */}
        <div className="pexp__radar">
          {loading && !radar ? <SkeletonLoader />
            : radar ? <SkillRadar spokes={radar.spokes} baseline={radar.baseline} size={360} />
            : <p className="players__msg">No radar for this player.</p>}
        </div>
      </div>
    </div>
  )
}

/** Compact podium (top-3) card. */
function PodiumCard({ r, rank, expanded, domain, palette, unit, onToggle }: {
  r: LeaderRow; rank: number; expanded: boolean; domain: [number, number];
  palette: Palette; unit: string; onToggle: (id: number) => void
}) {
  return (
    <button className={`ptop${expanded ? ' ptop--active' : ''}`}
      onClick={() => onToggle(r.player_id)} aria-expanded={expanded}>
      <span className={`ptop__rank ptop__rank--${rank}`}>{rank}</span>
      <Avatar id={r.player_id} team={r.team_abbrev} name={r.player_name} size={72} />
      <span className="ptop__name">{r.player_name ?? r.player_id}</span>
      <span className="ptop__meta">{r.sublabel}</span>
      <span className="ptop__total">{fmt(r.total)}<small> {unit}</small></span>
      <div className="ptop__bar">
        <ComponentStackBar segments={segmentsFor(r, palette)} total={r.total} domain={domain} se={r.total_sd ?? undefined} />
      </div>
    </button>
  )
}

/* ============================================================================
   Leaderboard content (driven by toolbar position/archetype)
   ============================================================================ */
function Leaderboard({ metric, position, archetype, season }: { metric: Metric; position: Pos; archetype: string; season: string }) {
  const [rows, setRows] = useState<LeaderRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const overall = archetype === 'ALL' || metric === 'value'  // GAR has no archetype ranking
  const palette = paletteFor(metric)
  const unit = metric === 'value' ? 'GAR' : 'value'
  const toggle = (id: number) => setExpandedId((cur) => (cur === id ? null : id))

  useEffect(() => {
    let active = true
    setRows(null); setError(null); setExpandedId(null)
    const req: Promise<LeaderRow[]> = metric === 'value'
      ? getValueRankings(position, season).then((rs) => rs.map(mapValue))
      : (overall ? getOverallLeaders(position, season, 50) : getArchetypeRanking(archetype, season, 50))
          .then((rs) => rs.map((r) => mapImpact(r, overall)))
    req.then((d) => active && setRows(d)).catch(() => active && setError('Could not load rankings.'))
    return () => { active = false }
  }, [metric, position, archetype, overall, season])

  const top = rows?.slice(0, 3) ?? []
  const rest = rows?.slice(3) ?? []

  // Asymmetric scale from the actual data (incl. whisker) so bars fill rightward. The podium
  // and the list get SEPARATE scales — otherwise the list is squashed against the #1 outlier
  // and wastes the right half. Each group's bars fill its own range.
  const [podiumDomain, listDomain] = useMemo<[[number, number], [number, number]]>(() => {
    const calc = (rs: LeaderRow[]): [number, number] => {
      let lo = 0, hi = 1
      for (const r of rs) {
        let posSum = 0, negSum = 0
        for (const c of r.components) (c.value >= 0 ? (posSum += c.value) : (negSum += c.value))
        const sd = r.total_sd ?? 0
        hi = Math.max(hi, posSum, r.total + sd)
        lo = Math.min(lo, negSum, r.total - sd)
      }
      return [lo, hi * 1.03]
    }
    const all = rows ?? []
    const restRows = all.slice(3)
    return [calc(all.slice(0, 3)), calc(restRows.length ? restRows : all.slice(0, 3))]
  }, [rows])
  const listTicks = niceTicks(listDomain)

  const subtitle = metric === 'value'
    ? 'Ranked by GAR — actual goals above replacement (“what happened”). Goals-based, so it includes shooting luck by design; the bar breaks GAR into components.'
    : overall
      ? 'Ranked by Impact — RAPM-based value above replacement (“what tends to repeat”). Each bar breaks the value into its components; the tick is the total, the line its uncertainty.'
      : 'Ranked within archetype by Impact (RAPM-based value). Each bar breaks the value into its components; the tick is the total, the line its uncertainty.'

  return (
    <section className="players__board">
      <div className="players__board-head">
        <p className="players__subtitle">{subtitle}</p>
        {rows && <span className="players__count">{rows.length} {rows.length === 1 ? 'player' : 'players'}</span>}
      </div>

      {error && <p className="players__msg">{error}</p>}
      {!rows && !error && <SkeletonLoader />}
      {rows && rows.length === 0 && <p className="players__msg">No qualifying players here.</p>}

      {rows && rows.length > 0 && (
        <>
          <div className="players__key">
            <div className="players__key-components">
              {palette.map((c) => (
                <span key={c.key} className="players__legend-item">
                  <span className="players__swatch" style={{ background: c.color }} />{c.label}
                </span>
              ))}
            </div>
            <div className="players__key-marks">
              <span className="players__legend-item"><span className="key-mark key-mark--tick" />total {unit}</span>
              <span className="players__legend-item"><span className="key-mark key-mark--whisker" />uncertainty</span>
              <span className="players__key-hint">Bars stack each component’s value (negatives extend left). Hover a bar for the full breakdown.</span>
            </div>
          </div>

          {(() => {
            const expIdx = top.findIndex((r) => r.player_id === expandedId)
            if (expIdx === -1) {
              return (
                <div className="players__podium">
                  {top.map((r, i) => (
                    <PodiumCard key={r.player_id} r={r} rank={i + 1} expanded={false}
                      domain={podiumDomain} palette={palette} unit={unit} onToggle={toggle} />
                  ))}
                </div>
              )
            }
            const exp = top[expIdx]
            const others = top.map((r, i) => ({ r, rank: i + 1 })).filter((x) => x.r.player_id !== exp.player_id)
            return (
              <div className="players__podium-expanded">
                <PlayerExpansion row={exp} season={season} onCollapse={() => toggle(exp.player_id)} />
                <div className="players__podium-others">
                  {others.map(({ r, rank }) => (
                    <PodiumCard key={r.player_id} r={r} rank={rank} expanded={false}
                      domain={podiumDomain} palette={palette} unit={unit} onToggle={toggle} />
                  ))}
                </div>
              </div>
            )
          })()}

          {rest.length > 0 && (
            <>
              <div className="players__rows">
                {rest.map((r, i) => (
                  <Fragment key={r.player_id}>
                    <button className={`prow${expandedId === r.player_id ? ' prow--active' : ''}`}
                      onClick={() => toggle(r.player_id)} aria-expanded={expandedId === r.player_id}>
                      <span className="prow__rank">{i + 4}</span>
                      <Avatar id={r.player_id} team={r.team_abbrev} name={r.player_name} size={38} />
                      <span className="prow__id">
                        <span className="prow__name">{r.player_name ?? r.player_id}</span>
                        <span className="prow__meta">{r.position}{r.team_abbrev ? ` · ${r.team_abbrev}` : ''}</span>
                      </span>
                      <span className="prow__bar">
                        <ComponentStackBar segments={segmentsFor(r, palette)} total={r.total} domain={listDomain} se={r.total_sd ?? undefined} gridlines={listTicks} />
                      </span>
                      <span className="prow__total">{fmt(r.total)}</span>
                    </button>
                    {expandedId === r.player_id && <PlayerExpansion row={r} season={season} />}
                  </Fragment>
                ))}
              </div>
              <div className="players__axis" aria-hidden="true">
                <div className="players__axis-track">
                  {listTicks.map((v) => (
                    <span key={v} className="players__axis-tick" style={{ left: `${tickPct(v, listDomain)}%` }}>
                      {v > 0 ? `+${v}` : v}
                    </span>
                  ))}
                </div>
              </div>
            </>
          )}
        </>
      )}
    </section>
  )
}

/* ============================================================================
   Divergence board
   ============================================================================ */
function DivBar({ label, z, tone }: { label: string; z: number; tone: 'trust' | 'value' }) {
  const clamped = Math.max(-3, Math.min(3, z))
  const pct = ((clamped + 3) / 6) * 100
  const left = Math.min(pct, 50)
  const width = Math.abs(pct - 50)
  return (
    <div className={`dbar dbar--${tone}`}>
      <span className="dbar__label">{label}</span>
      <span className="dbar__track">
        <span className="dbar__zero" />
        <span className="dbar__fill" style={{ left: `${left}%`, width: `${width}%` }} />
        <span className="dbar__dot" style={{ left: `${pct}%` }} />
      </span>
      <span className="dbar__val">{z >= 0 ? '+' : ''}{z.toFixed(1)}σ</span>
    </div>
  )
}

/** One expandable divergence entry: compact rank row, opens to the trust/value bars + explanation. */
function DivRow({ rank, r, defaultOpen }: { rank: number; r: DivergenceBoardRow; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(!!defaultOpen)
  return (
    <div className={`divrow${open ? ' divrow--open' : ''}`}>
      <button className="divrow__head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="divrow__rank">{rank}</span>
        <Avatar id={r.player_id} team={r.team_abbrev} name={r.player_name} size={34} />
        <span className="divrow__id">
          <span className="divrow__name">{r.player_name ?? r.player_id}</span>
          <span className="divrow__meta">{r.position}{r.team_abbrev ? ` · ${r.team_abbrev}` : ''}</span>
        </span>
        <span className="divrow__sigma">{Math.abs(r.divergence).toFixed(1)}σ</span>
        <ChevronDown size={15} className={`divrow__chev${open ? ' divrow__chev--open' : ''}`} />
      </button>
      {open && (
        <div className="divrow__detail">
          <DivBar label="Coach trust" z={r.trust_z} tone="trust" />
          <DivBar label="Isolated value" z={r.composite_z} tone="value" />
          <p className="divrow__explain">{r.explanation}</p>
          <Link to={`/players/${r.player_id}`} className="divrow__link">View player →</Link>
        </div>
      )}
    </div>
  )
}

function DivColumn({ title, caption, rows }: { title: string; caption: string; rows: DivergenceBoardRow[] }) {
  return (
    <div className="divcol">
      <div className="divcol__head">
        <h3 className="divcol__title">{title}</h3>
        <p className="divcol__caption">{caption}</p>
      </div>
      <div className="divcol__list">
        {rows.length === 0
          ? <p className="players__msg" style={{ padding: 'var(--space-5)' }}>No qualifying players.</p>
          : rows.map((r, i) => <DivRow key={r.player_id} rank={i + 1} r={r} defaultOpen={i === 0} />)}
      </div>
    </div>
  )
}

function DivergenceBoard() {
  const [rows, setRows] = useState<DivergenceBoardRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    getDivergenceBoard().then((d) => active && setRows(d)).catch(() => active && setError('Could not load board.'))
    return () => { active = false }
  }, [])
  if (error) return <p className="players__msg">{error}</p>
  if (!rows) return <SkeletonLoader />
  // each side ranked by the size of the disagreement
  const over = rows.filter((r) => r.side === 'trusted_over_value').sort((a, b) => b.divergence - a.divergence)
  const under = rows.filter((r) => r.side === 'value_over_trust').sort((a, b) => a.divergence - b.divergence)
  return (
    <section className="players__divergence">
      <p className="players__subtitle">
        Where coaching deployment (trust) and isolated value (composite) most disagree, by
        position-standardized z-scores. Each side is ranked by the size of the gap; expand a row
        for the breakdown. Explanations are generated from the underlying numbers.
      </p>

      <div className="div2col">
        <DivColumn
          title="Trusted beyond their value"
          caption="Heavy deployment the isolated numbers don’t reward — the eye-test-vs-analytics tension."
          rows={over}
        />
        <DivColumn
          title="Value beyond their deployment"
          caption="Strong isolated value in limited or sheltered roles — often offense not trusted defensively."
          rows={under}
        />
      </div>
    </section>
  )
}

/* ============================================================================
   Page
   ============================================================================ */
export default function Players() {
  const navigate = useNavigate()
  const [view, setView] = useState<'leaderboard' | 'divergence'>('leaderboard')
  const [metric, setMetric] = useState<Metric>('impact')
  const [position, setPosition] = useState<Pos>('ALL')
  const [archetype, setArchetype] = useState<string>('ALL')
  const [season, setSeason] = useState<string>(SEASONS[0])

  const changePosition = (p: Pos) => { setPosition(p); setArchetype('ALL') }
  const changeArchetype = (a: string) => {
    if (a !== 'ALL' && position === 'ALL') setPosition(archGroup(a))
    setArchetype(a)
  }

  const archOptions = useMemo<SelectOption[]>(() => {
    const list = position === 'F' ? ARCHETYPES.F : position === 'D' ? ARCHETYPES.D : [...ARCHETYPES.F, ...ARCHETYPES.D]
    return [{ value: 'ALL', label: 'All archetypes' }, ...list.map((a) => ({ value: a, label: a }))]
  }, [position])

  return (
    <PageLayout>
      <div className="players">
        <PageHeader
          title="Players"
          subtitle="Rank the league’s skaters by value, see where coaches and the models disagree, or jump straight to anyone."
        />

        <div className="players__toolbar">
          <div className="players__toolbar-top">
            <Tabs
              options={[
                { value: 'leaderboard', label: 'Leaderboard' },
                { value: 'divergence', label: 'Divergence Board' },
              ]}
              value={view}
              onChange={(v) => setView(v as 'leaderboard' | 'divergence')}
            />
            <div className="players__toolbar-search">
              <PlayerPicker placeholder="Find any player…" onSelect={(p) => navigate(`/players/${p.player_id}`)} />
            </div>
          </div>

          {view === 'leaderboard' && (
            <div className="players__toolbar-filters">
              <Tabs
                options={[
                  { value: 'impact', label: 'Play Driving' },
                  { value: 'value', label: 'Production' },
                ]}
                value={metric}
                onChange={(v) => setMetric(v as Metric)}
              />
              <Tabs
                options={[
                  { value: 'ALL', label: 'All skaters' },
                  { value: 'F', label: 'Forwards' },
                  { value: 'D', label: 'Defense' },
                ]}
                value={position}
                onChange={(v) => changePosition(v as Pos)}
              />
              <div className="players__toolbar-right">
                {metric === 'impact' && (
                  <Select value={archetype} ariaLabel="Archetype" options={archOptions} onChange={changeArchetype} />
                )}
                <Select value={season} ariaLabel="Season"
                  options={SEASONS.map((s) => ({ value: s, label: s }))} onChange={setSeason} />
              </div>
            </div>
          )}
        </div>

        {view === 'leaderboard'
          ? <Leaderboard metric={metric} position={position} archetype={archetype} season={season} />
          : <DivergenceBoard />}
      </div>
    </PageLayout>
  )
}
