/**
 * Inline Leaderboard-row preview (Players page). A COMPOSITION of existing pieces at a smaller
 * zoom — never a new visualization. Three zones: identity + archetype tags + verdict (left),
 * the SkillRadar centerpiece (center), value lenses + ranked base stats (right). Swaps vocabulary
 * by entity kind exactly like the rows. It's a preview, not a destination: "View full profile"
 * is the handoff. Lazy-fetches the clicked player only and caches it so re-open is instant.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
// (headshot/logo helpers now live in the shared PlayerAvatar)
import SkillRadar from '../visualizations/SkillRadar'
import OverallSummary from '../common/OverallSummary'
import PlayerAvatar from '../common/PlayerAvatar'
import SkeletonLoader from '../common/SkeletonLoader'
import { getPlayerRadar, getPlayerDetail, getPlayerPreview } from '../../api/players'
import { getGoalieRadar, getGoalieSeason, getGoaliePreview } from '../../api/goalies'
import { playerLabelsFromRadar } from '../../api/labels'
import {
  PlayerRadar, GoalieRadar, PlayerDetail, GoalieSeason, PlayerPreview, GoaliePreview, PreviewStat,
  OverallSummary as OverallData,
} from '../../api/types'
import './PlayerRowExpansion.css'

export interface ExpansionTarget {
  id: number
  name?: string | null
  team?: string | null
  position?: string | null
  entityKind: 'skater' | 'goalie'
}

type Payload =
  | { kind: 'skater'; radar: PlayerRadar | null; detail: PlayerDetail | null; preview: PlayerPreview | null }
  | { kind: 'goalie'; radar: GoalieRadar | null; season: GoalieSeason | null; preview: GoaliePreview | null }

const _cache = new Map<string, Payload>()

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'], v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

function fmtStat(s: PreviewStat): string {
  const v = s.value
  if (v == null) return '—'
  switch (s.fmt) {
    case 'int': return Math.round(v).toString()
    case 'rate': return v.toFixed(2)
    case 'min': return v.toFixed(1)
    case 'pct1': return `${(v * 100).toFixed(1)}%`
    case 'pct3': return v.toFixed(3).replace(/^0/, '')   // .912
    case 'plus': return `${v >= 0 ? '+' : ''}${v.toFixed(1)}`
    default: return String(v)
  }
}

const POS_NOUN: Record<string, string> = { F: 'forwards', D: 'defensemen', G: 'goalies' }

/** Ranked base-stats table: every stat shows its within-position rank in a mono column. */
function StatTable({ stats }: { stats: PreviewStat[] }) {
  return (
    <table className="pxe-stats">
      <tbody>
        {stats.map((s) => (
          <tr key={s.key}>
            <th scope="row">{s.label}</th>
            <td className="pxe-stats__v">{fmtStat(s)}</td>
            <td className="pxe-stats__rank">{s.rank != null ? ordinal(s.rank) : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const fmtSigned = (v?: number | null, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}`)

export default function PlayerRowExpansion({ target, season }: { target: ExpansionTarget; season: string }) {
  const navigate = useNavigate()
  const [payload, setPayload] = useState<Payload | null>(null)
  const [loading, setLoading] = useState(true)
  const cacheKey = `${target.entityKind}:${target.id}:${season}`
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    const cached = _cache.get(cacheKey)
    if (cached) { setPayload(cached); setLoading(false); return }
    setLoading(true); setPayload(null)
    const run = target.entityKind === 'goalie'
      ? Promise.allSettled([getGoalieRadar(target.id, season), getGoalieSeason(target.id, season), getGoaliePreview(target.id, season)])
          .then(([r, s, p]): Payload => ({
            kind: 'goalie',
            radar: r.status === 'fulfilled' ? r.value : null,
            season: s.status === 'fulfilled' ? s.value : null,
            preview: p.status === 'fulfilled' ? p.value : null,
          }))
      : Promise.allSettled([getPlayerRadar(target.id, season), getPlayerDetail(target.id, season), getPlayerPreview(target.id, season)])
          .then(([r, d, p]): Payload => ({
            kind: 'skater',
            radar: r.status === 'fulfilled' ? r.value : null,
            detail: d.status === 'fulfilled' ? d.value : null,
            preview: p.status === 'fulfilled' ? p.value : null,
          }))
    run.then((res) => {
      _cache.set(cacheKey, res)
      if (mounted.current) { setPayload(res); setLoading(false) }
    })
    return () => { mounted.current = false }
  }, [cacheKey, target.id, target.entityKind, season])

  const profileHref = `/players/${target.id}`
  const goProfile = () => navigate(profileHref)

  if (loading || !payload) {
    return <div className="pxe" role="region"><div className="pxe__loading"><SkeletonLoader /></div></div>
  }

  // ---- shared identity block ----
  const radarSpokes = payload.radar?.spokes ?? []
  const posNoun = payload.kind === 'skater'
    ? (POS_NOUN[payload.radar?.pos_group ?? ''] ?? 'their position')
    : 'goalies'

  let labels: { overall?: string | null; offensive?: string | null; defensive?: string | null } | null = null
  let age: number | null = null
  let hand: string | null = null
  let verdict: { headline: string; body: string } | null = null
  let overall: OverallData | null = null
  let valueLine: React.ReactNode = null
  let stats: PreviewStat[] = []

  if (payload.kind === 'skater') {
    labels = payload.radar ? playerLabelsFromRadar(payload.radar) : null
    age = payload.preview?.age ?? null
    hand = payload.preview?.shoots ?? null
    stats = payload.preview?.stats ?? []
    const value = payload.detail?.value ?? null
    overall = value?.overall ?? null
    if (value?.read) verdict = { headline: value.read.headline, body: value.read.body }
    if (value) {
      valueLine = (
        <div className="pxe-warline">
          <span className="pxe-warline__v">{fmtSigned(value.war)} <small>WAR</small></span>
          <span className="pxe-warline__v">{fmtSigned(value.gar)} <small>GAR</small></span>
          {value.war_sd != null && <span className="pxe-warline__band">± {value.war_sd.toFixed(1)}</span>}
        </div>
      )
    }
  } else {
    age = payload.preview?.age ?? null
    hand = payload.preview?.catches ?? null
    stats = payload.preview?.stats ?? []
    const s = payload.season
    overall = s?.overall ?? null
    if (s) {
      valueLine = (
        <div className="pxe-warline">
          {s.value && <span className="pxe-warline__v">{fmtSigned(s.value.war)} <small>WAR</small></span>}
          <span className="pxe-warline__v">{fmtSigned(s.gsax)} <small>GSAx</small></span>
          {s.our_hd_gsax != null && <span className="pxe-warline__v">{fmtSigned(s.our_hd_gsax)} <small>HD GSAx</small></span>}
        </div>
      )
    }
  }

  const meta = [target.position, target.team, age != null ? `Age ${age}` : null, hand ? `${hand}` : null]
    .filter(Boolean).join(' · ')

  const hasRadar = radarSpokes.filter((s) => s.percentile != null).length >= 3

  return (
    <div className="pxe" role="region" aria-label={`${target.name ?? 'Player'} preview`}>
      {/* 1. IDENTITY — headshot, name/meta, archetype tags, then the value-vs-impact verdict */}
      <div className="pxe__identity">
        <div className="pxe__id">
          <PlayerAvatar id={target.id} team={target.team} name={target.name} size={60} />
          <div className="pxe__idtext">
            <div className="pxe__name">{target.name ?? target.id}</div>
            <div className="pxe__meta">{meta}</div>
            {labels && (labels.offensive || labels.defensive || labels.overall) && (
              <div className="pxe__chips">
                {labels.offensive && <span className="pxe__chip">{labels.offensive}</span>}
                {labels.defensive && <span className="pxe__chip pxe__chip--quiet">{labels.defensive}</span>}
                {!labels.offensive && !labels.defensive && labels.overall && <span className="pxe__chip">{labels.overall}</span>}
              </div>
            )}
          </div>
        </div>
        {verdict && (
          <p className="pxe__verdict"><strong>{verdict.headline}</strong> {verdict.body}</p>
        )}
      </div>

      {/* 2. CONDENSED OVERALL STRIP (percentile + compact component bars + WAR/GAR readout) */}
      {overall
        ? <OverallSummary overall={overall} variant="strip" aside={valueLine} />
        : valueLine ? <div className="pxe__lenses-fallback">{valueLine}</div> : null}

      {/* 3. RADAR — the full-width centrepiece (its Skill/Usage/Style legend sits tight beneath) */}
      <div className="pxe__radar">
        {hasRadar
          ? <SkillRadar spokes={radarSpokes} baseline={payload.radar?.baseline ?? `Percentile vs ${posNoun}`} size={440} />
          : <p className="pxe__empty">No radar this season.</p>}
      </div>

      {/* 4. SEASON STATS (full width, each with its within-position rank) */}
      <div className="pxe__base">
        <div className="pxe__base-head">Season stats <span>· rank vs {posNoun}</span></div>
        {stats.length > 0 ? <StatTable stats={stats} /> : <p className="pxe__empty">No stats this season.</p>}
      </div>

      {/* 5. handoff */}
      <button className="pxe__profile" onClick={goProfile}>
        View full profile <ArrowRight size={15} />
      </button>
    </div>
  )
}
