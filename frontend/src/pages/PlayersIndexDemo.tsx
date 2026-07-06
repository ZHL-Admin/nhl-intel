import { Fragment } from 'react'
import TierBadge from '../components/common/TierBadge'

// M3.5 Players index demo (D14 / §10.5): rank by assessed_war; filtered view = tier separators
// with counts, no per-row chips; mixed view = per-row chips, no separators, visibly wider goalie
// bands. Shared-axis interval (thin track, ±1 sd band, point dot). One typeface, tabular numerals.

interface Row {
  id: number; name: string; pos: string; kind: 'skater' | 'goalie'
  war: number; sd: number; tier: string; tierLabel: string; conf: string
}

// Domain shared across all rows (WAR), so bands/dots sit on one axis.
const DOMAIN: [number, number] = [-1, 8]
const x = (v: number) => ((v - DOMAIN[0]) / (DOMAIN[1] - DOMAIN[0])) * 100

function IntervalBar({ war, sd, wide }: { war: number; sd: number; wide?: boolean }) {
  const lo = x(war - sd), hi = x(war + sd), dot = x(war), zero = x(0)
  return (
    <span className="ixrow__bar" title={`${war.toFixed(1)} ± ${sd.toFixed(1)} WAR`}>
      <span className="ixrow__track" />
      <span className="ixrow__zero" style={{ left: `${zero}%` }} />
      <span className={`ixrow__band ${wide ? 'is-wide' : ''}`} style={{ left: `${lo}%`, width: `${hi - lo}%` }} />
      <span className="ixrow__dot" style={{ left: `${dot}%` }} />
    </span>
  )
}

// Filtered (D) — assessed_war desc, full tier groups so separators carry the pool count.
const D_ROWS: Row[] = [
  ...Array.from({ length: 2 }, (_, i) => ({ id: 100 + i, name: ['Cale Makar', 'Quinn Hughes'][i], pos: 'D', kind: 'skater' as const, war: 6.2 - i * 0.9, sd: 1.2, tier: 'elite', tierLabel: 'Elite', conf: 'high' })),
  ...Array.from({ length: 3 }, (_, i) => ({ id: 110 + i, name: ['Roman Josi', 'Adam Fox', 'Zach Werenski'][i], pos: 'D', kind: 'skater' as const, war: 3.6 - i * 0.4, sd: 1.1, tier: 'number_one', tierLabel: 'Number-one defenseman', conf: 'high' })),
  ...Array.from({ length: 3 }, (_, i) => ({ id: 120 + i, name: ['Jaccob Slavin', 'Devon Toews', 'Evan Bouchard'][i], pos: 'D', kind: 'skater' as const, war: 1.9 - i * 0.25, sd: 1.0, tier: 'top_pair', tierLabel: 'Top-pair defenseman', conf: 'medium' })),
  ...Array.from({ length: 2 }, (_, i) => ({ id: 130 + i, name: ['Ryker Evans', 'Nick Perbix'][i], pos: 'D', kind: 'skater' as const, war: 0.25 - i * 0.05, sd: 1.0, tier: 'second_pair', tierLabel: 'Second-pair defenseman', conf: 'low' })),
]
// group counts = tier pool sizes (shown on separators)
const D_COUNTS: Record<string, number> = { elite: 12, number_one: 20, top_pair: 32, second_pair: 64 }

// Mixed (All) — skaters + goalies interleaved by assessed_war; goalies carry visibly wider bands.
const MIXED: Row[] = [
  { id: 200, name: 'Connor McDavid', pos: 'F', kind: 'skater', war: 6.5, sd: 1.2, tier: 'elite', tierLabel: 'Elite', conf: 'high' },
  { id: 201, name: 'Cale Makar', pos: 'D', kind: 'skater', war: 6.2, sd: 1.2, tier: 'elite', tierLabel: 'Elite', conf: 'high' },
  { id: 202, name: 'Connor Hellebuyck', pos: 'G', kind: 'goalie', war: 5.8, sd: 3.7, tier: 'elite_starter', tierLabel: 'Elite starter', conf: 'high' },
  { id: 203, name: 'Nathan MacKinnon', pos: 'F', kind: 'skater', war: 5.4, sd: 1.3, tier: 'elite', tierLabel: 'Elite', conf: 'high' },
  { id: 204, name: 'Igor Shesterkin', pos: 'G', kind: 'goalie', war: 4.6, sd: 3.6, tier: 'elite_starter', tierLabel: 'Elite starter', conf: 'high' },
  { id: 205, name: 'Jason Robertson', pos: 'F', kind: 'skater', war: 3.9, sd: 1.1, tier: 'first_line', tierLabel: 'First-line forward', conf: 'high' },
  { id: 206, name: 'Jake Oettinger', pos: 'G', kind: 'goalie', war: 2.9, sd: 3.4, tier: 'starter', tierLabel: 'Starter', conf: 'medium' },
]

const CONF_DOT: Record<string, string> = { high: 'var(--color-success)', medium: 'var(--color-warning)', low: 'var(--color-text-tertiary)' }

