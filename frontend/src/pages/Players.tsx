/**
 * Players index — one consolidated control region + a single uniform ranked list.
 *
 * Top: a short title, a mode toggle (Leaderboard | Divergence board) + search, then ONE control
 * bar — Show [All | Forwards | Defense | Goalies], Rank by [Total value (WAR) | Play-driving (RAPM)
 * | Production (GAR)], and the season. The list below is uniform rows (no podium): rank · avatar ·
 * name · bar · value.
 *
 * Cross-position rule: the mixed "All" list sorts by WAR (the only cross-position-comparable unit)
 * and uses a SIMPLE magnitude bar — skater and goalie component vocabularies don't mix in one
 * column. Filtered scopes (Forwards/Defense/Goalies) show the rich component breakdown with the
 * right palette and expose the colour legend. Goalie rows carry a "G" tag and a visibly wider
 * uncertainty band (goaltending is less stable; its cross-position order is soft).
 */
import { useState, useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronDown } from 'lucide-react'
import {
  PageLayout, PageHeader, ComponentStackBar, SkeletonLoader, Tabs, Select, PlayerPicker,
} from '../components/common'
import type { StackSegment } from '../components/common'
import { getOverallLeaders, getDivergenceBoard } from '../api/players'
import { getValueRankings } from '../api/rankings'
import { ArchetypeRankRow, DivergenceBoardRow, ValueRankingRow } from '../api/types'
import { COMPOSITE_COMPONENTS, VALUE_COMPONENTS, GOALIE_VALUE_COMPONENTS } from '../config/metrics'
import { getPlayerHeadshotUrl, getTeamLogoUrl } from '../utils/teams'
import './Players.css'

type Show = 'all' | 'F' | 'D' | 'G'
type RankBy = 'war' | 'rapm' | 'gar'
type Palette = { key: string; label: string; color: string }[]
// seasons with value + composite data (newest first)
const SEASONS = ['2025-26', '2024-25', '2023-24', '2022-23', '2021-22']

