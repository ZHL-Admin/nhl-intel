import { UncertaintyBand } from '../common'
import { OffseasonLineupSlot } from '../../api/types'
import { fmtWar } from '../../utils/forecastFormat'

const VALUE_DOMAIN: [number, number] = [0, 8]
const FWD_ORDER: Record<string, number> = { L: 0, C: 1, R: 2 }

function chunk<T>(arr: T[], n: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n))
  return out
}

function SlotRow({ s, isIn }: { s: OffseasonLineupSlot; isIn: boolean }) {
  const v = s.projected_war
  return (
    <div className="lslot">
      <div className="lslot__top">
        {s.position && <span className="lslot__pos mono">{s.position}</span>}
        <span className="lslot__name">{s.name ?? `#${s.player_id}`}</span>
        {isIn && <span className="lslot__in">IN</span>}
        <span className="lslot__val mono">{fmtWar(v)}</span>
      </div>
      <div className="lslot__band">
        <UncertaintyBand value={v} lo={v - s.war_sd} hi={v + s.war_sd}
          domainMin={VALUE_DOMAIN[0]} domainMax={VALUE_DOMAIN[1]} />
        <span className="lslot__sd mono">±{s.war_sd.toFixed(1)}</span>
      </div>
    </div>
  )
}

function LineCard({ title, slots, arrivals }: { title: string; slots: OffseasonLineupSlot[]; arrivals: Set<number> }) {
  return (
    <div className="lcard">
      <div className="lcard__head">{title}</div>
      {slots.map((s) => <SlotRow key={s.slot} s={s} isIn={s.player_id != null && arrivals.has(s.player_id)} />)}
    </div>
  )
}

/** §04 — Forwards (4 trios) · Defense (3 pairs) · Goaltending (starter + backup). Real line data is
 * not in the payload, so units are grouped by projected value and labeled illustrative. */
export default function ProjectedLineup({ lineup, arrivals }: {
  lineup: OffseasonLineupSlot[]; arrivals: Set<number>
}) {
  const realPlayers = lineup.filter((s) => s.player_id != null && !s.replacement)
  const fwd = realPlayers.filter((s) => s.position && 'CLR'.includes(s.position))
  const def = realPlayers.filter((s) => s.position === 'D')
  const goalies = realPlayers.filter((s) => s.position === 'G')

  const fwdLines = chunk(fwd, 3).slice(0, 4).map((trio) =>
    [...trio].sort((a, b) => (FWD_ORDER[a.position ?? ''] ?? 3) - (FWD_ORDER[b.position ?? ''] ?? 3)))
  const defPairs = chunk(def, 2).slice(0, 3)

  return (
    <div className="plineup">
      <p className="sec__subtitle">
        Valued slot by slot; new arrivals flagged. Arrangement illustrative — players ordered by
        projected value, not confirmed line assignments.
      </p>

      <div className="plineup__group">
        <div className="plineup__gtitle">Forwards</div>
        <div className="plineup__grid plineup__grid--fwd">
          {fwdLines.map((trio, i) => <LineCard key={i} title={`Line ${i + 1}`} slots={trio} arrivals={arrivals} />)}
        </div>
      </div>

      <div className="plineup__group">
        <div className="plineup__gtitle">Defense</div>
        <div className="plineup__grid plineup__grid--def">
          {defPairs.map((pair, i) => <LineCard key={i} title={`Pair ${i + 1}`} slots={pair} arrivals={arrivals} />)}
        </div>
      </div>

      <div className="plineup__group">
        <div className="plineup__gtitle">Goaltending</div>
        <div className="plineup__grid plineup__grid--goalie">
          <div className="lcard">
            <div className="lcard__head">Starter</div>
            {goalies[0]
              ? <SlotRow s={goalies[0]} isIn={goalies[0].player_id != null && arrivals.has(goalies[0].player_id)} />
              : <div className="lslot lslot--empty">Not yet projected —</div>}
          </div>
          <div className="lcard">
            <div className="lcard__head">Backup</div>
            {goalies[1]
              ? <SlotRow s={goalies[1]} isIn={goalies[1].player_id != null && arrivals.has(goalies[1].player_id)} />
              : <div className="lslot lslot--empty">Not yet projected —</div>}
          </div>
        </div>
      </div>
    </div>
  )
}
