/**
 * Matchup preview card (Phase 5.3, blueprint 6.4): pregame win probability, power ratings,
 * starter goalie form, fingerprint highlights, deterministic style-clash sentences, season
 * series, and any notable streaks — all from GET /games/{id}/preview. Shown on GameDetail for
 * unplayed games; embeddable elsewhere (Home, Phase 6).
 */
import { useEffect, useState } from 'react'
import ChartPanel from './ChartPanel'
import SkeletonLoader from './SkeletonLoader'
import { getGamePreview } from '../../api/games'
import { MatchupPreview } from '../../api/types'
import { getTeamLogoUrl } from '../../utils/teams'
import './MatchupPreviewCard.css'

export default function MatchupPreviewCard({ gameId }: { gameId: number | string }) {
  const [data, setData] = useState<MatchupPreview | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setData(null); setError(null)
    getGamePreview(gameId)
      .then((d) => active && setData(d))
      .catch((e) => active && setError(e?.response?.status === 400 ? 'unavailable' : 'error'))
    return () => { active = false }
  }, [gameId])

  if (error) return null
  if (!data) return <ChartPanel title="Matchup Preview"><SkeletonLoader /></ChartPanel>

  const homeWp = data.home_pregame_wp ?? null
  const awayWp = homeWp != null ? 1 - homeWp : null

  return (
    <ChartPanel title="Matchup Preview">
      <div className="preview-card">
        {homeWp != null && (
          <div className="preview-card__wp">
            <div className="preview-card__wp-labels">
              <span>{data.away.team_abbrev} {Math.round((awayWp ?? 0) * 100)}%</span>
              <span className="preview-card__wp-title">Pregame win probability</span>
              <span>{data.home.team_abbrev} {Math.round(homeWp * 100)}%</span>
            </div>
            <div className="preview-card__wp-bar">
              <div className="preview-card__wp-away" style={{ width: `${(awayWp ?? 0) * 100}%` }} />
              <div className="preview-card__wp-home" style={{ width: `${homeWp * 100}%` }} />
            </div>
          </div>
        )}

        <div className="preview-card__teams">
          {[data.away, data.home].map((t, i) => (
            <div key={t.team_id} className="preview-card__team">
              <div className="preview-card__team-head">
                <img src={getTeamLogoUrl(t.team_abbrev ?? '')} alt="" className="preview-card__logo"
                     onError={(e) => ((e.target as HTMLImageElement).style.visibility = 'hidden')} />
                <span className="preview-card__team-name">{t.team_abbrev}</span>
                <span className="preview-card__team-side">{i === 0 ? 'Away' : 'Home'}</span>
              </div>
              <dl className="preview-card__stats">
                <div><dt>Power rating</dt><dd>{t.power_rating != null ? `${t.power_rating > 0 ? '+' : ''}${t.power_rating.toFixed(2)}` : '—'}</dd></div>
                <div><dt>Starter (last-10 GSAx)</dt><dd>{t.goalie_name ?? '—'}{t.goalie_last10_gsax != null ? ` (${t.goalie_last10_gsax > 0 ? '+' : ''}${t.goalie_last10_gsax.toFixed(1)})` : ''}</dd></div>
              </dl>
              {t.fingerprint_top.length > 0 && (
                <div className="preview-card__chips">
                  {t.fingerprint_top.map((f) => <span key={f} className="preview-card__chip">{f}</span>)}
                </div>
              )}
            </div>
          ))}
        </div>

        {data.style_clash.length > 0 && (
          <div className="preview-card__section">
            <h4 className="preview-card__section-title">Style clash</h4>
            <ul className="preview-card__list">
              {data.style_clash.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}

        {data.notable_streaks.length > 0 && (
          <div className="preview-card__section">
            <h4 className="preview-card__section-title">Form watch</h4>
            <ul className="preview-card__list">
              {data.notable_streaks.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        )}

        {data.season_series && <div className="preview-card__series">{data.season_series}</div>}
      </div>
    </ChartPanel>
  )
}
