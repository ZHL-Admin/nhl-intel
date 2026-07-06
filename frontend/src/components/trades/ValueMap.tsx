/**
 * League value map (Handoff 6, surface 5A) — one bubble per trader entity (team or GM): X = value
 * given up (WAR), Y = value gained (WAR), a 45° break-even diagonal (above it = net positive). Bubble
 * colored by team, sized by trade count. Click an entity to open its dossier. The Traders landing.
 */
import {
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid,
  ReferenceLine, Tooltip as RTooltip, Cell, Label, LabelList,
} from 'recharts'
import { getTeamColor } from '../../utils/teams'
import { ValueMapPoint } from '../../api/trades'

function MapTip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const p: ValueMapPoint = payload[0].payload
  const r = p.record
  return (
    <div className="vm-tip">
      <div className="vm-tip__name">{p.label}</div>
      <div className="vm-tip__row"><span>net</span><span className="mono">{p.net_war >= 0 ? '+' : '−'}{Math.abs(p.net_war).toFixed(1)} ± {p.net_band_hw.toFixed(1)}</span></div>
      <div className="vm-tip__row"><span>gained / gave up</span><span className="mono">{p.gained_war.toFixed(1)} / {p.given_up_war.toFixed(1)}</span></div>
      <div className="vm-tip__row"><span>record</span><span className="mono">{r.decisive_wins}-{r.edge}-{r.even}-{r.losses}</span></div>
      <div className="vm-tip__row"><span>trades</span><span className="mono">{p.trade_count}</span></div>
    </div>
  )
}

export default function ValueMap({ points, onSelect }: {
  points: ValueMapPoint[]; onSelect: (id: string) => void
}) {
  if (!points.length) return <div className="vm-empty">No trades in this filter.</div>
  const max = Math.ceil(Math.max(1, ...points.map((p) => Math.max(p.given_up_war, p.gained_war))) * 1.08)
  // raw coordinates unchanged; the σ cue is visual emphasis only — clear entities solid + labeled,
  // leans normal, the indistinguishable cluster muted/low-opacity so it reads as a cluster.
  const emph = (s: string) => (s === 'clear' ? 0.95 : s === 'leans' ? 0.6 : 0.22)
  const data = points.map((p) => ({ ...p, x: p.given_up_war, y: p.gained_war,
    _clabel: p.separation === 'clear' ? p.label : '' }))

  return (
    <ResponsiveContainer width="100%" height={460}>
      <ScatterChart margin={{ top: 16, right: 24, bottom: 28, left: 8 }}
        role="img" aria-label="Trader value map: value given up versus value gained, in WAR. Points above the diagonal gained more than they gave up.">
        <CartesianGrid vertical={false} stroke="var(--color-border-subtle)" />
        <XAxis type="number" dataKey="x" domain={[0, max]} stroke="var(--color-border)"
          tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}>
          <Label value="Value given up (WAR)" position="insideBottom" dy={16} style={{ fontSize: 11, fill: 'var(--color-text-muted)' }} />
        </XAxis>
        <YAxis type="number" dataKey="y" domain={[0, max]} stroke="var(--color-border)"
          tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}>
          <Label value="Value gained (WAR)" angle={-90} position="insideLeft" dy={60} style={{ fontSize: 11, fill: 'var(--color-text-muted)' }} />
        </YAxis>
        <ZAxis type="number" dataKey="trade_count" range={[40, 520]} />
        <ReferenceLine segment={[{ x: 0, y: 0 }, { x: max, y: max }]} stroke="var(--color-border-strong)" strokeDasharray="5 4" />
        <RTooltip content={<MapTip />} cursor={{ strokeDasharray: '3 3' }} />
        <Scatter data={data} onClick={(d: any) => d?.id && onSelect(d.id)} cursor="pointer">
          {data.map((p) => (
            <Cell key={p.id} fill={getTeamColor(p.team_abbrev_for_color)} fillOpacity={emph(p.separation)}
              stroke={p.separation === 'clear' ? 'var(--color-text-primary)' : 'var(--color-bg-surface)'}
              strokeWidth={p.separation === 'clear' ? 1.5 : 1} />
          ))}
          <LabelList dataKey="_clabel" position="top" style={{ fontSize: 10, fill: 'var(--color-text-secondary)' }} />
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  )
}
