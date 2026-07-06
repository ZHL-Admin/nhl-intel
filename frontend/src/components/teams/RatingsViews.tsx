/**
 * RatingsViews (P2) — the Power Ratings and Deserved Standings views, moved verbatim out of the old
 * pages/Rankings.tsx so the Teams index can host them under its view switcher. The row lists, bars,
 * captions, glossary tooltips, and the power-view colour legend are byte-for-byte the originals
 * (same class names + RatingsViews.css copied from Rankings.css) — zero visual change. Each view is
 * self-contained: it fetches its own data and renders its own caption/how/legend + list.
 *
 * Frontend only — existing endpoints. No model or pipeline changes.
 */
import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUp, ArrowDown } from 'lucide-react'
import { Tooltip, ComponentStackBar, SkeletonLoader } from '../common'
import type { StackSegment } from '../common'
import { getPowerRankings, getDeservedStandings } from '../../api/rankings'
import { PowerRatingRow, DeservedStandingRow } from '../../api/types'
import { RATINGS_GLOSSARY, RATINGS_COMPONENTS, TRAJECTORY_MEANINGFUL_MOVE } from '../../config/metrics'
import { METHOD_LINKS } from '../../config/methods'
import { getTeamLogoUrl } from '../../utils/teams'
import './RatingsViews.css'

const COMPONENT_META = RATINGS_COMPONENTS

const POWER_CAPTION = 'Each bar is a team’s rating versus a league-average opponent — hover for the four-part split.'
const DESERVED_CAPTION = 'Points each team earned from the chances it created, against what it actually banked.'
const POWER_HOW =
  'Power rating estimates a team’s strength as net goals per game versus a league-average opponent, ' +
  'adjusted for score state and schedule. It is the sum of four sources, weighted by how well each ' +
  'predicts results: 5v5 play, finishing, goaltending, and special teams. Teams are sorted strongest to weakest.'
const DESERVED_HOW =
  'The season is replayed 10,000 times where each game’s goals are random draws from the chances ' +
  'created (expected goals). Deserved points are the average outcome; luck is how far actual points ' +
  'sit above (green) or below (red) what the chances earned. Teams are sorted by deserved points.'

const fmtRating = (v: number) => (v >= 0 ? '+' : '') + v.toFixed(2)
const fmtPts = (v: number) => (v >= 0 ? '+' : '') + v.toFixed(1)

function HeaderTip({ glossaryKey, children }: { glossaryKey: keyof typeof RATINGS_GLOSSARY; children: React.ReactNode }) {
  const g = RATINGS_GLOSSARY[glossaryKey]
  return (
    <Tooltip content={`${g.term}: ${g.shortDef}`}>
      <span className="rankings__tip">{children}</span>
    </Tooltip>
  )
}

/** Team logo, hidden gracefully on load error. */
function TeamLogo({ abbrev, size = 26 }: { abbrev?: string | null; size?: number }) {
  if (!abbrev) return null
  return (
    <img
      src={getTeamLogoUrl(abbrev)}
      alt=""
      className="rankings__logo"
      style={{ width: size, height: size }}
      onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))}
    />
  )
}

/** Trajectory arrow shown ONLY for a meaningful 15-day move; blank otherwise (no filler dashes). */
function TrajInline({ value }: { value?: number | null }) {
  if (value == null || Math.abs(value) <= TRAJECTORY_MEANINGFUL_MOVE) return null
  const up = value > 0
  return (
    <Tooltip content={`${RATINGS_GLOSSARY.trajectory.term}: ${RATINGS_GLOSSARY.trajectory.shortDef}`}>
      <span className={`rrow__traj ${up ? 'rrow__traj--up' : 'rrow__traj--down'}`}>
        {up ? <ArrowUp size={12} /> : <ArrowDown size={12} />}{Math.abs(value).toFixed(2)}
      </span>
    </Tooltip>
  )
}

/* ============================================================================
   Power Ratings
   ============================================================================ */

function segmentsFor(r: PowerRatingRow): StackSegment[] {
  return COMPONENT_META.map((c) => ({ key: c.key, label: c.label, value: r[c.contrib] as number, color: c.color }))
}

/** Symmetric scale around league average, sized to the largest total (+ its whisker). */
function usePowerDomain(rows: PowerRatingRow[]): [number, number] {
  return useMemo<[number, number]>(() => {
    let m = 0.1
    for (const r of rows) m = Math.max(m, Math.abs(r.total_rating) + (r.rating_se ?? 0))
    return [-m, m]
  }, [rows])
}

/** On-demand colour key (component swatches + the bar marks). */
function PowerLegend() {
  return (
    <div className="rankings__key">
      <div className="rankings__key-components">
        {COMPONENT_META.map((c) => (
          <span key={c.key} className="rankings__legend-item">
            <span className="rankings__swatch" style={{ background: c.color }} />
            <HeaderTip glossaryKey={c.key}>{c.label}</HeaderTip>
          </span>
        ))}
      </div>
      <div className="rankings__key-marks">
        <span className="rankings__legend-item"><span className="key-mark key-mark--tick" />total rating</span>
        <span className="rankings__legend-item"><span className="key-mark key-mark--whisker" />uncertainty</span>
        <span className="rankings__key-hint">Bar centred at league average; negatives extend left. Hover a bar for the split.</span>
      </div>
    </div>
  )
}

