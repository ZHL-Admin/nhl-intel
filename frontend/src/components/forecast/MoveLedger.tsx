import { UncertaintyBand } from '../common'
import { RosterMove } from '../../api/types'
import { fmtWar, fmtBand, fmtRating } from '../../utils/forecastFormat'

const WAR_DOMAIN: [number, number] = [-3.5, 3.5]

function initials(name: string | null | undefined): string {
  if (!name) return '··'
  const p = name.trim().split(/\s+/)
  return ((p[0]?.[0] ?? '') + (p[p.length - 1]?.[0] ?? '')).toUpperCase()
}

function MoveRow({ m, dir, fitNote }: { m: RosterMove; dir: 'in' | 'out'; fitNote?: string | null }) {
  const v = m.delta_contribution
  const lo = v - m.war_sd
  const hi = v + m.war_sd
  return (
    <div className="mrow">
      <span className="mrow__av" aria-hidden>{initials(m.name)}</span>
      <span className="mrow__name">{m.name ?? `#${m.player_id}`}</span>
      <span className="mrow__pos mono">{m.position}</span>
      <span className={`mrow__war mono ${dir === 'in' ? 'is-up' : 'is-down'}`}>
        {fmtWar(v)}
        <span className="mrow__warlabel">proj. WAR</span>
      </span>
      <span className="mrow__band">
        <UncertaintyBand value={v} lo={lo} hi={hi} domainMin={WAR_DOMAIN[0]} domainMax={WAR_DOMAIN[1]} />
        <span className="mrow__bandtext mono">{fmtBand(lo, hi, 1)}</span>
      </span>
      {fitNote && <p className="mrow__fit">{fitNote}</p>}
    </div>
  )
}

/** §02 — OUT and IN columns with a full-width net row. The per-row value is delta_contribution and the
 * columns reconcile to net_delta_war. The team style note attaches once, to the arrival it names. */
export default function MoveLedger({ moves, styleNote, netWar, netGoals }: {
  moves: RosterMove[]; styleNote?: string | null; netWar: number; netGoals: number
}) {
  const ins = moves.filter((m) => m.move_type === 'arrival')
  const outs = moves.filter((m) => m.move_type === 'departure')
  // The style note (one per team, about the biggest arrival) attaches to the arrival it names.
  const fitTargetId = styleNote
    ? (ins.find((m) => m.name && styleNote.includes(m.name)) ?? ins[0])?.player_id
    : null

  return (
    <div className="mledger">
      <p className="sec__subtitle">The bar shows the player's projected-WAR effect; the lighter span behind it is uncertainty.</p>
      <div className="mledger__cols">
        <div className="mledger__col">
          <div className="mledger__coltag mledger__coltag--out">OUT <span className="mono">{outs.length}</span></div>
          {outs.length === 0 && <p className="mledger__none">No departures logged.</p>}
          {outs.map((m, i) => <MoveRow key={`${m.player_id}-${i}`} m={m} dir="out" />)}
        </div>
        <div className="mledger__col">
          <div className="mledger__coltag mledger__coltag--in">IN <span className="mono">{ins.length}</span></div>
          {ins.length === 0 && <p className="mledger__none">No arrivals logged.</p>}
          {ins.map((m, i) => (
            <MoveRow key={`${m.player_id}-${i}`} m={m} dir="in"
              fitNote={m.player_id === fitTargetId ? styleNote : null} />
          ))}
        </div>
      </div>
      <div className="mledger__net">
        <span className="mledger__net-label">Net effect of moves</span>
        <span className={`mledger__net-val mono ${netWar >= 0 ? 'is-up' : 'is-down'}`}>{fmtWar(netWar)} proj WAR</span>
        <span className={`mledger__net-goals mono ${netGoals >= 0 ? 'is-up' : 'is-down'}`}>{fmtRating(netGoals)} goals/game</span>
      </div>
    </div>
  )
}
