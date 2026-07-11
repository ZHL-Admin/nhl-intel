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
import { ChevronDown, ChevronLeft, ChevronRight, X } from 'lucide-react'
import PlayerRowExpansion from '../components/players/PlayerRowExpansion'
import DeploymentBoard, { DEPLOYMENT_SITUATIONS } from '../components/players/DeploymentBoard'
import {
  PageLayout, PageCard, SkeletonLoader, Tabs, Select, PlayerPicker, PlayerAvatar, TierBadge,
} from '../components/common'
import { getValueRankings } from '../api/rankings'
import { ValueRankingRow, PlayerSearchResult } from '../api/types'
import './Players.css'

type Show = 'all' | 'F' | 'D' | 'G'

// Separator label = tier label pluralized to the position group (e.g. "Elite defensemen").
const POS_PLURAL: Record<string, string> = { F: 'forwards', D: 'defensemen', G: 'goalies' }
function sepLabel(tierLabel: string, pos?: string | null): string {
  if (tierLabel === 'Elite') return `Elite ${POS_PLURAL[pos ?? ''] ?? 'players'}`
  return tierLabel.replace(/defenseman$/, 'defensemen').replace(/forward$/, 'forwards').replace(/goalie$/, 'goalies')
}
// seasons with value + composite data (newest first)
const SEASONS = ['2025-26', '2024-25', '2023-24', '2022-23', '2021-22']
const PAGE_SIZE = 50          // ranked rows per page
const FETCH_ALL = 1000        // one call pulls the whole qualifying pool (≤ ~750); we paginate client-side

/** The position-filter scope a searched player belongs to (goalie / defense / forward). */
const scopeOf = (pos?: string | null): Show => (pos === 'G' ? 'G' : pos === 'D' ? 'D' : 'F')

// Rows + divergence board reuse the shared headshot component (one implementation site-wide).
const Avatar = PlayerAvatar

