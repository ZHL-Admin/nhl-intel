import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUp, ArrowDown, Minus } from 'lucide-react'
import { PageLayout, Tabs, Tooltip, ComponentStackBar, SkeletonLoader } from '../components/common'
import type { StackSegment } from '../components/common'
import { getPowerRankings, getDeservedStandings } from '../api/rankings'
import { PowerRatingRow, DeservedStandingRow } from '../api/types'
import { RATINGS_GLOSSARY } from '../config/metrics'
import { getTeamLogoUrl } from '../utils/teams'
import './Rankings.css'

// Component colours (shared by the stacked bars and the legend).
const COMPONENT_META: { key: keyof typeof RATINGS_GLOSSARY; contrib: keyof PowerRatingRow; label: string; color: string }[] = [
  { key: 'play_5v5', contrib: 'contrib_play_5v5', label: '5v5 play', color: '#3b82f6' },
  { key: 'finishing', contrib: 'contrib_finishing', label: 'Finishing', color: '#22c55e' },
  { key: 'goaltending', contrib: 'contrib_goaltending', label: 'Goaltending', color: '#a855f7' },
  { key: 'special_teams', contrib: 'contrib_special_teams', label: 'Special teams', color: '#f59e0b' },
]

function HeaderTip({ glossaryKey, children }: { glossaryKey: keyof typeof RATINGS_GLOSSARY; children: React.ReactNode }) {
  const g = RATINGS_GLOSSARY[glossaryKey]
  return (
    <Tooltip content={`${g.term}: ${g.shortDef}`}>
      <span className="rankings__th-tip">{children}</span>
    </Tooltip>
  )
}

function TeamCell({ teamId, abbrev }: { teamId: number; abbrev?: string | null }) {
  return (
    <Link to={`/teams/${teamId}`} className="rankings__team">
      {abbrev && <img src={getTeamLogoUrl(abbrev)} alt="" className="rankings__team-logo" onError={(e) => ((e.target as HTMLImageElement).style.visibility = 'hidden')} />}
      <span>{abbrev ?? teamId}</span>
    </Link>
  )
}

function Trajectory({ value }: { value?: number | null }) {
  if (value == null) return <span className="rankings__traj rankings__traj--flat"><Minus size={14} /></span>
  if (value > 0.02) return <span className="rankings__traj rankings__traj--up"><ArrowUp size={14} />{value.toFixed(2)}</span>
  if (value < -0.02) return <span className="rankings__traj rankings__traj--down"><ArrowDown size={14} />{Math.abs(value).toFixed(2)}</span>
  return <span className="rankings__traj rankings__traj--flat"><Minus size={14} /></span>
}

