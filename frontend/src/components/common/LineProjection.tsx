/**
 * Renders a line-fit projection (Phase 5.2): letter grade, projected xGF% with a confidence
 * band (the uncertainty-whisker pattern), deterministic reasons + risk, observed-history note,
 * the deeper-extrapolation label, a depth-3 member table, and the limitations footer.
 *
 * Shared by the Lineup Lab page and the embedded LineSwapWidget. Drives entirely off the API
 * payload (no client-side computation), so every number shown comes from the model.
 */
import { useState } from 'react'
import { Check, AlertTriangle, ChevronDown, Info } from 'lucide-react'
import { LineFitProjection } from '../../api/types'
import './LineProjection.css'

const GRADE_COLOR: Record<string, string> = {
  A: '#22c55e', B: '#84cc16', C: '#f59e0b', D: '#f97316', F: '#ef4444',
}

// xGF% display scale: lines realistically land ~35–65%; clamp the band into this window.
const LO = 0.35
const HI = 0.65
const pct = (v: number) => `${(Math.min(HI, Math.max(LO, v)) - LO) / (HI - LO) * 100}%`

function ConfidenceBar({ proj }: { proj: LineFitProjection }) {
  const lo = proj.interval_low ?? proj.projected_xgf_pct
  const hi = proj.interval_high ?? proj.projected_xgf_pct
  return (
    <div className="line-proj__bar">
      <div className="line-proj__bar-track">
        <div className="line-proj__bar-mid" />
        <div className="line-proj__bar-band" style={{ left: pct(lo), right: `calc(100% - ${pct(hi)})` }} />
        <div className="line-proj__bar-point" style={{ left: pct(proj.projected_xgf_pct) }} />
      </div>
      <div className="line-proj__bar-scale"><span>35%</span><span>50%</span><span>65%</span></div>
    </div>
  )
}

function CoreProjection({ proj, compact }: { proj: LineFitProjection; compact?: boolean }) {
  const [showTable, setShowTable] = useState(false)
  const color = GRADE_COLOR[proj.grade] ?? '#888'
  return (
    <div className={`line-proj ${compact ? 'line-proj--compact' : ''}`}>
      <div className="line-proj__head">
        <div className="line-proj__grade" style={{ background: color }}>{proj.grade}</div>
        <div className="line-proj__head-meta">
          <div className="line-proj__xgf">
            {(proj.projected_xgf_pct * 100).toFixed(0)}<span className="line-proj__xgf-unit">% xGF</span>
          </div>
          {proj.grade_sentence && <div className="line-proj__sentence">{proj.grade_sentence}</div>}
        </div>
      </div>

      <ConfidenceBar proj={proj} />

      <div className="line-proj__rates">
        <span>xGF/60 <strong>{proj.xgf_per60?.toFixed(2) ?? '—'}</strong></span>
        <span>xGA/60 <strong>{proj.xga_per60?.toFixed(2) ?? '—'}</strong></span>
      </div>

      {proj.deeper_extrapolation && (
        <div className="line-proj__tag line-proj__tag--extrap">
          Deeper extrapolation — these players don’t currently play together.
        </div>
      )}
      {proj.rookie_widened && (
        <div className="line-proj__tag line-proj__tag--rookie">
          Widened interval — a member has limited NHL minutes.
        </div>
      )}

      {proj.reasons.length > 0 && (
        <ul className="line-proj__reasons">
          {proj.reasons.map((r, i) => (
            <li key={i}><Check size={14} className="line-proj__reason-icon" />{r}</li>
          ))}
          {proj.risk && (
            <li className="line-proj__risk"><AlertTriangle size={14} className="line-proj__risk-icon" />{proj.risk}</li>
          )}
        </ul>
      )}

      {proj.observed_blend && (
        <div className="line-proj__observed">
          Blended with {proj.observed_blend.observed_minutes.toFixed(0)} real 5v5 minutes
          (observed {(proj.observed_blend.observed_xgf_pct * 100).toFixed(0)}% xGF,
          weighted {(proj.observed_blend.w_obs * 100).toFixed(0)}%).
        </div>
      )}

      {proj.members.length > 0 && (
        <div className="line-proj__depth">
          <button className="line-proj__depth-toggle" onClick={() => setShowTable(s => !s)}>
            <ChevronDown size={14} className={showTable ? 'line-proj__chev line-proj__chev--open' : 'line-proj__chev'} />
            Model inputs
          </button>
          {showTable && (
            <table className="line-proj__table">
              <thead>
                <tr><th>Player</th><th>Arch</th><th>Off</th><th>Def</th><th>Fin</th><th>5v5 min</th></tr>
              </thead>
              <tbody>
                {proj.members.map(m => (
                  <tr key={m.player_id}>
                    <td>{m.name}</td>
                    <td className="line-proj__td-arch">{m.archetype ?? '—'}</td>
                    <td>{m.off_impact?.toFixed(2) ?? '—'}</td>
                    <td>{m.def_impact?.toFixed(2) ?? '—'}</td>
                    <td>{m.finishing?.toFixed(1) ?? '—'}</td>
                    <td>{m.toi_5v5?.toFixed(0) ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

export default function LineProjection({ proj }: { proj: LineFitProjection }) {
  if (proj.line_type === 'UNIT5' && proj.forward_trio && proj.defense_pair) {
    const color = GRADE_COLOR[proj.grade] ?? '#888'
    return (
      <div className="line-proj line-proj--unit">
        <div className="line-proj__head">
          <div className="line-proj__grade" style={{ background: color }}>{proj.grade}</div>
          <div className="line-proj__head-meta">
            <div className="line-proj__xgf">{(proj.projected_xgf_pct * 100).toFixed(0)}<span className="line-proj__xgf-unit">% xGF (unit)</span></div>
            <div className="line-proj__sentence">Combined 5-skater unit (forward weight 0.6, defense 0.4).</div>
          </div>
        </div>
        <div className="line-proj__unit-parts">
          <div><div className="line-proj__unit-label">Forward trio</div><CoreProjection proj={proj.forward_trio} compact /></div>
          <div><div className="line-proj__unit-label">Defense pair</div><CoreProjection proj={proj.defense_pair} compact /></div>
        </div>
        {proj.limitations && <div className="line-proj__limit"><Info size={13} />{proj.limitations}</div>}
      </div>
    )
  }
  return (
    <>
      <CoreProjection proj={proj} />
      {proj.limitations && <div className="line-proj__limit"><Info size={13} />{proj.limitations}</div>}
    </>
  )
}
