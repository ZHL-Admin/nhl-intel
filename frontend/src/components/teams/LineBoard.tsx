/**
 * Compact line board (Team page · Lines). One scannable row per current line — members, grade
 * chip, an xGF% bar, and a one-line verdict — that expands to the full projection (reused
 * LineProjection). Replaces the old long stack of full-size projection blocks. The player-swap
 * experiment stays in LineSwapWidget, rendered below.
 */
import { useEffect, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { LineProjection, SkeletonLoader } from '../common'
import { getTeamLines } from '../../api/tools'
import { TeamLines, TeamLine } from '../../api/types'
import './LineBoard.css'

const GRADE_COLOR: Record<string, string> = { A: '#16a34a', B: '#65a30d', C: '#d97706', D: '#ea580c', F: '#dc2626' }
const gradeColor = (g?: string) => GRADE_COLOR[(g ?? '')[0]] ?? 'var(--color-text-secondary)'

// xGF% display window: lines realistically land ~35-65%.
const LO = 0.35, HI = 0.65
const barPct = (v: number) => `${((Math.min(HI, Math.max(LO, v)) - LO) / (HI - LO)) * 100}%`

function LineRow({ line }: { line: TeamLine }) {
  const [open, setOpen] = useState(false)
  const proj = line.projection
  const grade = proj?.grade
  const xgf = proj?.projected_xgf_pct
  const verdict = proj?.grade_sentence
  return (
    <div className={`line-board__item${open ? ' line-board__item--open' : ''}`}>
      <button className="line-board__row" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="line-board__members">{line.member_names.filter(Boolean).join(' · ')}</span>
        {grade && <span className="line-board__grade" style={{ color: gradeColor(grade), borderColor: gradeColor(grade) }}>{grade}</span>}
        <span className="line-board__bar" aria-hidden="true">
          {xgf != null && <span className="line-board__bar-fill" style={{ width: barPct(xgf), background: gradeColor(grade) }} />}
        </span>
        <span className="line-board__xgf mono">{xgf != null ? `${(xgf * 100).toFixed(1)}%` : '—'}</span>
        <span className="line-board__verdict">{verdict ?? `${line.minutes.toFixed(0)} min together`}</span>
        <ChevronDown size={16} className="line-board__chev" />
      </button>
      {open && proj && (
        <div className="line-board__detail">
          <LineProjection proj={proj} variant="hero" />
        </div>
      )}
    </div>
  )
}

export default function LineBoard({ teamId }: { teamId: number }) {
  const [lines, setLines] = useState<TeamLines | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let on = true
    setLines(null); setError(null)
    getTeamLines(teamId)
      .then((d) => on && setLines(d))
      .catch(() => on && setError('Could not load lines.'))
    return () => { on = false }
  }, [teamId])

  if (error) return <p className="line-board__error">{error}</p>
  if (!lines) return <SkeletonLoader />

  const f = lines.forward_lines ?? []
  const d = lines.defense_pairs ?? []
  if (f.length === 0 && d.length === 0) {
    return <p className="line-board__error">Not enough recent 5v5 ice time to derive current lines.</p>
  }

  return (
    <div className="line-board">
      <p className="team-profile__section-sub">
        {f.length} forward {f.length === 1 ? 'line' : 'lines'} and {d.length} defense {d.length === 1 ? 'pair' : 'pairs'} from
        the last 10 games (by shared 5v5 minutes), each projected by the line-fit model. Click a row for the full breakdown.
      </p>
      {f.length > 0 && (
        <>
          <h3 className="line-board__heading">Forward lines</h3>
          {f.map((l) => <LineRow key={l.player_ids.join('-')} line={l} />)}
        </>
      )}
      {d.length > 0 && (
        <>
          <h3 className="line-board__heading">Defense pairs</h3>
          {d.map((l) => <LineRow key={l.player_ids.join('-')} line={l} />)}
        </>
      )}
    </div>
  )
}
