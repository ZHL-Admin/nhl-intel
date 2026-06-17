/**
 * Renders a line-fit projection (Phase 5.2). Two variants:
 *  - 'hero'   — the champion result on the Lineup Lab page: large grade, headline xGF%,
 *               a prominent confidence meter, stat tiles, the reasons, member faces, and the
 *               depth table + limitations footer.
 *  - 'inline' — a compact card reused many-times-over inside the embedded LineSwapWidget.
 *
 * Drives entirely off the API payload (no client-side computation), so every number shown
 * comes from the model. `players` (optional) carries the built line so the hero can show faces.
 */
import { useState } from 'react'
import { Check, AlertTriangle, ChevronDown, Info } from 'lucide-react'
import { LineFitProjection, PlayerSearchResult } from '../../api/types'
import { getPlayerHeadshotUrl } from '../../utils/teams'
import './LineProjection.css'

interface GradeMeta { label: string; color: string }
const GRADE_META: Record<string, GradeMeta> = {
  A: { label: 'Elite', color: '#16a34a' },
  B: { label: 'Strong', color: '#65a30d' },
  C: { label: 'Average', color: '#d97706' },
  D: { label: 'Below average', color: '#ea580c' },
  F: { label: 'Struggles', color: '#dc2626' },
}
const gradeMeta = (g: string): GradeMeta => GRADE_META[g?.[0]] ?? { label: 'Projected', color: 'var(--color-text-secondary)' }

// xGF% display scale: lines realistically land ~35–65%; clamp the band into this window.
const LO = 0.35
const HI = 0.65
const pct = (v: number) => `${(Math.min(HI, Math.max(LO, v)) - LO) / (HI - LO) * 100}%`

/* ---- shared confidence meter ---- */
function ConfidenceMeter({ proj, big }: { proj: LineFitProjection; big?: boolean }) {
  const lo = proj.interval_low ?? proj.projected_xgf_pct
  const hi = proj.interval_high ?? proj.projected_xgf_pct
  const color = gradeMeta(proj.grade).color
  return (
    <div className={`lp-meter${big ? ' lp-meter--big' : ''}`}>
      <div className="lp-meter__track">
        <div className="lp-meter__mid" />
        <div className="lp-meter__band" style={{ left: pct(lo), right: `calc(100% - ${pct(hi)})` }} />
        <div className="lp-meter__point" style={{ left: pct(proj.projected_xgf_pct), background: color }}>
          <span className="lp-meter__point-val">{(proj.projected_xgf_pct * 100).toFixed(0)}%</span>
        </div>
      </div>
      <div className="lp-meter__scale">
        <span>35%</span>
        <span className="lp-meter__scale-even">even · 50%</span>
        <span>65%</span>
      </div>
    </div>
  )
}

/* ---- shared stat tiles ---- */
function StatTiles({ proj }: { proj: LineFitProjection }) {
  const diff = proj.xgf_per60 != null && proj.xga_per60 != null ? proj.xgf_per60 - proj.xga_per60 : null
  return (
    <div className="lp-tiles">
      <div className="lp-tile">
        <span className="lp-tile__val">{proj.xgf_per60?.toFixed(2) ?? '—'}</span>
        <span className="lp-tile__label">xGF / 60</span>
      </div>
      <div className="lp-tile">
        <span className="lp-tile__val">{proj.xga_per60?.toFixed(2) ?? '—'}</span>
        <span className="lp-tile__label">xGA / 60</span>
      </div>
      <div className="lp-tile">
        <span className={`lp-tile__val ${diff != null ? (diff >= 0 ? 'lp-pos' : 'lp-neg') : ''}`}>
          {diff != null ? `${diff >= 0 ? '+' : ''}${diff.toFixed(2)}` : '—'}
        </span>
        <span className="lp-tile__label">net / 60</span>
      </div>
    </div>
  )
}

/* ---- shared tags ---- */
function Tags({ proj }: { proj: LineFitProjection }) {
  if (!proj.deeper_extrapolation && !proj.rookie_widened) return null
  return (
    <div className="lp-tags">
      {proj.deeper_extrapolation && (
        <span className="lp-tag lp-tag--extrap">Deeper extrapolation · players don’t currently play together</span>
      )}
      {proj.rookie_widened && (
        <span className="lp-tag lp-tag--rookie">Widened interval · a member has limited NHL minutes</span>
      )}
    </div>
  )
}

/* ---- shared reasons ---- */
function Reasons({ proj, heading }: { proj: LineFitProjection; heading?: boolean }) {
  if (proj.reasons.length === 0 && !proj.risk) return null
  return (
    <div className="lp-reasons">
      {heading && <h4 className="lp-reasons__head">Why this grade</h4>}
      <ul className="lp-reasons__list">
        {proj.reasons.map((r, i) => (
          <li key={i}><Check size={15} className="lp-reasons__icon lp-pos" /><span>{r}</span></li>
        ))}
        {proj.risk && (
          <li className="lp-reasons__risk">
            <AlertTriangle size={15} className="lp-reasons__icon lp-warn" /><span>{proj.risk}</span>
          </li>
        )}
      </ul>
    </div>
  )
}

/* ---- observed-history blend note ---- */
function ObservedNote({ proj }: { proj: LineFitProjection }) {
  if (!proj.observed_blend) return null
  return (
    <div className="lp-observed">
      Blended with <strong>{proj.observed_blend.observed_minutes.toFixed(0)}</strong> real 5v5 minutes
      (observed {(proj.observed_blend.observed_xgf_pct * 100).toFixed(0)}% xGF, weighted{' '}
      {(proj.observed_blend.w_obs * 100).toFixed(0)}%).
    </div>
  )
}

