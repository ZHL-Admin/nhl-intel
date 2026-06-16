/**
 * Trade / free-agency fit (Phase 5.3, blueprint 6.4): score how well a player fills a team's
 * archetype + component gaps versus the league's top teams.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check } from 'lucide-react'
import { PageLayout, PlayerPicker, PercentileBarList, SkeletonLoader } from '../components/common'
import type { PercentileBarItem } from '../components/common'
import { tradeFit } from '../api/tools'
import { getStyleMap } from '../api/teams'
import { TradeFitResult, PlayerSearchResult, StyleMapTeam } from '../api/types'
import { getTeamName } from '../utils/teams'
import './TradeFit.css'

export default function TradeFit() {
  const [teams, setTeams] = useState<StyleMapTeam[]>([])
  const [teamId, setTeamId] = useState<number | null>(null)
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null)
  const [result, setResult] = useState<TradeFitResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getStyleMap().then((m) => setTeams([...m.teams].sort(
      (a, b) => (a.team_abbrev ?? '').localeCompare(b.team_abbrev ?? '')))).catch(() => {})
  }, [])

  const run = async () => {
    if (!player || !teamId) return
    setLoading(true); setError(null); setResult(null)
    try {
      setResult(await tradeFit(player.player_id, teamId))
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Could not compute fit.')
    } finally {
      setLoading(false)
    }
  }

  const needItems = useMemo<PercentileBarItem[]>(() => {
    if (!result?.need_profile) return []
    return result.need_profile.component_needs.map((n) => ({
      key: n.key, label: n.label,
      // bar fill = gap as a share of the largest gap; inverse so a big gap colours as a deficit
      percentile: clampGap(n.gap, result.need_profile!.component_needs),
      value: n.gap,
      inverse: true,
      formatValue: (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)} goals behind`,
    }))
  }, [result])

  return (
    <PageLayout>
      <div className="tradefit">
        <div className="tradefit__header">
          <Link to="/tools" className="tradefit__back">← Tools</Link>
          <h1 className="tradefit__title">Trade Fit</h1>
          <p className="tradefit__sub">
            How well does a player address a team’s biggest gaps versus the league’s top teams?
          </p>
        </div>

        <div className="tradefit__builder">
          <div className="tradefit__field">
            <label className="tradefit__label">Player</label>
            <PlayerPicker value={player} onSelect={setPlayer} onClear={() => setPlayer(null)} />
          </div>
          <div className="tradefit__field">
            <label className="tradefit__label">Team</label>
            <select className="tradefit__select" value={teamId ?? ''}
                    onChange={(e) => setTeamId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Select a team…</option>
              {teams.map((t) => (
                <option key={t.team_id} value={t.team_id}>
                  {getTeamName(t.team_abbrev ?? '') || t.team_abbrev}
                </option>
              ))}
            </select>
          </div>
          <button className="tradefit__run" disabled={!player || !teamId || loading} onClick={run}>
            {loading ? 'Scoring…' : 'Score fit'}
          </button>
        </div>

        <div className="tradefit__result">
          {loading && <SkeletonLoader />}
          {error && <div className="tradefit__error">{error}</div>}
          {result && !loading && (
            <>
              <div className="tradefit__score-card">
                <div className="tradefit__score">{result.fit_score.toFixed(0)}<span>/100</span></div>
                <div className="tradefit__score-meta">
                  <div className="tradefit__score-label">Fit score</div>
                  {result.player_archetypes.length > 0 && (
                    <div className="tradefit__chips">
                      {result.player_archetypes.slice(0, 3).map((a) => (
                        <span key={a.archetype} className="tradefit__chip">
                          {a.archetype} {(a.weight * 100).toFixed(0)}%
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {result.reasons.length > 0 && (
                <ul className="tradefit__reasons">
                  {result.reasons.map((r, i) => (
                    <li key={i}><Check size={15} className="tradefit__reason-icon" />{r}</li>
                  ))}
                </ul>
              )}

              {needItems.length > 0 && (
                <div className="tradefit__needs">
                  <h3 className="tradefit__needs-title">Team’s biggest gaps vs the top teams</h3>
                  <PercentileBarList items={needItems} />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </PageLayout>
  )
}

function clampGap(gap: number, all: { gap: number }[]): number {
  const max = Math.max(0.0001, ...all.map((n) => Math.abs(n.gap)))
  return Math.max(0, Math.min(1, gap / max))
}