const fmt = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}`

/** Unified row across all data sources (skater value / skater impact / goalie value / mixed). */
interface Row {
  id: number; name?: string | null; team?: string | null; position?: string | null
  entityKind: 'skater' | 'goalie'
  value: number          // assessed WAR — the reliability-shrunk estimate we rank + display by (M3.5)
  unit: string           // 'WAR'
  band?: number | null   // war_sd (from the assessment) — the ±1 sd interval
  tier?: string | null
  tierLabel?: string | null
}

const mapValueRow = (r: ValueRankingRow): Row => ({
  id: r.player_id, name: r.player_name, team: r.team_abbrev, position: r.position,
  entityKind: r.entity_kind === 'goalie' ? 'goalie' : 'skater',
  value: r.assessed_war ?? r.war, unit: 'WAR', band: r.war_sd,
  tier: r.tier, tierLabel: r.tier_label,
})

/* ============================================================================
   Shared-axis interval bar (M3.5): a thin track over the pool's WAR domain, a ±1 sd band, and a
   point dot at assessed WAR. Goalie bands are visibly wider (root-shrunk, low-signal), so the order
   reads as soft / tier-level. No filled magnitude bar; the number and the boundary share one axis.
   ============================================================================ */
function IntervalBar({ row, domain }: { row: Row; domain: [number, number] }) {
  const [lo, hi] = domain
  const x = (v: number) => (hi > lo ? Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100)) : 0)
  const sd = row.band ?? 0
  return (
    <span className={`ixbar ixbar--${row.entityKind}`}>
      <span className="ixbar__track" />
      {lo < 0 && <span className="ixbar__zero" style={{ left: `${x(0)}%` }} />}
      {sd > 0 && (
        <span className={`ixbar__band${row.entityKind === 'goalie' ? ' is-wide' : ''}`}
          style={{ left: `${x(row.value - sd)}%`, width: `${Math.max(0, x(row.value + sd) - x(row.value - sd))}%` }} />
      )}
      <span className="ixbar__dot" style={{ left: `${x(row.value)}%` }} />
    </span>
  )
}

/* ============================================================================
   Leaderboard
   ============================================================================ */
function Leaderboard({ show, season, jumpTarget, onJumpHandled, focusedId, onClearFocus }: {
  show: Show; season: string
  jumpTarget: PlayerSearchResult | null; onJumpHandled: () => void
  focusedId: number | null; onClearFocus: () => void
}) {
  const navigate = useNavigate()
  const [rows, setRows] = useState<Row[] | null>(null)
  const [rowsKey, setRowsKey] = useState<string | null>(null)  // the context the loaded rows belong to
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [expandedId, setExpandedId] = useState<number | null>(null)   // one open at a time
  const toggle = (id: number) => setExpandedId((cur) => (cur === id ? null : id))

  // Escape closes the open preview
  useEffect(() => {
    if (expandedId == null) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpandedId(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expandedId])

  const mixed = show === 'all'
  // identifies which (scope, season) the currently loaded rows came from — used to make the
  // search-jump wait for the right list before locating a player.
  const fetchKey = `${show}|${season}`

  useEffect(() => {
    let active = true
    setRows(null); setError(null); setExpandedId(null); setPage(0)
    const scope = mixed ? 'all' : show === 'G' ? 'goalies' : 'skaters'
    const position = (!mixed && show !== 'G') ? show : 'ALL'
    getValueRankings(scope, position, season, FETCH_ALL).then((rs) => rs.map(mapValueRow))
      .then((d) => { if (active) { setRows(d); setRowsKey(fetchKey) } })
      .catch(() => active && setError('Could not load rankings.'))
    return () => { active = false }
  }, [show, season, mixed, fetchKey])

  // SEARCH: once the rows for the right context have loaded, find the searched player. If they're
  // here, expand them (the focus filter below shows them as the only row); if they're in no ranked
  // list here (unqualified, or absent from the RAPM-composite pool), fall back to their full profile.
  useEffect(() => {
    if (!jumpTarget || !rows || rowsKey !== fetchKey) return
    if (rows.some((r) => r.id === jumpTarget.player_id)) {
      setExpandedId(jumpTarget.player_id)
    } else {
      navigate(`/players/${jumpTarget.player_id}`)
      onClearFocus()
    }
    onJumpHandled()
  }, [jumpTarget, rows, rowsKey, fetchKey, navigate, onJumpHandled, onClearFocus])

  // FOCUS: a search result is shown as the only row. Keep the focused player expanded whenever they
  // (re)appear in the loaded list (e.g. after a season change), so the result stays open on its own.
  useEffect(() => {
    if (focusedId != null && rows?.some((r) => r.id === focusedId)) setExpandedId(focusedId)
  }, [focusedId, rows])

  // shared WAR axis for the interval bars (symmetric enough to place the ±sd band + dot)
  const domain = useMemo(() => {
    let lo = 0, hi = 1
    for (const r of rows ?? []) { const sd = r.band ?? 0; hi = Math.max(hi, r.value + sd); lo = Math.min(lo, r.value - sd) }
    return [lo, hi * 1.03] as [number, number]
  }, [rows])
  // tier group sizes (the filtered-view separators' counts)
  const tierCounts = useMemo(() => {
    const m: Record<string, number> = {}
    for (const r of rows ?? []) if (r.tier) m[r.tier] = (m[r.tier] ?? 0) + 1
    return m
  }, [rows])

  // one-line caption (M3.5 item e): ranking key + band meaning + qualified count.
  const caption = mixed
    ? `Ranked by assessed WAR, the reliability-shrunk estimate — skaters and goalies on one scale. Bands show ±1 sd; goalie bands are wide, so the order is soft. ${rows?.length ?? 0} qualified.`
    : `Ranked by assessed WAR, the reliability-shrunk estimate${show === 'G' ? ' — goaltending is low-signal, read tiers not exact ranks' : ''}. Bands show ±1 sd. ${rows?.length ?? 0} qualified.`

  const nPages = rows ? Math.max(1, Math.ceil(rows.length / PAGE_SIZE)) : 1
  const safePage = Math.min(page, nPages - 1)
  const pageStart = safePage * PAGE_SIZE
  const pageRows = rows ? rows.slice(pageStart, pageStart + PAGE_SIZE) : []

  // A search result is shown on its own: when the focused player is present in the loaded list,
  // render only their row (keeping their true global rank) and hide the caption + pager.
  const focusedIdx = focusedId != null && rows ? rows.findIndex((r) => r.id === focusedId) : -1
  const isFocused = focusedIdx >= 0
  const displayRows = isFocused ? [rows![focusedIdx]] : pageRows
  const rankBase = isFocused ? focusedIdx : pageStart

  return (
    <section className="players__board">
      {error && <p className="players__msg">{error}</p>}
      {!rows && !error && <SkeletonLoader />}
      {rows && rows.length === 0 && <p className="players__msg">No qualifying players here.</p>}

      {rows && rows.length > 0 && (
        <>
          {isFocused && (
            <div className="players__focusbar">
              <span className="players__focusbar-lbl">
                Search result — showing <strong>{displayRows[0].name ?? displayRows[0].id}</strong> only
              </span>
              <button className="players__focusbar-clear" onClick={onClearFocus}>
                <X size={14} aria-hidden="true" /> Show all players
              </button>
            </div>
          )}
          {!isFocused && <div className="players__caption-row">
            <p className="players__caption">{caption}</p>
            <span className="players__count">{rows.length}</span>
          </div>}

          <div className="players__rows">
            {displayRows.map((r, i) => {
              const rank = rankBase + i   // global rank across all pages (0-based)
              const open = expandedId === r.id
              // Filtered view only: tier separator when the tier changes from the previous ranked row.
              const prevTier = rank > 0 ? rows![rank - 1].tier : null
              const sep = !mixed && r.tier && r.tier !== prevTier
              return (
                <Fragment key={r.id}>
                  {sep && (
                    <div className="players__tiersep">
                      {sepLabel(r.tierLabel ?? r.tier!, r.position)}
                      <span className="players__tiersep-n"> · {tierCounts[r.tier!] ?? 0}</span>
                    </div>
                  )}
                  <button id={`prow-${r.id}`}
                    className={`prow${rank === 0 ? ' prow--lead' : ''}${open ? ' prow--active' : ''}`}
                    onClick={() => toggle(r.id)} aria-expanded={open}>
                    <span className="prow__rank">{rank + 1}</span>
                    <Avatar id={r.id} team={r.team} name={r.name} size={36} />
                    <span className="prow__id">
                      <span className="prow__name">{r.name ?? r.id}</span>
                      <span className="prow__meta--header">
                        <span className={`prow__gtag--${r.entityKind} prow__gtag`}>{r.position}</span>
                        <span className="prow__meta">{r.team ? `${r.team}` : ''}</span>
                        {mixed && r.tierLabel && <TierBadge label={r.tierLabel} size="sm" />}
                      </span>
                    </span>
                    <span className="prow__bar"><IntervalBar row={r} domain={domain} /></span>
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

          {!isFocused && nPages > 1 && (
            <Pagination page={safePage} nPages={nPages} pageStart={pageStart}
              shown={pageRows.length} total={rows.length}
              onPage={(p) => { setPage(p); setExpandedId(null); window.scrollTo({ top: 0, behavior: 'smooth' }) }} />
          )}
        </>
      )}
    </section>
  )
}

/* ============================================================================
   Pagination — Prev / windowed page numbers / Next, with a "showing X–Y of N" readout.
   ============================================================================ */
function pageWindow(page: number, nPages: number): (number | '…')[] {
  const out: (number | '…')[] = []
  const add = (p: number) => out.push(p)
  const lo = Math.max(1, page - 1), hi = Math.min(nPages - 2, page + 1)
  add(0)
  if (lo > 1) out.push('…')
  for (let p = lo; p <= hi; p++) add(p)
  if (hi < nPages - 2) out.push('…')
  if (nPages > 1) add(nPages - 1)
  return out
}

function Pagination({ page, nPages, pageStart, shown, total, onPage }: {
  page: number; nPages: number; pageStart: number; shown: number; total: number; onPage: (p: number) => void
}) {
  return (
    <nav className="players__pager" aria-label="Player pages">
      <span className="players__pager-info">{pageStart + 1}–{pageStart + shown} of {total}</span>
      <span className="players__pager-ctrls">
        <button className="players__pager-btn" disabled={page === 0} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeft size={15} />
        </button>
        {pageWindow(page, nPages).map((p, i) =>
          p === '…'
            ? <span key={`gap-${i}`} className="players__pager-gap">…</span>
            : <button key={p} className={`players__pager-num${p === page ? ' players__pager-num--active' : ''}`}
                onClick={() => onPage(p)} aria-current={p === page ? 'page' : undefined}>{p + 1}</button>)}
        <button className="players__pager-btn" disabled={page >= nPages - 1} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRight size={15} />
        </button>
      </span>
    </nav>
  )
}

/* The "Divergence board" tab is now a deployment-efficiency tool (actual vs justified usage with a
   situation lens) — its own component. */

/* ============================================================================
   Page
   ============================================================================ */
export default function Players() {
  const [view, setView] = useState<'leaderboard' | 'divergence'>('leaderboard')
  const [show, setShow] = useState<Show>('all')
  const [season, setSeason] = useState<string>(SEASONS[0])
  const [situation, setSituation] = useState('all')           // Usage & Value tab's situation filter
  const [methodOpen, setMethodOpen] = useState(false)
  const [jumpTarget, setJumpTarget] = useState<PlayerSearchResult | null>(null)  // search -> locate in list
  const [focusedId, setFocusedId] = useState<number | null>(null)  // search -> show only that player

  // M3.5: the index ranks by assessed_war for every scope, so Show just re-scopes the same list.
  const changeShow = (s: Show) => setShow(s)

  // Search a player -> show that player as the only result. Auto-adjust the filters so they're in the
  // loaded list: jump to the leaderboard, the season the search ran against (current), and a Show scope
  // that contains them (keep 'all' or their current scope; otherwise switch to their position group).
  // The Leaderboard locates them once its list loads (falling back to the full profile only if they're
  // in no ranked list here) and renders just their row until "Show all players" clears the focus.
  const handleSearchSelect = (p: PlayerSearchResult) => {
    setView('leaderboard')
    if (season !== SEASONS[0]) setSeason(SEASONS[0])   // search is current-season roster
    const grp = scopeOf(p.position)
    if (show !== 'all' && show !== grp) changeShow(grp)
    setJumpTarget(p)
    setFocusedId(p.player_id)
  }
  const clearFocus = () => { setFocusedId(null); setJumpTarget(null) }

  return (
    <PageLayout>
      <div className="players">
        <PageCard
          eyebrow="Players"
          title="Leaderboards"
          subtitle="League-wide value, ranked. Filter, switch the lens, or press ⌘K to find anyone."
          controls={
          /* page controls live inside the header region */
          <div className="players__toolbar">
          {/* mode + search */}
          <div className="players__mode">
            <Tabs
              options={[
                { value: 'leaderboard', label: 'Player Rankings' },
                { value: 'divergence', label: 'Usage & Value' },
              ]}
              value={view}
              onChange={(v) => setView(v as 'leaderboard' | 'divergence')}
            />
            <div className="players__search">
              <PlayerPicker placeholder="Find any player…" onSelect={handleSearchSelect} />
            </div>
            <span className="players__cmdk-hint">Press ⌘K to find a player</span>
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

          {view === 'divergence' && (
            <div className="players__controls">
              <span className="players__control">
                <span className="players__control-lbl">Situation</span>
                <Tabs options={DEPLOYMENT_SITUATIONS} value={situation} onChange={setSituation} />
              </span>
            </div>
          )}
          </div>
          }
        >
        {view === 'leaderboard'
          ? <Leaderboard show={show} season={season}
              jumpTarget={jumpTarget} onJumpHandled={() => setJumpTarget(null)}
              focusedId={focusedId} onClearFocus={clearFocus} />
          : <DeploymentBoard situation={situation} />}
        </PageCard>
      </div>
    </PageLayout>
  )
}
