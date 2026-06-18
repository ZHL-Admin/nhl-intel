/**
 * Deployment-efficiency board (the Divergence Board rework). Two directional sides — over-used
 * (deployed beyond value) and under-used (value left on the bench) — re-lensed by a SITUATION
 * filter (All / 5v5 / PP / PK / Key moments). Each row compares ACTUAL usage against the usage the
 * player's situation-appropriate VALUE justifies, with the deterministic explanation from the API.
 * The board face is the mismatch for the active lens; the row expansion shows the player's FULL
 * deployment profile across situations (his highs and lows).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown } from 'lucide-react'
import { Tabs, Tooltip, SkeletonLoader, PlayerAvatar } from '../common'
import { getDeploymentBoard, getPlayerDeployment } from '../../api/players'
import { DeploymentBoard as Board, DeploymentRow, PlayerDeploymentEntry } from '../../api/types'
import './DeploymentBoard.css'

const SITUATIONS = [
  { value: 'all', label: 'All' },
  { value: '5v5', label: '5v5' },
  { value: 'pp', label: 'PP' },
  { value: 'pk', label: 'PK' },
  { value: 'key_moments', label: 'Key moments' },
]
const SIT_LABEL: Record<string, string> = {
  all: 'Overall', '5v5': '5v5', pp: 'Power play', pk: 'Penalty kill', key_moments: 'Key moments',
}
const HOW =
  'Each player’s ACTUAL usage in this situation is compared with the usage his situation-appropriate ' +
  'VALUE justifies (within position), capped at a realistic ceiling so maxed-out stars don’t read as ' +
  'under-used. Over-used = deployed beyond his impact; under-used = value the coach leaves on the bench. ' +
  'Wide uncertainty bands mean the gap is soft.'

const pct = (p: number) => `${Math.round(p * 100)}`

/** Actual-vs-justified usage bar: a hollow "justified" tick and a filled "actual" marker, the gap shaded. */
function DeploymentBar({ actual, justified, side }: { actual: number; justified: number; side: 'over' | 'under' }) {
  const a = Math.max(0, Math.min(1, actual)) * 100
  const j = Math.max(0, Math.min(1, justified)) * 100
  const lo = Math.min(a, j), hi = Math.max(a, j)
  return (
    <span className={`depbar depbar--${side}`}>
      <span className="depbar__gapfill" style={{ left: `${lo}%`, width: `${hi - lo}%` }} />
      <span className="depbar__justified" style={{ left: `${j}%` }} title={`Justified ${pct(justified)}p`} />
      <span className="depbar__actual" style={{ left: `${a}%` }} title={`Actual ${pct(actual)}p`} />
    </span>
  )
}

/** The full per-situation profile shown when a row is expanded. */
function DeploymentProfile({ playerId }: { playerId: number }) {
  const [rows, setRows] = useState<PlayerDeploymentEntry[] | null>(null)
  useEffect(() => {
    let active = true
    getPlayerDeployment(playerId).then((d) => active && setRows(d)).catch(() => active && setRows([]))
    return () => { active = false }
  }, [playerId])
  if (!rows) return <SkeletonLoader />
  if (rows.length === 0) return <p className="depboard__msg">No deployment profile.</p>
  return (
    <div className="depprofile">
      <div className="depprofile__head">Usage vs. justified, every situation</div>
      {rows.map((r) => {
        const side = r.gap >= 0 ? 'over' : 'under'
        return (
          <div className="depprofile__row" key={r.situation}>
            <span className="depprofile__sit">{SIT_LABEL[r.situation] ?? r.situation}</span>
            <DeploymentBar actual={r.actual_pctile} justified={r.justified_pctile} side={side} />
            <span className={`depprofile__gap depprofile__gap--${side}`}>
              {r.gap >= 0 ? '+' : ''}{Math.round(r.gap * 100)}
            </span>
          </div>
        )
      })}
      <div className="depprofile__legend">
        <span><span className="depbar__justified depbar__justified--key" /> justified by value</span>
        <span><span className="depbar__actual depbar__actual--key" /> actual usage</span>
      </div>
    </div>
  )
}

function DeployRow({ rank, r, side }: { rank: number; r: DeploymentRow; side: 'over' | 'under' }) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`deprow${open ? ' deprow--open' : ''}`}>
      <button className="deprow__head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="deprow__rank">{rank}</span>
        <PlayerAvatar id={r.player_id} team={r.team_abbrev} name={r.player_name} size={32} />
        <span className="deprow__id">
          <span className="deprow__name">{r.player_name ?? r.player_id}</span>
          <span className="deprow__meta">{r.position}{r.team_abbrev ? ` · ${r.team_abbrev}` : ''}</span>
        </span>
        <span className="deprow__bar"><DeploymentBar actual={r.actual_pctile} justified={r.justified_pctile} side={side} /></span>
        <span className={`deprow__gap deprow__gap--${side}`}>
          {r.gap >= 0 ? '+' : ''}{Math.round(r.gap * 100)}
          <small>±{Math.round(r.gap_sd * 100)}</small>
        </span>
        <ChevronDown size={15} className={`deprow__chev${open ? ' deprow__chev--open' : ''}`} aria-hidden="true" />
      </button>
      {open && (
        <div className="deprow__detail">
          <p className="deprow__explain">{r.explanation}</p>
          <DeploymentProfile playerId={r.player_id} />
          <Link to={`/players/${r.player_id}`} className="deprow__link">View full profile →</Link>
        </div>
      )}
    </div>
  )
}

function Column({ title, caption, rows, side }: { title: string; caption: string; rows: DeploymentRow[]; side: 'over' | 'under' }) {
  return (
    <div className="depcol">
      <div className="depcol__head">
        <h3 className="depcol__title">{title}</h3>
        <p className="depcol__caption">{caption}</p>
      </div>
      <div className="depcol__list">
        {rows.length === 0
          ? <p className="depboard__msg" style={{ padding: 'var(--space-5)' }}>No qualifying players.</p>
          : rows.map((r, i) => <DeployRow key={r.player_id} rank={i + 1} r={r} side={side} />)}
      </div>
    </div>
  )
}

export default function DeploymentBoard() {
  const [situation, setSituation] = useState('all')
  const [board, setBoard] = useState<Board | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setBoard(null); setError(null)
    getDeploymentBoard(situation).then((b) => active && setBoard(b)).catch(() => active && setError('Could not load the board.'))
    return () => { active = false }
  }, [situation])

  return (
    <section className="depboard">
      <div className="depboard__bar">
        <Tabs options={SITUATIONS} value={situation} onChange={setSituation} />
      </div>
      <p className="depboard__caption">
        {board?.caption ?? 'Comparing usage against the value it’s justified by.'}{' '}
        <Tooltip content={HOW}><span className="depboard__how">How this works</span></Tooltip>
      </p>

      {error && <p className="depboard__msg">{error}</p>}
      {!board && !error && <SkeletonLoader />}
      {board && (
        <div className="dep2col">
          <Column side="over" title="Over-used"
            caption="Deployed more than the model’s value warrants — trusted beyond impact."
            rows={board.over} />
          <Column side="under" title="Under-used"
            caption="Deployed less than the model’s value warrants — room to play them more."
            rows={board.under} />
        </div>
      )}
    </section>
  )
}
