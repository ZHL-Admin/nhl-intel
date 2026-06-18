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
import { useState, useEffect, useMemo, Fragment } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown } from 'lucide-react'
import PlayerRowExpansion from '../components/players/PlayerRowExpansion'
import DeploymentBoard from '../components/players/DeploymentBoard'
import {
  PageLayout, PageHeader, ComponentStackBar, SkeletonLoader, Tabs, Select, PlayerPicker, PlayerAvatar,
} from '../components/common'
import type { StackSegment } from '../components/common'
import { getOverallLeaders } from '../api/players'
import { getValueRankings, type ValueSort } from '../api/rankings'
import { ArchetypeRankRow, ValueRankingRow } from '../api/types'
import { COMPOSITE_COMPONENTS, VALUE_COMPONENTS, GOALIE_VALUE_COMPONENTS } from '../config/metrics'
import './Players.css'

type Show = 'all' | 'F' | 'D' | 'G'
type RankBy = 'war' | 'rapm' | 'gar'
type Palette = { key: string; label: string; color: string }[]
// seasons with value + composite data (newest first)
const SEASONS = ['2025-26', '2024-25', '2023-24', '2022-23', '2021-22']

// Rows + divergence board reuse the shared headshot component (one implementation site-wide).
const Avatar = PlayerAvatar

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
   The simple magnitude bar for the mixed list — single tone, entity-kind tinted, with a PROMINENT
   uncertainty band rendered as an error bar (translucent range + end caps + point tick). The wide
   goalie bands visibly overlap the rows around them, so the order reads as soft / tier-level.
   ============================================================================ */
function MagnitudeBar({ row, max }: { row: Row; max: number }) {
  const x = (v: number) => (max > 0 ? Math.max(0, Math.min(100, (v / max) * 100)) : 0)
  const v = x(row.value)
  const sd = row.band ?? 0
  const lo = x(row.value - sd)
  const hi = x(row.value + sd)
  return (
    <span className={`magbar magbar--${row.entityKind}`}>
      <span className="magbar__fill" style={{ width: `${v}%` }} />
      {sd > 0 && (
        <>
          <span className="magbar__range" style={{ left: `${lo}%`, width: `${Math.max(0, hi - lo)}%` }} />
          <span className="magbar__cap" style={{ left: `${lo}%` }} />
          <span className="magbar__cap" style={{ left: `${hi}%` }} />
        </>
      )}
      <span className="magbar__mark" style={{ left: `${v}%` }} />
    </span>
  )
}

/* ============================================================================
   Leaderboard
   ============================================================================ */
