import { UncertaintyBand, PlayerAvatar } from '../common'
import { OffseasonLineupSlot, OffseasonLineFits, OffseasonLineFit } from '../../api/types'
import { fmtWar } from '../../utils/forecastFormat'

const F_HEAD = ['LW', 'C', 'RW']
const D_HEAD = ['LD', 'RD']

/** Slot number of a lineup label (F7 -> 7). The offseason lineup is line-grouped (F1-3 = line 1, ...)
 * so line = (num-1)/perLine and column = (num-1)%perLine gives a clean, collision-free depth chart. */
const slotNum = (slot: string): number => parseInt(String(slot).slice(1), 10) || 0

/** Place real players into a fixed [nLines][perLine] grid by slot number; empty cells stay null so the
 * renderer draws a replacement placeholder in place (every line keeps its columns — no floating row). */
function grid(slots: OffseasonLineupSlot[], perLine: number, nLines: number): (OffseasonLineupSlot | null)[][] {
  const rows: (OffseasonLineupSlot | null)[][] = Array.from({ length: nLines }, () => Array(perLine).fill(null))
  for (const s of slots) {
    const n = slotNum(s.slot)
    const r = Math.floor((n - 1) / perLine)
    const c = (n - 1) % perLine
    if (r >= 0 && r < nLines && c >= 0 && c < perLine) rows[r][c] = s
  }
  return rows
}

/** Shared band scale for a position group: the largest (value + sd), padded, floored so a weak group
 * still reads. Skaters and goalies scale separately (goalie bands are ~3x wider). */
function bandMax(slots: OffseasonLineupSlot[]): number {
  const reals = slots.filter((s) => s.player_id != null && !s.replacement)
  return Math.max(0.5, ...reals.map((s) => s.projected_war + s.war_sd)) * 1.05
}

function FitBadge({ fit }: { fit?: OffseasonLineFit | null }) {
  if (!fit?.grade) return <span className="dc__fit dc__fit--none" aria-hidden />
  return <span className={`dc__fit dc__fit--${fit.grade[0].toLowerCase()}`} title="Cold-start line-fit grade (xGF%)">{fit.grade}</span>
}

function Slot({ s, team, domainMax, isIn }: {
  s: OffseasonLineupSlot | null; team?: string | null; domainMax: number; isIn: boolean
}) {
  if (!s || s.player_id == null) {
    return (
      <div className="dcslot dcslot--empty">
        <span className="dcslot__ph">Replacement level</span>
        <UncertaintyBand value={0} lo={0} hi={0} domainMin={0} domainMax={domainMax} size="sm" colorVar="var(--color-border-strong)" />
      </div>
    )
  }
  const v = s.projected_war
  // Realized last-season line only — the engine projects WAR, never a projected counting line.
  const counting = s.gp != null ? `${s.gp} GP · ${s.g ?? 0}-${s.a ?? 0}-${s.p ?? 0}` : null
  return (
    <div className="dcslot">
      <div className="dcslot__id">
        <PlayerAvatar id={s.player_id} team={team} name={s.name} size={30} showTeamLogo={false} />
        <span className="dcslot__name" title={s.name ?? undefined}>
          {s.name ?? `#${s.player_id}`}
          {isIn && <span className="dcslot__in">IN</span>}
        </span>
        <span className="dcslot__war mono" title="Projected WAR">{fmtWar(v)}</span>
      </div>
      <span className="dcslot__meta mono" title={counting ? `${s.g ?? 0} G · ${s.a ?? 0} A · ${s.p ?? 0} P` : undefined}>
        {s.position && <span className="dcslot__pos">{s.position}</span>}
        {s.age != null && <span>{s.age}y</span>}
        {counting && <span className="dcslot__count">{counting}</span>}
      </span>
      <UncertaintyBand value={v} lo={v - s.war_sd} hi={v + s.war_sd} domainMin={0} domainMax={domainMax} size="sm" />
    </div>
  )
}

function Chart({ kind, rows, heads, fits, arrivals, team, domainMax }: {
  kind: 'fwd' | 'def'; rows: (OffseasonLineupSlot | null)[][]; heads: string[]
  fits: (OffseasonLineFit | null)[]; arrivals: Set<number>; team?: string | null; domainMax: number
}) {
  const label = kind === 'fwd' ? 'Line' : 'Pair'
  return (
    <div className={`dc dc--${kind}`}>
      <div className="dc__head">
        <span className="dc__rowlabel" aria-hidden />
        {heads.map((h) => <span key={h} className="dc__colhead mono">{h}</span>)}
        <span className="dc__fithead" aria-hidden />
      </div>
      {rows.map((cells, i) => (
        <div className="dc__row" key={i}>
          <span className="dc__rowlabel">{label} {i + 1}</span>
          {cells.map((c, j) => (
            <Slot key={j} s={c} team={team} domainMax={domainMax}
              isIn={c?.player_id != null && arrivals.has(c.player_id)} />
          ))}
          <FitBadge fit={fits[i]} />
        </div>
      ))}
    </div>
  )
}

/** §04 — the projected depth chart. Forwards: 4 lines x LW/C/RW. Defense: 3 pairs x LD/RD. Goalies:
 * starter + backup. The lineup is deployment-seeded (real observed 5v5 units), so lines carry a real
 * cold-start fit grade — no "arrangement illustrative" caveat. Replacement holes render in place, so
 * every line keeps three slots and every pair two (no floating short row). */
export default function ProjectedLineup({ lineup, arrivals, team, fits }: {
  lineup: OffseasonLineupSlot[]; arrivals: Set<number>; team?: string | null; fits?: OffseasonLineFits | null
}) {
  const fwd = lineup.filter((s) => String(s.slot).startsWith('F'))
  const def = lineup.filter((s) => String(s.slot).startsWith('D'))
  const goalies = lineup.filter((s) => String(s.slot).startsWith('G'))
    .sort((a, b) => slotNum(a.slot) - slotNum(b.slot))

  const fwdRows = grid(fwd, 3, 4)
  const defRows = grid(def, 2, 3)
  const skaterMax = bandMax([...fwd, ...def])
  const goalieMax = bandMax(goalies)

  return (
    <div className="plineup">
      <p className="sec__subtitle">Projected depth chart with each slot's value + band; new arrivals flagged.</p>

      <div className="plineup__group">
        <div className="plineup__gtitle">Forwards</div>
        <Chart kind="fwd" rows={fwdRows} heads={F_HEAD} fits={fits?.forward ?? []}
          arrivals={arrivals} team={team} domainMax={skaterMax} />
      </div>

      <div className="plineup__group">
        <div className="plineup__gtitle">Defense</div>
        <Chart kind="def" rows={defRows} heads={D_HEAD} fits={fits?.defense ?? []}
          arrivals={arrivals} team={team} domainMax={skaterMax} />
      </div>

      <div className="plineup__group">
        <div className="plineup__gtitle">Goaltending</div>
        <div className="dc dc--goalie">
          {(['Starter', 'Backup'] as const).map((role, i) => (
            <div className="dc__row" key={role}>
              <span className="dc__rowlabel">{role}</span>
              <Slot s={goalies[i] ?? null} team={team} domainMax={goalieMax}
                isIn={goalies[i]?.player_id != null && arrivals.has(goalies[i].player_id as number)} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
