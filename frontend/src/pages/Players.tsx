import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { PageLayout, ComponentStackBar, SkeletonLoader, Tabs } from '../components/common'
import type { StackSegment } from '../components/common'
import { getArchetypeRanking, getDivergenceBoard } from '../api/players'
import { ArchetypeRankRow, DivergenceBoardRow } from '../api/types'
import { ARCHETYPES, COMPOSITE_COMPONENTS } from '../config/metrics'
import './Players.css'

function DivergenceBoard() {
  const [rows, setRows] = useState<DivergenceBoardRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    getDivergenceBoard().then((d) => active && setRows(d)).catch(() => active && setError('Could not load board.'))
    return () => { active = false }
  }, [])
  if (error) return <p className="players__placeholder-text">{error}</p>
  if (!rows) return <SkeletonLoader />
  const over = rows.filter((r) => r.side === 'trusted_over_value')
  const under = rows.filter((r) => r.side === 'value_over_trust')
  const card = (r: DivergenceBoardRow) => (
    <div key={r.player_id} className="divergence__card">
      <div className="divergence__card-head">
        <Link to={`/players/${r.player_id}`} className="players__name">{r.player_name ?? r.player_id}</Link>
        <span className="divergence__score">{(r.divergence >= 0 ? '+' : '') + r.divergence.toFixed(1)}σ</span>
      </div>
      <p className="divergence__explain">{r.explanation}</p>
    </div>
  )
  return (
    <div className="divergence">
      <p className="players__subtitle">
        Where coaching deployment (trust) and isolated value (composite) most disagree, by
        position-standardized z-scores. Explanations are generated from the underlying numbers.
      </p>

      {/* The high-signal side: players a coach leans on more than the models support. */}
      <h3 className="divergence__col-title">Trusted beyond their value</h3>
      <p className="divergence__caption">
        The eye-test-vs-analytics tension lives here — heavy defensive deployment the isolated
        numbers don't reward.
      </p>
      <div className="divergence__grid">{over.map(card)}</div>

      {/* The reverse side is largely mechanical (trust is defense-weighted, so offensive */}
      {/* stars sit here), so it is presented compactly as secondary. */}
      <details className="divergence__secondary">
        <summary>Value beyond their deployment ({under.length}) — mostly offensive stars not used in defensive roles</summary>
        <div className="divergence__grid">{under.map(card)}</div>
      </details>
    </div>
  )
}

function rowSegments(r: ArchetypeRankRow): StackSegment[] {
  const m = new Map(r.components.map((c) => [c.key, c.value]))
  return COMPOSITE_COMPONENTS.map((c) => ({
    key: c.key, label: c.label, value: m.get(c.key) ?? 0, color: c.color,
  }))
}

function Players() {
  const [view, setView] = useState<'archetype' | 'divergence'>('archetype')
  const [pos, setPos] = useState<'F' | 'D'>('F')
  const [archetype, setArchetype] = useState<string>(ARCHETYPES.F[0])
  const [rows, setRows] = useState<ArchetypeRankRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  // keep the selected archetype valid when switching position group
  useEffect(() => { setArchetype(ARCHETYPES[pos][0]) }, [pos])

  useEffect(() => {
    let active = true
    setRows(null); setError(null)
    getArchetypeRanking(archetype, undefined, 50)
      .then((d) => active && setRows(d))
      .catch(() => active && setError('Could not load rankings.'))
    return () => { active = false }
  }, [archetype])

  const domain = useMemo<[number, number]>(() => {
    let m = 1
    for (const r of rows ?? []) {
      let posSum = 0, negSum = 0
      for (const c of r.components) (c.value >= 0 ? (posSum += c.value) : (negSum += c.value))
      m = Math.max(m, posSum, Math.abs(negSum))
    }
    return [-m, m]
  }, [rows])

  return (
    <PageLayout>
      <div className="players">
        <div className="players__header">
          <h1 className="players__title">Players</h1>
        </div>

        <Tabs
          options={[
            { value: 'archetype', label: 'Rank by Archetype' },
            { value: 'divergence', label: 'Divergence Board' },
          ]}
          value={view}
          onChange={(v) => setView(v as 'archetype' | 'divergence')}
        />

        {view === 'divergence' && <DivergenceBoard />}

        {view === 'archetype' && (
        <section className="players__leaderboard">
          <p className="players__subtitle">
            Ranked within archetype by total value (goals above replacement). Each bar breaks
            the value into its components; the tick is the total, the line its uncertainty.
          </p>
          <div className="players__controls">
            <div className="players__position-filter">
              {(['F', 'D'] as const).map((p) => (
                <button key={p}
                  className={`players__filter-button ${pos === p ? 'players__filter-button--active' : ''}`}
                  onClick={() => setPos(p)}>
                  {p === 'F' ? 'Forwards' : 'Defense'}
                </button>
              ))}
            </div>
            <select className="players__sort-select" value={archetype}
              onChange={(e) => setArchetype(e.target.value)}>
              {ARCHETYPES[pos].map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>

          {error && <p className="players__placeholder-text">{error}</p>}
          {!rows && !error && <SkeletonLoader />}
          {rows && rows.length === 0 && (
            <p className="players__placeholder-text">No qualifying players in this archetype.</p>
          )}
          {rows && rows.length > 0 && (
            <table className="players__table">
              <thead>
                <tr><th>#</th><th>Player</th><th className="players__num">Total</th>
                  <th className="players__bar-col">Value breakdown (goals)</th></tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.player_id}>
                    <td className="players__rank">{i + 1}</td>
                    <td>
                      <Link to={`/players/${r.player_id}`} className="players__name">
                        {r.player_name ?? r.player_id}
                      </Link>
                      <span className="players__pos">{r.position}</span>
                    </td>
                    <td className="players__num players__total">
                      {(r.composite_total >= 0 ? '+' : '') + r.composite_total.toFixed(1)}
                    </td>
                    <td className="players__bar-col">
                      <ComponentStackBar segments={rowSegments(r)} total={r.composite_total}
                        domain={domain} se={r.composite_total_sd} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="players__legend">
            {COMPOSITE_COMPONENTS.map((c) => (
              <span key={c.key} className="players__legend-item">
                <span className="players__swatch" style={{ background: c.color }} />{c.label}
              </span>
            ))}
          </div>
        </section>
        )}
      </div>
    </PageLayout>
  )
}

export default Players