// Separator label = tier label pluralized to the position group (e.g. "Elite defensemen").
const POS_PLURAL: Record<string, string> = { F: 'forwards', D: 'defensemen', G: 'goalies' }
function sepLabel(tierLabel: string, pos: string): string {
  if (tierLabel === 'Elite') return `Elite ${POS_PLURAL[pos] ?? 'players'}`
  return tierLabel.replace(/defenseman$/, 'defensemen').replace(/forward$/, 'forwards').replace(/goalie$/, 'goalies')
}

function Rows({ rows, mixed }: { rows: Row[]; mixed: boolean }) {
  let lastTier = ''
  return (
    <div className="ixlist">
      {rows.map((r, i) => {
        const sep = !mixed && r.tier !== lastTier
        lastTier = r.tier
        return (
          <Fragment key={r.id}>
            {sep && (
              <div className="ixsep">
                {sepLabel(r.tierLabel, r.pos)} <span className="ixsep__count">· {D_COUNTS[r.tier] ?? '—'}</span>
              </div>
            )}
            <div className="ixrow">
              <span className="ixrow__rank">{i + 1}</span>
              <span className="ixrow__name">
                {r.name}
                <span className={`ixrow__pos ixrow__pos--${r.kind}`}>{r.pos}</span>
                {mixed && <TierBadge label={r.tierLabel} confidence={r.conf} size="sm" />}
              </span>
              <IntervalBar war={r.war} sd={r.sd} wide={r.kind === 'goalie'} />
              <span className="ixrow__val">
                <b>{r.war.toFixed(1)}</b> <span className="ixrow__u">WAR</span>
                <span className="ixrow__band">± {r.sd.toFixed(1)}</span>
                <span className="ixrow__dot" style={{ background: CONF_DOT[r.conf] }} />
              </span>
            </div>
          </Fragment>
        )
      })}
    </div>
  )
}

export default function PlayersIndexDemo() {
  return (
    <div className="ixdemo">
      <style>{CSS}</style>
      <h1>Players index (M3.5)</h1>
      <p className="ixcap">Ranked by assessed WAR, the reliability-shrunk estimate. Bands show ±1 sd. 279 qualified.
        <a className="ixcap__link" href="#"> How we measure value</a></p>

      <h2>Filtered · Defensemen — tier separators with counts, no per-row chips</h2>
      <Rows rows={D_ROWS} mixed={false} />

      <h2>Mixed · All — per-row tier chips, no separators, goalie bands visibly wider</h2>
      <Rows rows={MIXED} mixed={true} />
    </div>
  )
}

const CSS = `
.ixdemo { max-width: 860px; margin: 0 auto; padding: var(--space-6); font-family: var(--font-sans); }
.ixdemo h1 { margin: 0 0 var(--space-1); }
.ixdemo h2 { font-size: var(--text-sm); color: var(--color-text-secondary); margin: var(--space-5) 0 var(--space-2); font-weight: 600; }
.ixcap { font-size: var(--text-xs); color: var(--color-text-tertiary); margin: 0 0 var(--space-3); }
.ixcap__link { color: var(--color-accent); text-decoration: none; }
.ixlist { border: 1px solid var(--color-border); border-radius: var(--radius-lg); overflow: hidden; }
.ixsep { background: var(--color-bg-elevated); padding: 6px var(--space-3); font-size: var(--text-xs); font-weight: 700; color: var(--color-text-secondary); border-top: 1px solid var(--color-border); }
.ixsep:first-child { border-top: none; }
.ixsep__count { color: var(--color-text-tertiary); font-weight: 500; font-variant-numeric: tabular-nums; }
.ixrow { display: grid; grid-template-columns: 34px 1fr 220px 130px; align-items: center; gap: var(--space-3); padding: 8px var(--space-3); border-top: 1px solid var(--color-border); }
.ixrow__rank { font-variant-numeric: tabular-nums; color: var(--color-text-tertiary); font-size: var(--text-sm); text-align: right; }
.ixrow__name { display: flex; align-items: center; gap: var(--space-2); font-weight: 500; }
.ixrow__pos { font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: var(--radius-sm); background: var(--color-bg-elevated); color: var(--color-text-secondary); }
.ixrow__pos--goalie { color: var(--color-accent); }
.ixrow__bar { position: relative; height: 20px; }
.ixrow__track { position: absolute; top: 50%; left: 0; right: 0; height: 2px; background: var(--color-border); transform: translateY(-50%); }
.ixrow__zero { position: absolute; top: 3px; bottom: 3px; width: 1px; background: var(--color-border); }
.ixrow__band { position: absolute; top: 50%; height: 8px; transform: translateY(-50%); background: color-mix(in srgb, var(--color-accent) 22%, transparent); border-radius: var(--radius-sm); }
.ixrow__band.is-wide { background: color-mix(in srgb, var(--color-accent) 14%, transparent); }
.ixrow__dot { position: absolute; top: 50%; width: 9px; height: 9px; border-radius: 50%; background: var(--color-accent); transform: translate(-50%, -50%); }
.ixrow__val { display: flex; align-items: center; gap: 6px; justify-content: flex-end; font-variant-numeric: tabular-nums; }
.ixrow__val b { font-weight: 700; }
.ixrow__u { font-size: 10px; color: var(--color-text-tertiary); }
.ixrow__band { }
.ixrow__val .ixrow__band { position: static; transform: none; background: none; height: auto; font-size: var(--text-xs); color: var(--color-text-tertiary); }
.ixrow__val .ixrow__dot { position: static; transform: none; }
`