function PowerRow({ r, rank, domain }: { r: PowerRatingRow; rank: number; domain: [number, number] }) {
  return (
    <Link to={`/teams/${r.team_id}`} className="rrow">
      <span className={`rrow__rank${rank === 1 ? ' rrow__rank--lead' : ''}`}>{rank}</span>
      <TeamLogo abbrev={r.team_abbrev} />
      <span className="rrow__team">
        <span className="rrow__name">{r.team_abbrev ?? r.team_id}</span>
        <span className="rrow__sub">{r.games_played} GP</span>
      </span>
      <span className="rrow__bar">
        <ComponentStackBar
          variant="total" segments={segmentsFor(r)} total={r.total_rating}
          domain={domain} se={r.rating_se}
        />
      </span>
      <span className="rrow__value">
        <span className="rrow__total">{fmtRating(r.total_rating)}</span>
        <TrajInline value={r.trajectory_15d} />
      </span>
    </Link>
  )
}

function PowerList({ rows }: { rows: PowerRatingRow[] }) {
  const domain = usePowerDomain(rows)
  return (
    <div className="rankings__rows rankings__rows--power">
      {rows.map((r, i) => <PowerRow key={r.team_id} r={r} rank={i + 1} domain={domain} />)}
    </div>
  )
}

/** Full Power Ratings view: caption + how + on-demand legend + list. Self-fetching. */
export function PowerRatingsView() {
  const [rows, setRows] = useState<PowerRatingRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showColors, setShowColors] = useState(false)
  useEffect(() => {
    let active = true
    getPowerRankings().then((r) => active && setRows(r)).catch(() => active && setError('Could not load power ratings.'))
    return () => { active = false }
  }, [])

  return (
    <div className="rankings__view">
      <div className="rankings__meta">
        <p className="rankings__caption">{POWER_CAPTION}</p>
        <div className="rankings__meta-actions">
          {rows && <span className="rankings__count">{rows.length} teams</span>}
          <Tooltip content={POWER_HOW}><span className="rankings__how">How power ratings work</span></Tooltip>
          <Link to={METHOD_LINKS.power} className="rankings__how-link">Full method →</Link>
          <button
            type="button"
            className={`rankings__colors${showColors ? ' rankings__colors--on' : ''}`}
            onClick={() => setShowColors((s) => !s)}
            aria-expanded={showColors}
          >
            Legend
          </button>
        </div>
      </div>
      {showColors && <PowerLegend />}
      {error && <p className="rankings__msg">{error}</p>}
      {!error && (rows ? <PowerList rows={rows} /> : <SkeletonLoader />)}
    </div>
  )
}

/* ============================================================================
   Deserved Standings — same grammar; bar shows the actual-vs-deserved (luck) gap
   ============================================================================ */

function useLuckDomain(rows: DeservedStandingRow[]): [number, number] {
  return useMemo<[number, number]>(() => {
    let m = 1
    for (const r of rows) m = Math.max(m, Math.abs(r.luck_delta))
    return [-m, m]
  }, [rows])
}

function DeservedRow({ r, rank, domain }: { r: DeservedStandingRow; rank: number; domain: [number, number] }) {
  const lucky = r.luck_delta > 0
  const seg: StackSegment[] = [{
    key: 'luck', label: 'Luck (actual − deserved)', value: r.luck_delta,
    color: lucky ? 'var(--color-success)' : 'var(--color-danger)',
  }]
  return (
    <Link to={`/teams/${r.team_id}`} className="rrow rrow--deserved">
      <span className={`rrow__rank${rank === 1 ? ' rrow__rank--lead' : ''}`}>{rank}</span>
      <TeamLogo abbrev={r.team_abbrev} />
      <span className="rrow__team">
        <span className="rrow__name">{r.team_abbrev ?? r.team_id}</span>
        <span className="rrow__sub">{r.games} GP</span>
      </span>
      <span className="rrow__pts">
        <span className="rrow__total">{r.actual_points}</span>
        <span className="rrow__sub">{r.deserved_points.toFixed(0)} deserved</span>
      </span>
      <span className="rrow__bar">
        <ComponentStackBar
          variant="total" segments={seg} total={r.luck_delta} domain={domain}
          totalColor={lucky ? 'var(--color-success)' : 'var(--color-danger)'} formatValue={fmtPts}
        />
      </span>
      <span className={`rrow__luck ${r.luck_delta > 0 ? 'rrow__luck--pos' : r.luck_delta < 0 ? 'rrow__luck--neg' : ''}`}>
        {fmtPts(r.luck_delta)}
      </span>
    </Link>
  )
}

function DeservedList({ rows }: { rows: DeservedStandingRow[] }) {
  const domain = useLuckDomain(rows)
  return (
    <div className="rankings__rows rankings__rows--deserved">
      {rows.map((r, i) => <DeservedRow key={r.team_id} r={r} rank={i + 1} domain={domain} />)}
    </div>
  )
}

/** Full Deserved Standings view: caption + how + list. Self-fetching. */
export function DeservedStandingsView() {
  const [rows, setRows] = useState<DeservedStandingRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    getDeservedStandings().then((r) => active && setRows(r)).catch(() => active && setError('Could not load deserved standings.'))
    return () => { active = false }
  }, [])

  return (
    <div className="rankings__view">
      <div className="rankings__meta">
        <p className="rankings__caption">{DESERVED_CAPTION}</p>
        <div className="rankings__meta-actions">
          {rows && <span className="rankings__count">{rows.length} teams</span>}
          <Tooltip content={DESERVED_HOW}><span className="rankings__how">How deserved points work</span></Tooltip>
          <Link to={METHOD_LINKS.deserved} className="rankings__how-link">Full method →</Link>
        </div>
      </div>
      {error && <p className="rankings__msg">{error}</p>}
      {!error && (rows ? <DeservedList rows={rows} /> : <SkeletonLoader />)}
    </div>
  )
}
