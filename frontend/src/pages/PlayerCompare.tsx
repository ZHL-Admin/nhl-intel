/**
 * Player compare (Blueprint 2.5.1) — "A or B?" in one screen. Two EntityIdentity M headers, both
 * assessment bands stacked on the same tier ladder, P4 diverging rows over the shared radar spokes,
 * both radars, and a WOWY note when they've shared ice. Pure composition of existing pieces.
 */
import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { PageLayout, PageCard, SkeletonLoader, EntityIdentity, CompareRows, type PlayerIdentity, type CompareRow } from '../components/common'
import AssessmentBand from '../components/players/AssessmentBand'
import SkillRadar from '../components/visualizations/SkillRadar'
import { usePageTitle } from '../hooks/usePageTitle'
import { getPlayerDetail, getPlayerAssessment, getPlayerRadar, getPlayerWowy } from '../api/players'
import type { PlayerDetail, PlayerAssessment, PlayerRadar, PlayerWowy } from '../api/types'
import './PlayerCompare.css'

interface Side { detail: PlayerDetail; assess: PlayerAssessment | null; radar: PlayerRadar }

async function loadSide(id: number): Promise<Side> {
  const [detail, assess, radar] = await Promise.all([
    getPlayerDetail(id), getPlayerAssessment(id).catch(() => null), getPlayerRadar(id),
  ])
  return { detail, assess, radar }
}

function identity(s: Side): PlayerIdentity {
  return {
    id: s.detail.player_id,
    name: s.detail.player_name,
    position: s.detail.position,
    teamAbbrev: s.detail.team_abbrev,
    archetypes: s.detail.durable_archetype ? [s.detail.durable_archetype] : undefined,
    tier: s.assess?.tier_label ? { label: s.assess.tier_label } : null,
    confidenceTone: (s.assess?.confidence_label as 'high' | 'medium' | 'low' | undefined) ?? null,
  }
}

export default function PlayerCompare() {
  usePageTitle('Compare')
  const [params] = useSearchParams()
  const a = Number(params.get('a'))
  const b = Number(params.get('b'))

  const [sides, setSides] = useState<{ a: Side; b: Side } | null>(null)
  const [wowy, setWowy] = useState<PlayerWowy | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!a || !b) { setError(true); return }
    let active = true
    Promise.all([loadSide(a), loadSide(b)])
      .then(([sa, sb]) => active && setSides({ a: sa, b: sb }))
      .catch(() => active && setError(true))
    getPlayerWowy(a).then((w) => active && setWowy(w)).catch(() => {})
    return () => { active = false }
  }, [a, b])

  if (error) {
    return (
      <PageLayout><PageCard title="Compare" subtitle="Two players, side by side.">
        <p className="cmp-page__empty">Pick two players to compare. <Link to="/players">Browse players →</Link></p>
      </PageCard></PageLayout>
    )
  }
  if (!sides) {
    return <PageLayout><PageCard title="Compare"><SkeletonLoader height={400} /></PageCard></PageLayout>
  }

  const A = sides.a, B = sides.b
  // P4 rows over the radar spokes present for both.
  const rows: CompareRow[] = A.radar.spokes
    .filter((sp) => sp.present && sp.percentile != null)
    .map((sp): CompareRow | null => {
      const sb = B.radar.spokes.find((x) => x.key === sp.key && x.present && x.percentile != null)
      if (!sb) return null
      return { label: sp.label, aValue: sp.percentile!, bValue: sb.percentile!, aDisplay: `${Math.round(sp.percentile!)}`, bDisplay: `${Math.round(sb.percentile!)}` }
    })
    .filter((r): r is CompareRow => r !== null)

  const shared = wowy?.partners.find((p) => p.partner_id === b)

  return (
    <PageLayout>
      <PageCard title="Compare" subtitle="Two players, side by side.">
        <div className="cmp-page__heads">
          <EntityIdentity kind="player" size="m" player={identity(A)} link />
          <span className="cmp-page__vs">vs</span>
          <EntityIdentity kind="player" size="m" player={identity(B)} link />
        </div>

        <div className="page-divider" />

        <div className="cmp-page__bands">
          <div className="cmp-page__band"><AssessmentBand assessment={A.assess} /></div>
          <div className="cmp-page__band"><AssessmentBand assessment={B.assess} /></div>
        </div>

        {rows.length > 0 && (
          <section className="cmp-page__section">
            <h2 className="page-region-title">
              Percentiles · <span style={{ color: 'var(--color-data-1)' }}>{A.detail.player_name}</span> vs <span style={{ color: 'var(--color-data-2)' }}>{B.detail.player_name}</span>
            </h2>
            <CompareRows rows={rows} aColor="var(--color-data-1)" bColor="var(--color-data-2)" />
          </section>
        )}

        <div className="page-divider" />

        <div className="cmp-page__radars">
          <div className="cmp-page__radar">
            <h3 className="page-region-title">{A.detail.player_name}</h3>
            <SkillRadar spokes={A.radar.spokes} baseline={A.radar.baseline} hideLegend />
          </div>
          <div className="cmp-page__radar">
            <h3 className="page-region-title">{B.detail.player_name}</h3>
            <SkillRadar spokes={B.radar.spokes} baseline={B.radar.baseline} hideLegend />
          </div>
        </div>

        {shared && (
          <p className="cmp-page__wowy">
            They've shared {Math.round(shared.toi_together_sec / 60)} minutes at 5v5 this season
            {shared.xgf_pct_together != null ? ` — ${(shared.xgf_pct_together * 100).toFixed(0)}% xGF together` : ''}.
          </p>
        )}
      </PageCard>
    </PageLayout>
  )
}
