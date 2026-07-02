/**
 * Rankings (Phase 3.1) — team Power Ratings + Deserved Standings, sharing the Players-page
 * grammar: a consolidated top (short descriptor · mode tabs · one caption · on-demand legend),
 * then a single uniform list of teams. Each row carries a simple single-tone magnitude bar of
 * the TOTAL; the four-component breakdown lives on hover and on the team page (no podium, no
 * always-on legend, no four-way segmentation on the list). Frontend only — existing endpoints.
 */
import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUp, ArrowDown } from 'lucide-react'
import { PageLayout, PageCard, Tabs, Tooltip, ComponentStackBar, SkeletonLoader } from '../components/common'
import type { StackSegment } from '../components/common'
import { getPowerRankings, getDeservedStandings } from '../api/rankings'
import { PowerRatingRow, DeservedStandingRow } from '../api/types'
import { RATINGS_GLOSSARY, RATINGS_COMPONENTS } from '../config/metrics'
import { getTeamLogoUrl } from '../utils/teams'
import './Rankings.css'

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
  if (value == null || Math.abs(value) <= 0.03) return null
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

/** On-demand colour key (component swatches + the bar marks). Lives inside the top card. */
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

function PowerView({ rows }: { rows: PowerRatingRow[] }) {
  const domain = usePowerDomain(rows)
  return (
    <div className="rankings__rows rankings__rows--power">
      {rows.map((r, i) => <PowerRow key={r.team_id} r={r} rank={i + 1} domain={domain} />)}
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

function DeservedView({ rows }: { rows: DeservedStandingRow[] }) {
  const domain = useLuckDomain(rows)
  return (
    <div className="rankings__rows rankings__rows--deserved">
      {rows.map((r, i) => <DeservedRow key={r.team_id} r={r} rank={i + 1} domain={domain} />)}
    </div>
  )
}

/* ============================================================================
   Page
   ============================================================================ */
export default function Rankings() {
  const [tab, setTab] = useState<'power' | 'deserved'>('power')
  const [power, setPower] = useState<PowerRatingRow[] | null>(null)
  const [deserved, setDeserved] = useState<DeservedStandingRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showColors, setShowColors] = useState(false)

  useEffect(() => {
    let active = true
    Promise.all([getPowerRankings(), getDeservedStandings()])
      .then(([p, d]) => { if (active) { setPower(p); setDeserved(d) } })
      .catch(() => { if (active) setError('Could not load rankings.') })
    return () => { active = false }
  }, [])

  const loading = !power || !deserved
  const count = tab === 'power' ? power?.length : deserved?.length

  return (
    <PageLayout>
      <div className="rankings">
        <PageCard
          title="Rankings"
          subtitle="Team strength by net goals per game, with the luck stripped out."
          controls={
            <div className="rankings__toolbar">
              <div className="rankings__bar">
                <Tabs
                  options={[
                    { value: 'power', label: 'Power Ratings' },
                    { value: 'deserved', label: 'Deserved Standings' },
                  ]}
                  value={tab}
                  onChange={(v) => setTab(v as 'power' | 'deserved')}
                />
                {!loading && count != null && <span className="rankings__count">{count} teams</span>}
              </div>

              <div className="rankings__meta">
                <p className="rankings__caption">{tab === 'power' ? POWER_CAPTION : DESERVED_CAPTION}</p>
                <div className="rankings__meta-actions">
                  <Tooltip content={tab === 'power' ? POWER_HOW : DESERVED_HOW}>
                    <span className="rankings__how">
                      {tab === 'power' ? 'How power ratings work' : 'How deserved points work'}
                    </span>
                  </Tooltip>
                  {tab === 'power' && (
                    <button
                      type="button"
                      className={`rankings__colors${showColors ? ' rankings__colors--on' : ''}`}
                      onClick={() => setShowColors((s) => !s)}
                      aria-expanded={showColors}
                    >
                      Legend
                    </button>
                  )}
                </div>
              </div>

              {tab === 'power' && showColors && <PowerLegend />}
            </div>
          }
        >
          {error && <p className="rankings__msg">{error}</p>}
          {loading && !error && <SkeletonLoader />}
          {!loading && tab === 'power' && <PowerView rows={power!} />}
          {!loading && tab === 'deserved' && <DeservedView rows={deserved!} />}
        </PageCard>
      </div>
    </PageLayout>
  )
}
