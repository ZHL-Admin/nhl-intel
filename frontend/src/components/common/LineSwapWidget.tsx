/**
 * Embedded line-swap widget (Phase 5.2, blueprint 6.1 / section 9 team page).
 *
 * Renders a team's current forward trios + defense pairs (from GET /teams/{id}/lines), each with
 * its observed xGF% and projected grade. The user can swap any one member via the shared
 * PlayerPicker to see the line re-project inline (POST /tools/line-fit). Used on TeamProfile.
 */
import { useEffect, useState } from 'react'
import { RefreshCw, ArrowLeftRight } from 'lucide-react'
import { getTeamLines, lineFit } from '../../api/tools'
import { TeamLine, LineFitProjection, PlayerSearchResult } from '../../api/types'
import LineProjection from './LineProjection'
import PlayerPicker from './PlayerPicker'
import SkeletonLoader from './SkeletonLoader'
import './LineSwapWidget.css'

interface RowState {
  base: TeamLine
  ids: number[]
  names: string[]
  proj: LineFitProjection | null
  swapIdx: number | null     // which slot is being edited
  loading: boolean
  dirty: boolean
}

function init(line: TeamLine): RowState {
  return {
    base: line, ids: [...line.player_ids], names: [...line.member_names],
    proj: line.projection ?? null, swapIdx: null, loading: false, dirty: false,
  }
}

function LineRow({ row, season, onChange }: {
  row: RowState; season: string; onChange: (r: RowState) => void
}) {
  const posFilter = row.base.line_type === 'D2' ? 'D' : 'F'

  const doSwap = async (slot: number, picked: PlayerSearchResult) => {
    const ids = [...row.ids]; ids[slot] = picked.player_id
    const names = [...row.names]; names[slot] = picked.name ?? `#${picked.player_id}`
    const next = { ...row, ids, names, swapIdx: null, loading: true, dirty: true }
    onChange(next)
    try {
      const proj = await lineFit(ids, season)
      onChange({ ...next, proj, loading: false })
    } catch {
      onChange({ ...next, loading: false })
    }
  }

  const reset = async () => {
    const next = { ...row, ids: [...row.base.player_ids], names: [...row.base.member_names], dirty: false, loading: true, swapIdx: null }
    onChange(next)
    const proj = row.base.projection ?? (await lineFit(row.base.player_ids, season))
    onChange({ ...next, proj, loading: false })
  }

  return (
    <div className="swap-widget__row">
      <div className="swap-widget__members">
        {row.names.map((name, slot) => (
          <div key={slot} className="swap-widget__member">
            {row.swapIdx === slot ? (
              <PlayerPicker season={season} positionFilter={posFilter}
                placeholder={`Swap ${posFilter === 'D' ? 'defenseman' : 'forward'}…`}
                onSelect={(p) => doSwap(slot, p)} />
            ) : (
              <button className="swap-widget__chip" onClick={() => onChange({ ...row, swapIdx: slot })}>
                <ArrowLeftRight size={12} />
                <span>{name}</span>
              </button>
            )}
          </div>
        ))}
        {row.dirty && (
          <button className="swap-widget__reset" onClick={reset} title="Reset to current line">
            <RefreshCw size={13} /> reset
          </button>
        )}
      </div>
      <div className="swap-widget__proj">
        {row.loading ? <SkeletonLoader />
          : row.proj ? <LineProjection proj={row.proj} />
          : <div className="swap-widget__empty">No projection.</div>}
      </div>
    </div>
  )
}

export default function LineSwapWidget({ teamId, season }: { teamId: number; season?: string }) {
  const [rows, setRows] = useState<RowState[] | null>(null)
  const [resolvedSeason, setResolvedSeason] = useState<string>(season ?? '')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setRows(null); setError(null)
    getTeamLines(teamId, season)
      .then((data) => {
        if (!active) return
        setResolvedSeason(data.season)
        setRows([...data.forward_lines, ...data.defense_pairs].map(init))
      })
      .catch(() => active && setError('Could not load lines.'))
    return () => { active = false }
  }, [teamId, season])

  if (error) return <div className="swap-widget__empty">{error}</div>
  if (!rows) return <SkeletonLoader />

  const update = (i: number, r: RowState) => setRows(rs => rs!.map((x, j) => (j === i ? r : x)))
  const fwd = rows.filter(r => r.base.line_type === 'F3')
  const def = rows.filter(r => r.base.line_type === 'D2')

  return (
    <div className="swap-widget">
      <p className="swap-widget__intro">
        Current lines over the last 10 games. Swap any player to see the projection change.
      </p>
      <h3 className="swap-widget__group">Forward lines</h3>
      {fwd.map((r) => <LineRow key={r.base.player_ids.join('-')} row={r} season={resolvedSeason}
        onChange={(nr) => update(rows.indexOf(r), nr)} />)}
      <h3 className="swap-widget__group">Defense pairs</h3>
      {def.map((r) => <LineRow key={r.base.player_ids.join('-')} row={r} season={resolvedSeason}
        onChange={(nr) => update(rows.indexOf(r), nr)} />)}
    </div>
  )
}