function PowerTable({ rows }: { rows: PowerRatingRow[] }) {
  // shared symmetric scale: the widest positive / negative stack across all teams
  const domain = useMemo<[number, number]>(() => {
    let m = 0.1
    for (const r of rows) {
      let pos = 0, neg = 0
      for (const c of COMPONENT_META) {
        const v = r[c.contrib] as number
        if (v >= 0) pos += v; else neg += v
      }
      m = Math.max(m, pos, Math.abs(neg))
    }
    return [-m, m]
  }, [rows])

  return (
    <div className="rankings__table-wrap">
      <table className="rankings__table">
        <thead>
          <tr>
            <th className="rankings__rank-col">#</th>
            <th>Team</th>
            <th className="rankings__num">GP</th>
            <th className="rankings__num"><HeaderTip glossaryKey="power_rating">Rating</HeaderTip></th>
            <th className="rankings__bar-col"><HeaderTip glossaryKey="power_rating">Component breakdown (goals/game)</HeaderTip></th>
            <th className="rankings__num"><HeaderTip glossaryKey="uncertainty">±</HeaderTip></th>
            <th className="rankings__num"><HeaderTip glossaryKey="trajectory">15d</HeaderTip></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const segments: StackSegment[] = COMPONENT_META.map((c) => ({
              key: c.key, label: c.label, value: r[c.contrib] as number, color: c.color,
            }))
            return (
              <tr key={r.team_id}>
                <td className="rankings__rank-col">{i + 1}</td>
                <td><TeamCell teamId={r.team_id} abbrev={r.team_abbrev} /></td>
                <td className="rankings__num">{r.games_played}</td>
                <td className="rankings__num rankings__total">{(r.total_rating >= 0 ? '+' : '') + r.total_rating.toFixed(2)}</td>
                <td className="rankings__bar-col">
                  <ComponentStackBar segments={segments} total={r.total_rating} domain={domain} se={r.rating_se} />
                </td>
                <td className="rankings__num rankings__muted">{r.rating_se != null ? r.rating_se.toFixed(2) : '—'}</td>
                <td className="rankings__num"><Trajectory value={r.trajectory_15d} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="rankings__legend">
        {COMPONENT_META.map((c) => (
          <span key={c.key} className="rankings__legend-item">
            <span className="rankings__legend-swatch" style={{ background: c.color }} />
            <HeaderTip glossaryKey={c.key}>{c.label}</HeaderTip>
          </span>
        ))}
        <span className="rankings__legend-note">Bar centred at league average; tick = total, line = uncertainty.</span>
      </div>
    </div>
  )
}

function DeservedTable({ rows }: { rows: DeservedStandingRow[] }) {
  return (
    <div className="rankings__table-wrap">
      <table className="rankings__table">
        <thead>
          <tr>
            <th className="rankings__rank-col">#</th>
            <th>Team</th>
            <th className="rankings__num">GP</th>
            <th className="rankings__num">Actual</th>
            <th className="rankings__num"><HeaderTip glossaryKey="deserved_points">Deserved</HeaderTip></th>
            <th className="rankings__num rankings__muted">10th–90th</th>
            <th className="rankings__num"><HeaderTip glossaryKey="deserved_points">Luck</HeaderTip></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.team_id}>
              <td className="rankings__rank-col">{i + 1}</td>
              <td><TeamCell teamId={r.team_id} abbrev={r.team_abbrev} /></td>
              <td className="rankings__num">{r.games}</td>
              <td className="rankings__num">{r.actual_points}</td>
              <td className="rankings__num rankings__total">{r.deserved_points.toFixed(1)}</td>
              <td className="rankings__num rankings__muted">{r.deserved_p10.toFixed(0)}–{r.deserved_p90.toFixed(0)}</td>
              <td className={`rankings__num rankings__luck ${r.luck_delta > 0 ? 'rankings__luck--pos' : r.luck_delta < 0 ? 'rankings__luck--neg' : ''}`}>
                {(r.luck_delta >= 0 ? '+' : '') + r.luck_delta.toFixed(1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Rankings() {
  const [tab, setTab] = useState<'power' | 'deserved'>('power')
  const [power, setPower] = useState<PowerRatingRow[] | null>(null)
  const [deserved, setDeserved] = useState<DeservedStandingRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    Promise.all([getPowerRankings(), getDeservedStandings()])
      .then(([p, d]) => { if (active) { setPower(p); setDeserved(d) } })
      .catch(() => { if (active) setError('Could not load rankings.') })
    return () => { active = false }
  }, [])

  const loading = !power || !deserved

  return (
    <PageLayout>
      <div className="rankings">
        <div className="rankings__header">
          <h1 className="rankings__title">Rankings</h1>
          <p className="rankings__subtitle">
            Power ratings show where each team’s edge comes from. Deserved standings replay
            the season from the chances created.
          </p>
        </div>
        <Tabs
          options={[{ value: 'power', label: 'Power Ratings' }, { value: 'deserved', label: 'Deserved Standings' }]}
          value={tab}
          onChange={(v) => setTab(v as 'power' | 'deserved')}
        />
        {error && <p className="rankings__error">{error}</p>}
        {loading && !error && <SkeletonLoader />}
        {!loading && tab === 'power' && <PowerTable rows={power!} />}
        {!loading && tab === 'deserved' && <DeservedTable rows={deserved!} />}
      </div>
    </PageLayout>
  )
}