function initials(name?: string | null): string {
  if (!name) return '—'
  const p = name.trim().split(/\s+/)
  return ((p[0]?.[0] ?? '') + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase() || '—'
}

/** Round headshot with a team-logo badge and initials fallback. */
function Avatar({ id, team, name, size = 38 }: { id: number; team?: string | null; name?: string | null; size?: number }) {
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

/** Unified row across all data sources (skater value / skater impact / goalie value / mixed). */
interface Row {
  id: number; name?: string | null; team?: string | null; position?: string | null
  entityKind: 'skater' | 'goalie'
  value: number          // the headline number on the right (WAR / GAR / composite value)
  unit: string           // 'WAR' | 'GAR' | 'value'
  band?: number | null   // sd of the headline value (the uncertainty whisker)
  components: { key: string; value: number }[]
  war?: number | null    // magnitude for the mixed simple bar
}

function segmentsFor(row: Row, palette: Palette): StackSegment[] {
  const m = new Map(row.components.map((c) => [c.key, c.value]))
  return palette.map((c) => ({ key: c.key, label: c.label, value: m.get(c.key) ?? 0, color: c.color }))
}

const mapValueRow = (r: ValueRankingRow, unit: string, value: number, band?: number | null): Row => ({
  id: r.player_id, name: r.player_name, team: r.team_abbrev, position: r.position,
  entityKind: r.entity_kind === 'goalie' ? 'goalie' : 'skater',
  value, unit, band, components: r.components, war: r.war,
})

/* ============================================================================
   The simple magnitude bar for the mixed list (single tone, entity-kind tinted, with a band)
   ============================================================================ */
function MagnitudeBar({ row, max }: { row: Row; max: number }) {
  const w = max > 0 ? Math.max(0, (row.value / max)) * 100 : 0
  const band = row.band ? (row.band / (max || 1)) * 100 : 0
  return (
    <span className={`magbar magbar--${row.entityKind}`}>
      <span className="magbar__fill" style={{ width: `${Math.min(100, w)}%` }} />
      {band > 0 && (
        <span className="magbar__band"
          style={{ left: `${Math.max(0, w - band)}%`, width: `${Math.min(100, w + band) - Math.max(0, w - band)}%` }} />
      )}
    </span>
  )
}

/* ============================================================================
   Leaderboard
   ============================================================================ */
function Leaderboard({ show, rankBy, season }: { show: Show; rankBy: RankBy; season: string }) {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  // resolve the lens that actually applies to the current scope
  const effRankBy: RankBy = show === 'all' ? 'war' : (show === 'G' && rankBy === 'rapm' ? 'war' : rankBy)
  const mixed = show === 'all'
  const palette: Palette = mixed ? [] : show === 'G' ? GOALIE_VALUE_COMPONENTS
    : effRankBy === 'rapm' ? COMPOSITE_COMPONENTS : VALUE_COMPONENTS

  useEffect(() => {
    let active = true
    setRows(null); setError(null)
    let req: Promise<Row[]>
    if (mixed) {
      req = getValueRankings('all', 'ALL', season, 60).then((rs) => rs.map((r) => mapValueRow(r, 'WAR', r.war, r.war_sd)))
    } else if (show === 'G') {
      const unit = effRankBy === 'gar' ? 'GAR' : 'WAR'
      req = getValueRankings('goalies', 'ALL', season, 60).then((rs) =>
        rs.map((r) => mapValueRow(r, unit, effRankBy === 'gar' ? r.gar : r.war, effRankBy === 'gar' ? r.gar_sd : r.war_sd)))
    } else if (effRankBy === 'rapm') {
      req = getOverallLeaders(show, season, 60).then((rs: ArchetypeRankRow[]) => rs.map((r) => ({
        id: r.player_id, name: r.player_name, team: r.team_abbrev, position: r.position,
        entityKind: 'skater' as const, value: r.composite_total, unit: 'value',
        band: r.composite_total_sd ?? null, components: r.components, war: null,
      })))
    } else {
      const unit = effRankBy === 'gar' ? 'GAR' : 'WAR'
      req = getValueRankings('skaters', show, season, 60).then((rs) =>
        rs.map((r) => mapValueRow(r, unit, effRankBy === 'gar' ? r.gar : r.war, effRankBy === 'gar' ? r.gar_sd : r.war_sd)))
    }
    req.then((d) => active && setRows(d)).catch(() => active && setError('Could not load rankings.'))
    return () => { active = false }
  }, [show, effRankBy, season, mixed])

  // shared scales: a symmetric component-bar domain (filtered) and a max for the magnitude bar (mixed)
  const { domain, maxMag } = useMemo(() => {
    let lo = 0, hi = 1, max = 1
    for (const r of rows ?? []) {
      let posSum = 0, negSum = 0
      for (const c of r.components) (c.value >= 0 ? (posSum += c.value) : (negSum += c.value))
      const sd = r.band ?? 0
      hi = Math.max(hi, posSum, r.value + sd); lo = Math.min(lo, negSum, r.value - sd)
      max = Math.max(max, (r.value ?? 0) + sd)
    }
    return { domain: [lo, hi * 1.03] as [number, number], maxMag: max }
  }, [rows])

  const caption = mixed
    ? 'Sorted by Wins Above Replacement (WAR) — skaters and goalies on one scale. Bars show magnitude; goalie order is soft (note the wider bands).'
    : show === 'G'
      ? `Sorted by goalie ${effRankBy === 'gar' ? 'GAR — goals saved above a replacement backup' : 'WAR — goals saved above replacement, on the shared win scale'}. Goaltending is less stable: bands are wide.`
      : effRankBy === 'rapm'
        ? 'Sorted by Play-Driving — RAPM-based value above replacement (“what tends to repeat”). The bar breaks value into components.'
        : `Sorted by ${effRankBy === 'gar' ? 'Production — GAR, goals above replacement (“what happened”)' : 'Total value — WAR, on the shared win scale'}. The bar breaks value into components.`

  return (
    <section className="players__board">
      {error && <p className="players__msg">{error}</p>}
      {!rows && !error && <SkeletonLoader />}
      {rows && rows.length === 0 && <p className="players__msg">No qualifying players here.</p>}

      {rows && rows.length > 0 && (
        <>
          <div className="players__caption-row">
            <p className="players__caption">{caption}</p>
            {!mixed && <ColorsLegend palette={palette} />}
            <span className="players__count">{rows.length}</span>
          </div>

          <div className="players__rows">
            {rows.map((r, i) => (
              <button key={r.id} className={`prow${i === 0 ? ' prow--lead' : ''}`}
                onClick={() => navigate(`/players/${r.id}`)}>
                <span className="prow__rank">{i + 1}</span>
                <Avatar id={r.id} team={r.team} name={r.name} size={36} />
                <span className="prow__id">
                  <span className="prow__name">
                    {r.name ?? r.id}
                    {r.entityKind === 'goalie' && <span className="prow__gtag">G</span>}
                  </span>
                  <span className="prow__meta">{r.position}{r.team ? ` · ${r.team}` : ''}</span>
                </span>
                <span className="prow__bar">
                  {mixed
                    ? <MagnitudeBar row={r} max={maxMag} />
                    : <ComponentStackBar segments={segmentsFor(r, palette)} total={r.value}
                        domain={domain} se={r.band ?? undefined} />}
                </span>
                <span className="prow__total">
                  <span className="prow__total-v">{fmt(r.value)}</span>
                  <span className="prow__total-u">{r.unit}</span>
                  {r.band != null && r.band > 0 && <span className="prow__total-band">± {r.band.toFixed(1)}</span>}
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  )
}

/** Inline, click-to-expand colour legend (only meaningful in a filtered, component-bar view). */
function ColorsLegend({ palette }: { palette: Palette }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="players__colors">
      <button className="players__colors-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        Colors <ChevronDown size={13} className={open ? 'players__colors-chev--open' : ''} />
      </button>
      {open && (
        <span className="players__legend">
          {palette.map((c) => (
            <span key={c.key} className="players__legend-item">
              <span className="players__swatch" style={{ background: c.color }} />{c.label}
            </span>
          ))}
        </span>
      )}
    </span>
  )
}

/* ============================================================================
   Divergence board (unchanged behaviour)
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
        <DivColumn title="Trusted beyond their value"
          caption="Heavy deployment the isolated numbers don’t reward — the eye-test-vs-analytics tension."
          rows={over} />
        <DivColumn title="Value beyond their deployment"
          caption="Strong isolated value in limited or sheltered roles — often offense not trusted defensively."
          rows={under} />
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
  const [show, setShow] = useState<Show>('all')
  const [rankBy, setRankBy] = useState<RankBy>('war')
  const [season, setSeason] = useState<string>(SEASONS[0])
  const [methodOpen, setMethodOpen] = useState(false)

  // Show and Rank-by are interdependent (only WAR is cross-position-comparable; RAPM is skater-only;
  // GAR isn't comparable across positions). Rather than disable buttons, keep every button clickable
  // and gently coerce the OTHER control to a valid combination, so the two always stay consistent.
  const changeShow = (s: Show) => {
    setShow(s)
    if (s === 'all') setRankBy('war')              // mixed list -> WAR is the only valid unit
    else if (s === 'G' && rankBy === 'rapm') setRankBy('war')  // goalies have no play-driving lens
  }
  const changeRankBy = (v: RankBy) => {
    setRankBy(v)
    // a position-specific lens can't apply to the mixed (or, for RAPM, goalie) scope — narrow to
    // a scope where it's meaningful instead of being inert.
    if (v === 'rapm' && !(show === 'F' || show === 'D')) setShow('F')
    else if (v === 'gar' && show === 'all') setShow('F')
  }

  return (
    <PageLayout>
      <div className="players">
        <PageHeader
          title="Players"
          subtitle="League-wide value, ranked. Filter, switch the lens, or search anyone."
        />

        {/* mode + search */}
        <div className="players__mode">
          <Tabs
            options={[
              { value: 'leaderboard', label: 'Leaderboard' },
              { value: 'divergence', label: 'Divergence board' },
            ]}
            value={view}
            onChange={(v) => setView(v as 'leaderboard' | 'divergence')}
          />
          <div className="players__search">
            <PlayerPicker placeholder="Find any player…" onSelect={(p) => navigate(`/players/${p.player_id}`)} />
          </div>
        </div>

        {view === 'leaderboard' && (
          <>
            {/* one consolidated control bar */}
            <div className="players__controls">
              <span className="players__control">
                <span className="players__control-lbl">Show</span>
                <Tabs
                  options={[
                    { value: 'all', label: 'All' }, { value: 'F', label: 'Forwards' },
                    { value: 'D', label: 'Defense' }, { value: 'G', label: 'Goalies' },
                  ]}
                  value={show}
                  onChange={(v) => changeShow(v as Show)}
                />
              </span>
              <span className="players__divider" />
              <span className="players__control">
                <span className="players__control-lbl">Rank by</span>
                <Tabs
                  options={[
                    { value: 'war', label: 'Total value', tag: 'WAR' },
                    { value: 'rapm', label: 'Play-driving', tag: 'RAPM' },
                    { value: 'gar', label: 'Production', tag: 'GAR' },
                  ]}
                  value={show === 'all' ? 'war' : (show === 'G' && rankBy === 'rapm' ? 'war' : rankBy)}
                  onChange={(v) => changeRankBy(v as RankBy)}
                />
              </span>
              <span className="players__controls-spacer" />
              <Select value={season} ariaLabel="Season"
                options={SEASONS.map((s) => ({ value: s, label: s }))} onChange={setSeason} />
            </div>

            {/* honest one-liner + methodology link */}
            <div className="players__methrow">
              <button className="players__methlink" onClick={() => setMethodOpen((o) => !o)} aria-expanded={methodOpen}>
                How we measure value
              </button>
              {methodOpen && (
                <p className="players__methnote">
                  GAR is goals above a freely-available replacement player; WAR = GAR ÷ 6 goals, the
                  one unit comparable across positions, so skaters and goalies share the mixed list.
                  Play-driving is the RAPM-based composite (“what tends to repeat”); Production is
                  actual goals (“what happened”). Goalie value is goals saved above a backup — wide
                  bands because goaltending regresses hard year to year.
                </p>
              )}
            </div>

            <Leaderboard show={show} rankBy={rankBy} season={season} />
          </>
        )}

        {view === 'divergence' && <DivergenceBoard />}
      </div>
    </PageLayout>
  )
}