function Leaderboard({ show, rankBy, season, sort, setSort }: {
  show: Show; rankBy: RankBy; season: string; sort: ValueSort; setSort: (s: ValueSort) => void
}) {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)   // one open at a time
  const toggle = (id: number) => setExpandedId((cur) => (cur === id ? null : id))

  // Escape closes the open preview
  useEffect(() => {
    if (expandedId == null) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpandedId(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expandedId])

  // resolve the lens that actually applies to the current scope
  const effRankBy: RankBy = show === 'all' ? 'war' : (show === 'G' && rankBy === 'rapm' ? 'war' : rankBy)
  const mixed = show === 'all'
  const palette: Palette = mixed ? [] : show === 'G' ? GOALIE_VALUE_COMPONENTS
    : effRankBy === 'rapm' ? COMPOSITE_COMPONENTS : VALUE_COMPONENTS
  // the confidence/point order applies to the value lenses (GAR/WAR), not the RAPM composite lens
  const sortable = effRankBy !== 'rapm'

  useEffect(() => {
    let active = true
    setRows(null); setError(null); setExpandedId(null)
    let req: Promise<Row[]>
    if (mixed) {
      req = getValueRankings('all', 'ALL', season, 60, sort).then((rs) => rs.map((r) => mapValueRow(r, 'WAR', r.war, r.war_sd)))
    } else if (show === 'G') {
      const unit = effRankBy === 'gar' ? 'GAR' : 'WAR'
      req = getValueRankings('goalies', 'ALL', season, 60, sort).then((rs) =>
        rs.map((r) => mapValueRow(r, unit, effRankBy === 'gar' ? r.gar : r.war, effRankBy === 'gar' ? r.gar_sd : r.war_sd)))
    } else if (effRankBy === 'rapm') {
      req = getOverallLeaders(show, season, 60).then((rs: ArchetypeRankRow[]) => rs.map((r) => ({
        id: r.player_id, name: r.player_name, team: r.team_abbrev, position: r.position,
        entityKind: 'skater' as const, value: r.composite_total, unit: 'value',
        band: r.composite_total_sd ?? null, components: r.components, war: null,
      })))
    } else {
      const unit = effRankBy === 'gar' ? 'GAR' : 'WAR'
      req = getValueRankings('skaters', show, season, 60, sort).then((rs) =>
        rs.map((r) => mapValueRow(r, unit, effRankBy === 'gar' ? r.gar : r.war, effRankBy === 'gar' ? r.gar_sd : r.war_sd)))
    }
    req.then((d) => active && setRows(d)).catch(() => active && setError('Could not load rankings.'))
    return () => { active = false }
  }, [show, effRankBy, season, mixed, sort])

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

  // confidence note appended to the value-lens captions so the order is honest about accounting
  // for uncertainty (goalie bands are wide; a confident skater outranks a noisy goalie of equal WAR)
  const confNote = sortable && sort === 'confidence'
    ? ' Ordered by confidence-adjusted value (point − ½ sd), so wide-band goalies rank by what we’re confident they provided.'
    : ''
  const caption = (mixed
    ? 'Wins Above Replacement (WAR) — skaters and goalies on one scale; goalie estimates are reliability-shrunk and bands are wide, so the order is soft.'
    : show === 'G'
      ? `Goalie ${effRankBy === 'gar' ? 'GAR — reliability-shrunk goals saved above a replacement backup' : 'WAR — goals saved above replacement, on the shared win scale'}. Goaltending is low-signal: bands are wide, read tiers not exact ranks.`
      : effRankBy === 'rapm'
        ? 'Play-Driving — RAPM-based value above replacement (“what tends to repeat”). The bar breaks value into components.'
        : `${effRankBy === 'gar' ? 'Production — GAR, goals above replacement (“what happened”)' : 'Total value — WAR, on the shared win scale'}. The bar breaks value into components.`) + confNote

  return (
    <section className="players__board">
      {error && <p className="players__msg">{error}</p>}
      {!rows && !error && <SkeletonLoader />}
      {rows && rows.length === 0 && <p className="players__msg">No qualifying players here.</p>}

      {rows && rows.length > 0 && (
        <>
          <div className="players__caption-row">
            <p className="players__caption">{caption}</p>
            {sortable && (
              <span className="players__order">
                <Tabs
                  options={[
                    { value: 'confidence', label: 'Confidence-adjusted' },
                    { value: 'point', label: 'Point estimate' },
                  ]}
                  value={sort}
                  onChange={(v) => setSort(v as ValueSort)}
                />
              </span>
            )}
            {!mixed && <ColorsLegend palette={palette} />}
            <span className="players__count">{rows.length}</span>
          </div>

          <div className="players__rows">
            {rows.map((r, i) => {
              const open = expandedId === r.id
              return (
                <Fragment key={r.id}>
                  <button className={`prow${i === 0 ? ' prow--lead' : ''}${open ? ' prow--active' : ''}`}
                    onClick={() => toggle(r.id)} aria-expanded={open}>
                    <span className="prow__rank">{i + 1}</span>
                    <Avatar id={r.id} team={r.team} name={r.name} size={36} />
                    <span className="prow__id">
                      <span className="prow__name">{r.name ?? r.id}</span>
                      <span className="prow__meta--header">
                        <span className={`prow__gtag--${r.entityKind} prow__gtag`}>{r.position}</span>
                        <span className="prow__meta">{r.team ? `${r.team}` : ''}</span>
                      </span>
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
                    <ChevronDown size={16} className={`prow__chev${open ? ' prow__chev--open' : ''}`} aria-hidden="true" />
                  </button>
                  {open && (
                    <PlayerRowExpansion
                      target={{ id: r.id, name: r.name, team: r.team, position: r.position, entityKind: r.entityKind }}
                      season={season}
                    />
                  )}
                </Fragment>
              )
            })}
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
        Legend <ChevronDown size={13} className={open ? 'players__colors-chev--open' : ''} />
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

/* The "Divergence board" tab is now a deployment-efficiency tool (actual vs justified usage with a
   situation lens) — its own component. */

/* ============================================================================
   Page
   ============================================================================ */
export default function Players() {
  const navigate = useNavigate()
  const [view, setView] = useState<'leaderboard' | 'divergence'>('leaderboard')
  const [show, setShow] = useState<Show>('all')
  const [rankBy, setRankBy] = useState<RankBy>('war')
  const [season, setSeason] = useState<string>(SEASONS[0])
  const [sort, setSort] = useState<ValueSort>('confidence')   // confidence-adjusted order by default
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

        {/* consolidated control card (matches the Rankings page) */}
        <div className="players__toolbar">
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
                    actual goals (“what happened”). Goalie value is goals saved above a backup, but
                    goaltending is low-signal year to year, so goalie estimates are regressed toward
                    the mean by their measured reliability (more shots → less regression) and their
                    bands stay wide. The mixed board orders by confidence-adjusted value so a
                    tight-band skater isn’t out-ranked by a noisy goalie of equal point estimate.
                  </p>
                )}
              </div>
            </>
          )}
        </div>

        {view === 'leaderboard'
          ? <Leaderboard show={show} rankBy={rankBy} season={season} sort={sort} setSort={setSort} />
          : <DeploymentBoard />}
      </div>
    </PageLayout>
  )
}
