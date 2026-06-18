/**
 * Trade / free-agency fit (Phase 5.3, blueprint 6.4) — visual builder.
 *
 * Pick a player (browse a roster or search) and a destination team, then score how well the
 * player fills that team's archetype + component gaps versus the league's top teams. The result
 * is the hero: a fit score, the player → team visual, the reasons, the team's gap profile, and
 * the teams whose gaps this player best fills.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Check, Info, Plus, ArrowRight, RotateCcw, Share2, Zap, Sparkles } from 'lucide-react'
import { PageLayout, PageHeader, PlayerCard, PlayerExplorer, SkeletonLoader } from '../components/common'
import type { PlayerCardData } from '../components/common'
import { tradeFit, bestTeamFits } from '../api/tools'
import { getStyleMap } from '../api/teams'
import { TradeFitResult, PlayerSearchResult, BestTeamFit, FitDimension } from '../api/types'
import { getTeamName, getTeamLogoUrl, getPlayerHeadshotUrl } from '../utils/teams'
import './TradeFit.css'

interface TeamOpt { team_id: number; abbrev: string; name: string }

/** Letter-grade colour (the combined headline). */
const GRADE_COLOR: Record<string, string> = { A: '#16a34a', B: '#65a30d', C: '#d97706', D: '#ea580c', F: '#dc2626' }
function gradeColor(grade?: string | null): string {
  return GRADE_COLOR[(grade ?? '')[0]] ?? '#64748b'
}
/** Per-dimension colour discipline: positive = green ramp; neutral (incl. LOW NEED) = amber, never
 * red; warn (a genuine stylistic mismatch) = orange. Low need is "not a gap", not a failure. */
function dimColor(tone: string): string {
  if (tone === 'positive') return '#16a34a'
  if (tone === 'warn') return '#ea580c'
  return '#d97706'   // neutral / low-need amber
}

/** Share the current fit — Web Share API on mobile, clipboard link otherwise. */
function ShareButton({ url, name, team, grade }: { url: string; name: string; team: string; grade: string }) {
  const [copied, setCopied] = useState(false)
  const onShare = async () => {
    const text = `${name} grades ${grade} as a fit for the ${team} in NHL Intel’s Trade Fit:`
    if (typeof navigator !== 'undefined' && (navigator as any).share) {
      try { await (navigator as any).share({ title: 'NHL Intel · Trade Fit', text, url }) } catch { /* dismissed */ }
      return
    }
    try { await navigator.clipboard.writeText(`${text} ${url}`); setCopied(true); setTimeout(() => setCopied(false), 2200) } catch { /* blocked */ }
  }
  return (
    <button className={`tf__share${copied ? ' tf__share--copied' : ''}`} onClick={onShare}>
      {copied ? <><Check size={15} /> Link copied</> : <><Share2 size={15} /> Share</>}
    </button>
  )
}

