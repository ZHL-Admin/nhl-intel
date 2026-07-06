import type { PlayerContext } from '../../api/types'
import './ContextTab.css'

interface Props {
  context: PlayerContext | null
  loading?: boolean
}

const pctLabel = (p?: number | null) => (p == null ? '—' : `${Math.round(p * 100)}th`)
const rate = (v?: number | null) => (v == null ? '—' : v.toFixed(3))

/** Layer-2 context: QoC/QoT (null percentiles muted), strength splits, zone deployment, top WOWY
 * partners, and the fit deep-links. One fetch (/players/{id}/context). */
export default function ContextTab({ context: c, loading }: Props) {
  if (loading) return <div className="ctx__msg">Loading context…</div>
  if (!c) return <div className="ctx__msg">No context available for this player-season.</div>

  const q = c.quality
  return (
    <div className="ctx">
      {/* Quality of competition / teammates */}
      <section className="ctx__card">
        <h3 className="ctx__h">Quality of competition &amp; teammates</h3>
        {q ? (
          <div className="ctx__qoc">
            {([['Competition (QoC)', q.qoc_pctile, q.qoc_war_rate],
               ['Teammates (QoT)', q.qot_pctile, q.qot_war_rate]] as const).map(([label, pct, r]) => {
              const muted = pct == null
              return (
                <div key={label} className={`ctx__dial${muted ? ' ctx__dial--muted' : ''}`}>
                  <div className="ctx__dial-pct">{pctLabel(pct)}</div>
                  <div className="ctx__dial-lbl">{label}</div>
                  <div className="ctx__dial-rate">
                    rate {rate(r)}{muted ? ' · below 5v5 floor, percentile muted' : ' pctile'}
                  </div>
                </div>
              )
            })}
          </div>
        ) : <p className="ctx__none">No 5v5 matchup data this season.</p>}
      </section>

      {/* Zone deployment */}
      {c.zone_deployment && (
        <section className="ctx__card">
          <h3 className="ctx__h">Zone deployment (5v5 starts)</h3>
          <div className="ctx__zones">
            <span>OZ {(c.zone_deployment.ozs_pct * 100).toFixed(0)}%</span>
            <span>NZ {(c.zone_deployment.nzs_pct * 100).toFixed(0)}%</span>
            <span>DZ {(c.zone_deployment.dzs_pct * 100).toFixed(0)}%</span>
          </div>
        </section>
      )}

      {/* Strength splits */}
      {c.strength_splits.length > 0 && (
        <section className="ctx__card">
          <h3 className="ctx__h">Strength-state splits</h3>
          <table className="ctx__table">
            <thead><tr><th>Situation</th><th>TOI/GP</th><th>P/60</th><th>xGF%/CF%</th></tr></thead>
            <tbody>
              {c.strength_splits.map((s) => (
                <tr key={s.situation}>
                  <td>{s.situation}</td>
                  <td>{s.toi_per_gp?.toFixed(1) ?? '—'}</td>
                  <td>{s.points_per60?.toFixed(2) ?? '—'}</td>
                  <td>{s.cf_pct != null ? `${(s.cf_pct * 100).toFixed(1)}%` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* With / without (top-5 WOWY) */}
      {c.wowy_top.length > 0 && (
        <section className="ctx__card">
          <h3 className="ctx__h">With / without — top partners (5v5)</h3>
          <table className="ctx__table">
            <thead><tr><th>Partner</th><th>Together xGF%</th><th>Δ with help</th><th></th></tr></thead>
            <tbody>
              {c.wowy_top.map((w) => (
                <tr key={w.partner_id} className={w.small_sample ? 'ctx__muted-row' : ''}>
                  <td>{w.partner_name ?? w.partner_id}</td>
                  <td>{w.xgf_pct_together != null ? `${(w.xgf_pct_together * 100).toFixed(1)}%` : '—'}</td>
                  <td>{w.together_minus_focal_alone != null
                    ? `${w.together_minus_focal_alone >= 0 ? '+' : ''}${(w.together_minus_focal_alone * 100).toFixed(1)}%` : '—'}</td>
                  <td>{w.small_sample ? <span className="ctx__flag">small sample</span> : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Try him elsewhere */}
      <section className="ctx__card ctx__fit">
        <h3 className="ctx__h">Try him elsewhere</h3>
        <a className="ctx__fit-link" href={c.fit.player_fit}>See him on another team →</a>
        <a className="ctx__fit-link" href={c.fit.lineup_lab}>Slot him into a line →</a>
      </section>
    </div>
  )
}