/* ---- depth-3 member table ---- */
function DepthTable({ proj }: { proj: LineFitProjection }) {
  const [open, setOpen] = useState(false)
  if (proj.members.length === 0) return null
  return (
    <div className="lp-depth">
      <button className="lp-depth__toggle" onClick={() => setOpen((s) => !s)}>
        <ChevronDown size={14} className={open ? 'lp-depth__chev lp-depth__chev--open' : 'lp-depth__chev'} />
        Model inputs
      </button>
      {open && (
        <table className="lp-table">
          <thead>
            <tr><th>Player</th><th>Archetype</th><th>Off</th><th>Def</th><th>Fin</th><th>5v5 min</th></tr>
          </thead>
          <tbody>
            {proj.members.map((m) => (
              <tr key={m.player_id}>
                <td>{m.name}</td>
                <td className="lp-table__arch">{m.archetype ?? '—'}</td>
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
  )
}

/* ---- member faces (hero only) ---- */
function FaceStrip({ players }: { players: PlayerSearchResult[] }) {
  if (!players.length) return null
  return (
    <div className="lp-faces">
      {players.map((p) => {
        const src = p.headshot_url || (p.team_abbrev ? getPlayerHeadshotUrl(p.player_id, p.team_abbrev) : '')
        const last = (p.name ?? '').split(' ').slice(-1)[0]
        return (
          <div className="lp-face" key={p.player_id} title={p.name ?? undefined}>
            {src
              ? <img src={src} alt="" onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
              : <span className="lp-face__blank" />}
            <span className="lp-face__name">{last}</span>
          </div>
        )
      })}
    </div>
  )
}

/* ---- compact inline card (LineSwapWidget + unit sub-parts) ---- */
function InlineCard({ proj }: { proj: LineFitProjection }) {
  const meta = gradeMeta(proj.grade)
  return (
    <div className="lp-inline">
      <div className="lp-inline__head">
        <span className="lp-inline__grade" style={{ background: meta.color }}>{proj.grade}</span>
        <span className="lp-inline__xgf">{(proj.projected_xgf_pct * 100).toFixed(0)}<small>% xGF</small></span>
        {proj.grade_sentence && <span className="lp-inline__sentence">{proj.grade_sentence}</span>}
      </div>
      <ConfidenceMeter proj={proj} />
      <div className="lp-inline__rates">
        <span>xGF/60 <strong>{proj.xgf_per60?.toFixed(2) ?? '—'}</strong></span>
        <span>xGA/60 <strong>{proj.xga_per60?.toFixed(2) ?? '—'}</strong></span>
      </div>
      <Tags proj={proj} />
      <Reasons proj={proj} />
      <ObservedNote proj={proj} />
      <DepthTable proj={proj} />
    </div>
  )
}

/* ---- hero card (Lineup Lab champion) ---- */
function HeroCard({ proj, players, unit }: { proj: LineFitProjection; players?: PlayerSearchResult[]; unit?: boolean }) {
  const meta = gradeMeta(proj.grade)
  return (
    <div className="lp-hero" style={{ ['--lp-grade' as string]: meta.color } as React.CSSProperties}>
      <div className="lp-hero__banner">
        <div className="lp-hero__grade">
          <span className="lp-hero__grade-letter">{proj.grade}</span>
          <span className="lp-hero__grade-label">{meta.label}</span>
        </div>
        <div className="lp-hero__headline">
          <div className="lp-hero__metric">
            {(proj.projected_xgf_pct * 100).toFixed(0)}<span className="lp-hero__metric-unit">% xGF</span>
          </div>
          <p className="lp-hero__sentence">
            {proj.grade_sentence ?? `Projected expected-goals share for this ${unit ? '5-skater unit' : 'line'}.`}
          </p>
        </div>
        {players && players.length > 0 && <FaceStrip players={players} />}
      </div>

      {unit ? (
        <div className="lp-hero__body">
          <div className="lp-hero__unit">
            <div><span className="lp-hero__unit-label">Forward trio</span>{proj.forward_trio && <InlineCard proj={proj.forward_trio} />}</div>
            <div><span className="lp-hero__unit-label">Defense pair</span>{proj.defense_pair && <InlineCard proj={proj.defense_pair} />}</div>
          </div>
        </div>
      ) : (
        <div className="lp-hero__body lp-hero__body--split">
          <div className="lp-hero__col">
            <ConfidenceMeter proj={proj} big />
            <StatTiles proj={proj} />
            <Tags proj={proj} />
            <ObservedNote proj={proj} />
          </div>
          <div className="lp-hero__col lp-hero__col--reasons">
            <Reasons proj={proj} heading />
            <DepthTable proj={proj} />
          </div>
        </div>
      )}

      {proj.limitations && (
        <div className="lp-hero__limit"><Info size={14} /><span>{proj.limitations}</span></div>
      )}
    </div>
  )
}

export default function LineProjection({ proj, players, variant = 'inline' }: {
  proj: LineFitProjection
  players?: PlayerSearchResult[]
  variant?: 'hero' | 'inline'
}) {
  const isUnit = proj.line_type === 'UNIT5' && !!proj.forward_trio && !!proj.defense_pair
  if (variant === 'hero') return <HeroCard proj={proj} players={players} unit={isUnit} />
  // inline (swap widget): unit collapses to two stacked compact cards
  if (isUnit) {
    return (
      <div className="lp-inline-unit">
        {proj.forward_trio && <InlineCard proj={proj.forward_trio} />}
        {proj.defense_pair && <InlineCard proj={proj.defense_pair} />}
      </div>
    )
  }
  return <InlineCard proj={proj} />
}