function TeamGrid({ teams, activeId, onPick }: {
  teams: TeamOpt[]; activeId?: number | null; onPick: (t: TeamOpt) => void
}) {
  return (
    <section className="tf-picker">
      <h3 className="tf-picker__head">Choose the destination team</h3>
      {teams.length === 0 ? <SkeletonLoader /> : (
        <div className="tf-teamgrid">
          {teams.map((t) => (
            <button key={t.team_id} title={t.name}
              className={`tf-teamcard${activeId === t.team_id ? ' tf-teamcard--active' : ''}`}
              onClick={() => onPick(t)}>
              <img src={getTeamLogoUrl(t.abbrev)} alt="" draggable={false}
                onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
              <span className="tf-teamcard__name">{t.name}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

export default function TradeFit() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [teams, setTeams] = useState<TeamOpt[]>([])
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null)
  const [team, setTeam] = useState<TeamOpt | null>(null)
  const [mode, setMode] = useState<'player' | 'team'>('player')
  const [result, setResult] = useState<TradeFitResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // teams + share-link reconstruction
  useEffect(() => {
    let on = true
    getStyleMap().then((m) => {
      if (!on) return
      const opts = m.teams
        .filter((t) => t.team_abbrev)
        .map((t) => ({ team_id: t.team_id, abbrev: t.team_abbrev as string, name: getTeamName(t.team_abbrev as string) }))
        .sort((a, b) => a.name.localeCompare(b.name))
      setTeams(opts)

      const pl = searchParams.get('player')
      const tm = searchParams.get('team')
      if (pl && tm) {
        const [pid, abbrev] = pl.split('.')
        const teamId = parseInt(tm, 10)
        const t = opts.find((o) => o.team_id === teamId) ?? null
        setTeam(t)
        setLoading(true)
        tradeFit(parseInt(pid, 10), teamId)
          .then((res) => {
            if (!on) return
            setResult(res)
            setPlayer({
              player_id: parseInt(pid, 10), name: res.player_name, team_id: null,
              team_abbrev: abbrev || null, position: null, archetype: null,
              headshot_url: abbrev ? getPlayerHeadshotUrl(parseInt(pid, 10), abbrev) : null,
            })
          })
          .catch(() => on && setError('Could not load that shared fit.'))
          .finally(() => on && setLoading(false))
      }
    }).catch(() => {})
    return () => { on = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const runFit = async (pl: PlayerSearchResult, tm: TeamOpt) => {
    setLoading(true); setError(null); setResult(null)
    try {
      const res = await tradeFit(pl.player_id, tm.team_id)
      setResult(res)
      setSearchParams({ player: `${pl.player_id}.${pl.team_abbrev ?? ''}`, team: String(tm.team_id) }, { replace: true })
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Could not compute fit.')
    } finally {
      setLoading(false)
    }
  }

  const run = () => { if (player && team) runFit(player, team) }
  const pickPlayer = (p: PlayerSearchResult) => { setPlayer(p); if (!team) setMode('team') }
  const pickTeam = (t: TeamOpt) => { setTeam(t); if (!player) setMode('player') }
  const switchTeam = (t: TeamOpt) => { if (player) { setTeam(t); runFit(player, t) } }

  const showResult = !!result && !loading
  const shareUrl = player && team
    ? `${window.location.origin}/tools/trade-fit?player=${player.player_id}.${player.team_abbrev ?? ''}&team=${team.team_id}`
    : ''

  return (
    <PageLayout>
      <div className="tf">
        <PageHeader
          back={{ to: '/tools', label: 'Tools' }}
          title="Trade Fit"
          subtitle="How well does a player address a team’s biggest gaps versus the league’s top teams?"
        />

        {showResult ? (
          <div className="tf__result">
            <div className="tf__result-bar">
              <button className="tf__again" onClick={() => { setResult(null); setError(null) }}>
                <RotateCcw size={15} /> Score another
              </button>
              {shareUrl && (
                <ShareButton url={shareUrl} name={result!.player_name ?? 'This player'}
                  team={team?.name ?? ''} grade={result!.overall_grade} />
              )}
            </div>
            <Hero result={result!} player={player} team={team} />
            {player && (
              <BestTeamFits playerId={player.player_id} excludeTeamId={team?.team_id ?? null}
                teams={teams} onPick={switchTeam} />
            )}
          </div>
        ) : loading ? (
          <div className="tf__result"><SkeletonLoader /></div>
        ) : (
          <>
            <div className="tf-build">
              <div className="tf-build__slots">
                <div className={`tf-slot${mode === 'player' ? ' tf-slot--armed' : ''}`} onClick={() => setMode('player')}>
                  <span className="tf-slot__label">Player</span>
                  {player ? (
                    <PlayerCard player={player as PlayerCardData} size="lg" onRemove={() => setPlayer(null)} />
                  ) : (
                    <button className="tf-slot__empty" onClick={(e) => { e.stopPropagation(); setMode('player') }}>
                      <span className="tf-slot__plus"><Plus size={20} /></span>
                      <span>Add a player</span>
                    </button>
                  )}
                </div>

                <ArrowRight className="tf-build__arrow" size={22} />

                <div className={`tf-slot${mode === 'team' ? ' tf-slot--armed' : ''}`} onClick={() => setMode('team')}>
                  <span className="tf-slot__label">Destination</span>
                  {team ? (
                    <div className="tf-slot__team">
                      <img src={getTeamLogoUrl(team.abbrev)} alt=""
                        onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
                      <span className="tf-slot__team-name">{team.name}</span>
                      <button className="tf-slot__team-clear" onClick={(e) => { e.stopPropagation(); setTeam(null) }} aria-label="Clear team">✕</button>
                    </div>
                  ) : (
                    <button className="tf-slot__empty" onClick={(e) => { e.stopPropagation(); setMode('team') }}>
                      <span className="tf-slot__plus"><Plus size={20} /></span>
                      <span>Choose a team</span>
                    </button>
                  )}
                </div>
              </div>

              {error && <div className="tf__error">{error}</div>}

              <button className="tf-run" disabled={!player || !team || loading} onClick={run}>
                <Zap size={16} />
                {loading ? 'Scoring…' : !player ? 'Add a player' : !team ? 'Choose a team' : 'Score fit'}
              </button>
            </div>

            {mode === 'team'
              ? <TeamGrid teams={teams} activeId={team?.team_id} onPick={pickTeam} />
              : <PlayerExplorer onPick={pickPlayer} takenIds={player ? new Set([player.player_id]) : undefined} />}
          </>
        )}
      </div>
    </PageLayout>
  )
}

/** One fit dimension row: label | bar (level) over a tangible-driver note | right-aligned value. */
function DimensionRow({ d }: { d: FitDimension }) {
  const color = dimColor(d.tone)
  const pct = d.level == null ? 0 : Math.max(0, Math.min(1, d.level)) * 100
  // model-estimate softness: a faint band around the marker (line fit, quality)
  const band = d.uncertain && d.sd ? Math.min(20, d.sd * 100) : 0
  return (
    <div className={`tf-dim tf-dim--${d.tone}`}>
      <div className="tf-dim__head">
        <span className="tf-dim__label">{d.label}{d.uncertain && <span className="tf-dim__est" title="Model estimate — read as a tier, not a precise number">~</span>}</span>
        <span className="tf-dim__val" style={{ color }}>{d.value}</span>
      </div>
      <div className="tf-dim__bar" aria-hidden="true">
        {d.level != null && band > 0 && (
          <span className="tf-dim__band" style={{ left: `${Math.max(0, pct - band)}%`, width: `${Math.min(100, pct + band) - Math.max(0, pct - band)}%`, background: color }} />
        )}
        {d.level != null && <span className="tf-dim__fill" style={{ width: `${pct}%`, background: color }} />}
      </div>
      <p className="tf-dim__note">{d.note}</p>
    </div>
  )
}

function Hero({ result, player, team }: {
  result: TradeFitResult
  player: PlayerSearchResult | null
  team: TeamOpt | null
}) {
  const color = gradeColor(result.overall_grade)
  const name = result.player_name ?? player?.name ?? 'This player'
  const faceSrc = player?.headshot_url
    || (player?.team_abbrev ? getPlayerHeadshotUrl(player.player_id, player.team_abbrev) : '')

  return (
    <div className="tf-hero" style={{ ['--tf-grade' as string]: color } as React.CSSProperties}>
      {/* player -> team inputs */}
      <div className="tf-hero__io">
        {faceSrc
          ? <img className="tf-hero__face" src={faceSrc} alt="" onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
          : <span className="tf-hero__face tf-hero__face--blank" />}
        <span className="tf-hero__io-name">{name}</span>
        <ArrowRight size={18} className="tf-hero__viz-arrow" />
        {team && <img className="tf-hero__logo" src={getTeamLogoUrl(team.abbrev)} alt="" onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />}
        <span className="tf-hero__io-name">{team?.name ?? ''}</span>
      </div>

      {/* HEADLINE CARD: grade (left) + deterministic verdict (right) */}
      <div className="tf-headline">
        <div className="tf-headline__grade">
          <span className="tf-headline__letter">{result.overall_grade}</span>
          <span className="tf-headline__label">overall fit</span>
        </div>
        <p className="tf-headline__verdict">{result.verdict_sentence}</p>
      </div>

      {/* BREAKDOWN: the five dimensions (the grade NEVER appears without these) */}
      <div className="tf-dims">
        {result.dimensions.map((d) => <DimensionRow key={d.key} d={d} />)}
      </div>

      <div className="tf-hero__limit">
        <Info size={14} />
        <span>
          Each dimension is measured separately; the grade is a weighted blend gated by positional
          relevance. Low need means “not a statistical gap”, not a bad fit. The model can’t see
          injuries, departures, cap, or locker room — weigh those yourself.
        </span>
      </div>
    </div>
  )
}

/** Teams whose gaps this player best fills — click one to re-score for that destination. */
function BestTeamFits({ playerId, excludeTeamId, teams, onPick }: {
  playerId: number
  excludeTeamId: number | null
  teams: TeamOpt[]
  onPick: (t: TeamOpt) => void
}) {
  const [data, setData] = useState<BestTeamFit[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let on = true
    setLoading(true); setError(null); setData(null)
    bestTeamFits(playerId, excludeTeamId ?? undefined)
      .then((d) => on && setData(d))
      .catch(() => on && setError('Could not load team fits.'))
      .finally(() => on && setLoading(false))
    return () => { on = false }
  }, [playerId, excludeTeamId])

  const byId = (id: number) => teams.find((t) => t.team_id === id)

  return (
    <div className="tf-best">
      <div className="tf-best__head">
        <span className="tf-best__icon"><Sparkles size={16} /></span>
        <div>
          <h3 className="tf-best__title">Best team fits</h3>
          <p className="tf-best__sub">
            Teams whose biggest gaps this player’s skills fill best. Click a team to re-score the fit there.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="tf-best__loading"><SkeletonLoader /><span>Ranking teams…</span></div>
      ) : error ? (
        <p className="tf-best__msg">{error}</p>
      ) : data && data.length > 0 ? (
        <div className="tf-best__grid">
          {data.map((d) => {
            const t = byId(d.team_id)
            if (!t) return null
            return (
              <button key={d.team_id} className="tf-bestcard" onClick={() => onPick(t)}>
                <span className="tf-bestcard__score" style={{ color: gradeColor(d.grade) }}>
                  {d.grade ?? '—'}<small>{d.fit_score.toFixed(0)}</small>
                </span>
                <img className="tf-bestcard__logo" src={getTeamLogoUrl(t.abbrev)} alt=""
                  onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
                <span className="tf-bestcard__name">{t.name}</span>
                {d.reason && <span className="tf-bestcard__reason">{d.reason}</span>}
              </button>
            )
          })}
        </div>
      ) : (
        <p className="tf-best__msg">No clearly stronger fit elsewhere.</p>
      )}
    </div>
  )
}
