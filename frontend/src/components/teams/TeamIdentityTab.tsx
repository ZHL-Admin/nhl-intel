/**
 * Team identity fingerprint tab (Phase 3.2): grouped percentile bars + a territory-to-danger
 * conversion panel whose plain-English diagnosis is rendered entirely from API ranks.
 */
import { useState, useEffect } from 'react'
import { ChartPanel, PercentileBarList, Tabs, SkeletonLoader } from '../common'
import type { PercentileBarItem } from '../common'
import { getTeamIdentity } from '../../api/teams'
import { TeamIdentity, TeamIdentityWindow } from '../../api/types'
import { FINGERPRINT_GROUPS } from '../../config/metrics'
import './TeamIdentityTab.css'

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

/** Rank from the top (1 = best) given an ascending percentile and league size. */
function rankFromTop(pctile: number | null | undefined, size: number): number | null {
  if (pctile == null) return null
  return Math.round((1 - pctile) * (size - 1)) + 1
}

function metricMap(win: TeamIdentityWindow): Record<string, { value?: number | null; percentile?: number | null }> {
  const m: Record<string, { value?: number | null; percentile?: number | null }> = {}
  for (const x of win.metrics) m[x.key] = { value: x.value, percentile: x.percentile }
  return m
}

function ConversionPanel({ win, size }: { win: TeamIdentityWindow; size: number }) {
  const m = metricMap(win)
  const ozRank = rankFromTop(m.oz_time_pct?.percentile, size)
  const convRank = rankFromTop(m.oz_conversion?.percentile, size)
  if (ozRank == null || convRank == null) {
    return <p className="identity__conv-note">Edge zone-time not available for this season.</p>
  }
  const gap = convRank - ozRank // positive => converts worse than territory rank
  let diagnosis: string
  if (gap >= 8) {
    diagnosis = `Controls territory (${ordinal(ozRank)} in offensive-zone time) but struggles to turn it into danger (${ordinal(convRank)} in expected goals per o-zone minute) — a volume-over-quality structure.`
  } else if (gap <= -8) {
    diagnosis = `Generates danger efficiently (${ordinal(convRank)} in expected goals per o-zone minute) despite only ${ordinal(ozRank)} in offensive-zone time — quality over territory.`
  } else {
    diagnosis = `Offensive-zone time (${ordinal(ozRank)}) and danger conversion (${ordinal(convRank)}) are roughly aligned.`
  }
  return (
    <div className="identity__conv">
      <div className="identity__conv-stats">
        <div className="identity__conv-stat">
          <span className="identity__conv-rank">{ordinal(ozRank)}</span>
          <span className="identity__conv-cap">O-zone time</span>
        </div>
        <div className="identity__conv-stat">
          <span className="identity__conv-rank">{ordinal(convRank)}</span>
          <span className="identity__conv-cap">xG per o-zone minute</span>
        </div>
      </div>
      <p className="identity__conv-diagnosis">{diagnosis}</p>
    </div>
  )
}

export default function TeamIdentityTab({ teamId }: { teamId: number }) {
  const [identity, setIdentity] = useState<TeamIdentity | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [windowKind, setWindowKind] = useState<'season' | 'last25'>('season')

  useEffect(() => {
    let active = true
    setIdentity(null)
    setError(null)
    getTeamIdentity(teamId)
      .then((d) => active && setIdentity(d))
      .catch(() => active && setError('Could not load team identity.'))
    return () => { active = false }
  }, [teamId])

  if (error) return <p className="identity__error">{error}</p>
  if (!identity) return <SkeletonLoader />

  const win = identity.windows.find((w) => w.window === windowKind) ?? identity.windows[0]

  return (
    <div className="identity">
      <div className="identity__head">
        <Tabs
          options={[
            { value: 'season', label: 'Full season' },
            { value: 'last25', label: 'Last 25' },
          ]}
          value={windowKind}
          onChange={(v) => setWindowKind(v as 'season' | 'last25')}
        />
        <span className="identity__games">{win.games} games</span>
      </div>

      <ChartPanel title="Territory-to-danger conversion" subtitle="Where this team's offense comes from structurally">
        <ConversionPanel win={win} size={identity.league_size} />
      </ChartPanel>

      <div className="identity__groups">
        {FINGERPRINT_GROUPS.map((group) => {
          const m = metricMap(win)
          const items: PercentileBarItem[] = group.metrics.map((gm) => ({
            key: gm.key,
            label: gm.label,
            percentile: m[gm.key]?.percentile,
            value: m[gm.key]?.value,
            inverse: gm.inverse,
            formatValue: (v) => (Math.abs(v) < 1 ? v.toFixed(3) : v.toFixed(2)),
          }))
          return (
            <ChartPanel key={group.title} title={group.title}>
              <PercentileBarList items={items} />
            </ChartPanel>
          )
        })}
      </div>
      <p className="identity__foot">
        Percentiles are league rank within the {identity.season} season ({identity.league_size} teams).
        Bars green = top third, red = bottom third; for “allowed”/penalty rows the colour is flipped.
      </p>
    </div>
  )
}
