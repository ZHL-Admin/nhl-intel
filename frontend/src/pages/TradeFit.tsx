/**
 * Player Fit (Phase 5.3, blueprint 6.4) — visual builder.
 *
 * Pick a player (browse a roster or search) and a destination team, then score how well the
 * player fills that team's archetype + component gaps versus the league's top teams. The result
 * is the hero: a fit score, the player → team visual, the reasons, the team's gap profile, and
 * the teams whose gaps this player best fills.
 */
import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { Check, Info, ArrowRight, RotateCcw, Share2, Zap, Sparkles, Search, X } from 'lucide-react'
import { PageLayout, PageCard, SkeletonLoader, Tooltip } from '../components/common'
import { tradeFit, bestTeamFits, searchPlayers } from '../api/tools'
import { getPlayerPreview, getOverallLeaders } from '../api/players'
import { getStyleMap } from '../api/teams'
import { TradeFitResult, PlayerSearchResult, BestTeamFit, FitDimension, FitComponentNeed, PlayerPreview, ArchetypeRankRow } from '../api/types'
import { getTeamName, getTeamLogoUrl, getPlayerHeadshotUrl, getTeamColor } from '../utils/teams'
import { ordinal, fmtWar } from '../utils/format'
import './TradeFit.css'

// match-dimension weights, mirroring config.MATCH_WEIGHTS (need .55 / style .20 / line .25); quality
// is NOT a weighted term — it's the floor, shown with a "floor" tag rather than a weight chip.
const DIM_WEIGHT: Record<string, number> = { need: 55, style: 20, line: 25 }
// the single canonical fit-vs-quality explanation (lives in the quality chip's tooltip, not the footer)
const FIT_VS_QUALITY =
  'Fit and quality are two different things. Quality is how good the player is — it sets a FLOOR ' +
  'under fit (a strong player keeps a respectable fit even at a stylistic mismatch) but never a ' +
  'ceiling. Fit is the match: how his strengths land on this team’s thin spots (by role), whether ' +
  'his style suits their system, and how he complements the unit he’d join. A low-value player who ' +
  'lands on a real need can still fit well.'

interface TeamOpt { team_id: number; abbrev: string; name: string }

/** Letter-grade colour (the combined headline). */
const GRADE_COLOR: Record<string, string> = { A: '#16a34a', B: '#65a30d', C: '#d97706', D: '#ea580c', F: '#dc2626' }
function gradeColor(grade?: string | null): string {
  return GRADE_COLOR[(grade ?? '')[0]] ?? '#64748b'
}
/**
 * Dimension bar/value colour by LEVEL (strength), so a weak dimension visibly reads as the soft
 * spot at a glance — not all green. Thresholds live HERE (one place):
 *   strong   >= 0.60  -> green
 *   middling 0.40-0.60 -> amber
 *   weak     <  0.40  -> muted burnt-red (a "soft spot" tone, not alarm-red)
 * NEED is excluded from this scale: it keeps its tone colour (low need = amber "not a gap", never a
 * penalty), per the asymmetric-need model — so a low-need bar must not look like a weakness.
 */
const LEVEL_STRONG = 0.60
const LEVEL_MIDDLING = 0.42
// Calm, semantic ramp: green = a real strength, neutral slate = moderate (NOT a warning — most fits
// are moderate and shouldn't read as orange alarms), amber = the genuine soft spot. One accent colour
// at a time keeps the card from looking like a wall of orange.
function levelColor(level?: number | null): string {
  if (level == null) return '#94a3b8'            // n/a — slate
  if (level >= LEVEL_STRONG) return '#16a34a'    // strong — green
  if (level >= LEVEL_MIDDLING) return '#64748b'  // moderate — neutral slate
  return '#d97706'                               // weak — amber (the soft spot)
}

/** Share the current fit — Web Share API on mobile, clipboard link otherwise. */
function ShareButton({ url, name, team, grade }: { url: string; name: string; team: string; grade: string }) {
  const [copied, setCopied] = useState(false)
  const onShare = async () => {
    const text = `${name} grades ${grade} as a fit for the ${team} in NHL Intel’s Player Fit:`
    if (typeof navigator !== 'undefined' && (navigator as any).share) {
      try { await (navigator as any).share({ title: 'NHL Intel · Player Fit', text, url }) } catch { /* dismissed */ }
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

/** A browse/search row: avatar + name + position·team (mono) + archetype label. */
function PlayerRow({ p, onPick, selected }: {
  p: PlayerSearchResult; onPick: (p: PlayerSearchResult) => void; selected?: boolean
}) {
  const face = p.headshot_url || (p.team_abbrev ? getPlayerHeadshotUrl(p.player_id, p.team_abbrev) : '')
  return (
    <button className={`tf-prow${selected ? ' tf-prow--selected' : ''}`} onClick={() => onPick(p)}>
      {face
        ? <img className="tf-prow__face" src={face} alt="" onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
        : <span className="tf-prow__face tf-prow__face--blank" />}
      <span className="tf-prow__name">{p.name}</span>
      <span className="tf-prow__meta">{p.position ?? ''}{p.team_abbrev ? ` · ${p.team_abbrev}` : ''}</span>
      {p.archetype && <span className="tf-prow__arch">{p.archetype}</span>}
    </button>
  )
}

/**
 * Player-active picker: league search + a short "recent & notable" list. Each row shows the
 * player's archetype label straight from the search / leaders payload — the same v2 archetype
 * source getPlayerLabels derives from, so there's no drift and no per-row fetch (no N+1).
 */
function PlayerPickerPanel({ onPick, selectedId }: {
  onPick: (p: PlayerSearchResult) => void; selectedId: number | null
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PlayerSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [notable, setNotable] = useState<PlayerSearchResult[] | null>(null)

  // "recent & notable" = the league's top players by Overall (the leaders payload carries the
  // archetype + team, so we render rows without an extra call per player).
  useEffect(() => {
    let on = true
    getOverallLeaders('ALL', undefined, 12)
      .then((rows: ArchetypeRankRow[]) => {
        if (!on) return
        setNotable(rows.filter((r) => r.position !== 'G').map((r) => ({
          player_id: r.player_id, name: r.player_name ?? '', team_id: null,
          team_abbrev: r.team_abbrev ?? null, position: r.position ?? null,
          headshot_url: r.team_abbrev ? getPlayerHeadshotUrl(r.player_id, r.team_abbrev) : null,
          archetype: r.primary_archetype ?? null,
        })))
      })
      .catch(() => on && setNotable([]))
    return () => { on = false }
  }, [])

  // debounced league-wide search
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) { setResults([]); setSearching(false); return }
    let on = true
    setSearching(true)
    const t = setTimeout(async () => {
      try { const data = await searchPlayers(q, 24); if (on) setResults(data.filter((p) => p.position !== 'G')) }
      catch { if (on) setResults([]) }
      finally { if (on) setSearching(false) }
    }, 220)
    return () => { on = false; clearTimeout(t) }
  }, [query])

  const searchMode = query.trim().length >= 2
  const list = searchMode ? results : (notable ?? [])

  return (
    <section className="tf-pick">
      <div className="tf-pick__search">
        <Search size={16} className="tf-pick__search-icon" />
        <input className="tf-pick__input" placeholder="Search any player in the league…"
          value={query} onChange={(e) => setQuery(e.target.value)} autoFocus />
        {query && (
          <button className="tf-pick__clear" onClick={() => setQuery('')} aria-label="Clear search"><X size={15} /></button>
        )}
      </div>
      <h4 className="tf-pick__head">{searchMode ? 'Search results' : 'Recent & notable'}</h4>
      {(searchMode ? (searching && results.length === 0) : notable === null) ? (
        <SkeletonLoader />
      ) : list.length === 0 ? (
        <p className="tf-pick__empty">{searchMode ? `No players match “${query.trim()}”.` : 'No players to show.'}</p>
      ) : (
        <div className="tf-pick__list">
          {list.map((p) => <PlayerRow key={p.player_id} p={p} onPick={onPick} selected={p.player_id === selectedId} />)}
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
        <PageCard
          title="Player Fit"
          subtitle="How well does a player fit into a specific team?"
          bodyClassName="tf__body"
        >
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
              <>
                <div className="page-divider" />
                <BestTeamFits playerId={player.player_id} excludeTeamId={team?.team_id ?? null}
                  teams={teams} onPick={switchTeam} />
              </>
            )}
          </div>
        ) : loading ? (
          <div className="tf__result"><SkeletonLoader /></div>
        ) : (
          <>
            <div className="tf-build">
              <div className="tf-build__slots">
                {/* Player card — a stateful toggle; active one drives the picker below */}
                <button type="button" aria-pressed={mode === 'player'}
                  className={`tf-card${mode === 'player' ? ' tf-card--active' : ''}`}
                  onClick={() => setMode('player')}>
                  <span className="tf-card__head">
                    <span className="tf-card__label">Player</span>
                    {mode === 'player' && <span className="tf-card__tag">Selecting</span>}
                  </span>
                  {player ? (
                    <span className="tf-card__chip">
                      {(player.headshot_url || player.team_abbrev)
                        ? <img className="tf-card__face" alt=""
                            src={player.headshot_url || getPlayerHeadshotUrl(player.player_id, player.team_abbrev || '')}
                            onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
                        : <span className="tf-card__face tf-card__face--blank" />}
                      <span className="tf-card__chip-meta">
                        <span className="tf-card__chip-name">{player.name}</span>
                        <span className="tf-card__chip-sub">{player.position ?? ''}{player.team_abbrev ? ` · ${player.team_abbrev}` : ''}</span>
                      </span>
                      <span className="tf-card__clear" role="button" tabIndex={0} aria-label="Clear player"
                        onClick={(e) => { e.stopPropagation(); setPlayer(null); setMode('player') }}><X size={14} /></span>
                    </span>
                  ) : (
                    <span className="tf-card__placeholder">Search for a player</span>
                  )}
                </button>

                <ArrowRight className="tf-build__arrow" size={22} />

                {/* Destination card — toggle to the team grid */}
                <button type="button" aria-pressed={mode === 'team'}
                  className={`tf-card${mode === 'team' ? ' tf-card--active' : ''}`}
                  onClick={() => setMode('team')}>
                  <span className="tf-card__head">
                    <span className="tf-card__label">Destination</span>
                    {mode === 'team' && <span className="tf-card__tag">Selecting</span>}
                  </span>
                  {team ? (
                    <span className="tf-card__chip">
                      <img className="tf-card__logo" src={getTeamLogoUrl(team.abbrev)} alt=""
                        onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
                      <span className="tf-card__chip-meta">
                        <span className="tf-card__chip-name">{team.name}</span>
                        <span className="tf-card__chip-sub">{team.abbrev}</span>
                      </span>
                      <span className="tf-card__clear" role="button" tabIndex={0} aria-label="Clear team"
                        onClick={(e) => { e.stopPropagation(); setTeam(null); setMode('team') }}><X size={14} /></span>
                    </span>
                  ) : (
                    <span className="tf-card__placeholder">Choose a destination team</span>
                  )}
                </button>
              </div>

              {error && <div className="tf__error">{error}</div>}

              <button className="tf-run" disabled={!player || !team || loading} onClick={run}>
                <Zap size={16} />
                {loading ? 'Scoring…' : 'Score the fit'}
              </button>
              {!(player && team) && (
                <p className="tf-build__hint">
                  {!player && !team ? 'Add a player and a destination to score'
                    : !player ? 'Add a player to score'
                      : 'Choose a destination to score'}
                </p>
              )}
            </div>

            <div className="page-divider" />

            {/* ONE contextual picker, driven by the active card */}
            {mode === 'team'
              ? <TeamGrid teams={teams} activeId={team?.team_id} onPick={pickTeam} />
              : <PlayerPickerPanel onPick={pickPlayer} selectedId={player?.player_id ?? null} />}
          </>
        )}
        </PageCard>
      </div>
    </PageLayout>
  )
}

/** "Where he fits the roster": team-need vs his-strength per role (already sorted by need desc),
 * with a fills/gap/covered/low-need tag per row and a one-line takeaway. De-carded (on background). */
const TAG_LABEL: Record<FitComponentNeed['tag'], string> =
  { fills: 'fills', gap: 'gap', covered: 'covered', low_need: 'low need' }
const TAG_TONE: Record<FitComponentNeed['tag'], string> =
  { fills: 'pos', gap: 'warn', covered: 'neutral', low_need: 'muted' }

function NeedSection({ rows, summary, teamColor }: { rows: FitComponentNeed[]; summary: string; teamColor?: string }) {
  return (
    <div className="tf-need">
      <div className="tf-need__legend">
        <span><i className="tf-need__dot tf-need__dot--need" style={{ backgroundColor: teamColor }} /> team need</span>
        <span><i className="tf-need__dot tf-need__dot--str" /> his strength</span>
      </div>
      {rows.map((r) => (
        <div key={r.component} className="tf-need__row">
          <span className="tf-need__label">{r.label}</span>
          <span className="tf-need__bars">
            <span className="tf-need__bar" title={`Team need ${Math.round(r.team_need * 100)}`}>
              <span className="tf-need__fill tf-need__fill--need" style={{ width: `${r.team_need * 100}%`, backgroundColor: teamColor }} />
            </span>
            <span className="tf-need__bar" title={`His strength ${Math.round(r.player_strength * 100)} (within role)`}>
              <span className="tf-need__fill tf-need__fill--str" style={{ width: `${r.player_strength * 100}%` }} />
            </span>
          </span>
          <span className={`tf-need__tag tf-need__tag--${TAG_TONE[r.tag]}`}>{TAG_LABEL[r.tag]}</span>
        </div>
      ))}
      {summary && <p className="tf-need__takeaway">{summary}</p>}
    </div>
  )
}

/** One decomposition row: label (+ weight or a 'floor' tag) | level word | bar | driver note. Coloured
 * by LEVEL (green strong / slate moderate / amber soft spot — never red). Estimates (Line, Quality)
 * carry the EST tag + a translucent ±SE band. The NEED breakdown lives in its own section, not here. */
function DimensionRow({ d, weight, gateTag }: { d: FitDimension; weight?: number; gateTag?: string }) {
  const color = levelColor(d.level)
  const pct = d.level == null ? 0 : Math.max(0, Math.min(1, d.level)) * 100
  const band = d.uncertain && d.sd ? Math.min(20, d.sd * 100) : 0
  return (
    <div className={`tf-dim tf-dim--${d.tone}`}>
      <div className="tf-dim__head">
        <span className="tf-dim__label">
          {d.label}
          {weight != null && <span className="tf-dim__weight" title="weight in the fit blend">{weight}%</span>}
          {gateTag && <span className="tf-dim__weight tf-dim__weight--floor"
            title="Quality isn't averaged in — it sets a floor under fit">{gateTag}</span>}
          {d.uncertain && (
            <span className="tf-dim__est" title="Model estimate — read this as a tier, not a precise number">est.</span>
          )}
        </span>
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
  const teamColor = team ? getTeamColor(team.abbrev) : undefined;
  const faceSrc = player?.headshot_url
    || (player?.team_abbrev ? getPlayerHeadshotUrl(player.player_id, player.team_abbrev) : '')

  // Tangible player facts we actually have from the API (age / position / handedness / current
  // team). No contract or cap — the NHL API doesn't provide it, so we don't fabricate it.
  const [preview, setPreview] = useState<PlayerPreview | null>(null)
  useEffect(() => {
    if (!player) return
    let on = true
    getPlayerPreview(player.player_id).then((p) => on && setPreview(p)).catch(() => {})
    return () => { on = false }
  }, [player?.player_id])
  const factParts = [
    player?.position ?? preview?.pos_group ?? null,
    preview?.shoots ? `Shoots ${preview.shoots}` : null,
    preview?.age ? `Age ${preview.age}` : null,
    player?.team_abbrev ? getTeamName(player.team_abbrev) : null,
  ].filter(Boolean) as string[]
  const primaryArch = player?.archetype ?? result.player_archetypes?.[0]?.archetype ?? null

  // Quality is the FLOOR, not a co-equal hero: a chip on the verdict line + one decomposition row.
  const q = result.quality
  const qualityRow: FitDimension = {
    key: 'quality', label: 'Quality', level: q.percentile ?? null,
    value: q.label || '—', note: q.note, tone: 'positive', uncertain: true,
    sd: q.war_sd != null ? Math.min(0.18, q.war_sd / 15) : null,
  }

  return (
    <div className="tf-hero" style={{ ['--tf-grade' as string]: color } as React.CSSProperties}>
      {/* player -> team inputs (each links to its profile) */}
      <div className="tf-hero__io">
        <Link className="tf-hero__io-link" to={`/players/${result.player_id}`}>
          {faceSrc
            ? <img className="tf-hero__face" src={faceSrc} alt="" onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
            : <span className="tf-hero__face tf-hero__face--blank" />}
          <span className="tf-hero__io-name">{name}</span>
        </Link>
        <ArrowRight size={18} className="tf-hero__viz-arrow" />
        <Link className="tf-hero__io-link" to={`/teams/${result.team_id}`}>
          {team && <img className="tf-hero__logo" src={getTeamLogoUrl(team.abbrev)} alt="" onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />}
          <span className="tf-hero__io-name">{team?.name ?? ''}</span>
        </Link>
      </div>

      {/* tangible player facts + archetype chip (what the API gives us; no cap/contract) */}
      {(factParts.length > 0 || primaryArch) && (
        <div className="tf-hero__facts">
          <span>{factParts.join(' · ')}</span>
          {primaryArch && <span className="tf-prow__arch tf-hero__arch">{primaryArch}</span>}
        </div>
      )}

      {/* ONE HERO ANSWER: the grade card + the verdict at lead size + quality as a subordinate chip */}
      <div className="tf-answer">
        <div className="tf-answer__grade">
          <span className="tf-answer__letter">{result.overall_grade}</span>
          <span className="tf-answer__score">{result.overall_score.toFixed(0)} / 100</span>
          <span className="tf-answer__label">Fit with {team?.name ?? 'the team'}</span>
        </div>
        <div className="tf-answer__read">
          <p className="tf-answer__verdict">{result.verdict_sentence}</p>
          <span className="tf-qchip">
            <span className="tf-qchip__k">Quality</span>
            <span className="tf-qchip__v">
              {q.percentile != null ? ordinal(q.percentile * 100) : '—'} · {q.label}
              {q.war != null && <> · {fmtWar(q.war)}{q.war_sd ? ` ± ${q.war_sd.toFixed(1)}` : ''} WAR</>}
            </span>
            <span className="tf-qchip__floor">high floor on fit</span>
            <Tooltip content={FIT_VS_QUALITY}>
              <span className="tf-qchip__info" tabIndex={0} aria-label="How fit and quality differ"><Info size={13} /></span>
            </Tooltip>
          </span>
        </div>
      </div>

      {/* WHY IT GRADES — one decomposition of all the dimensions (quality as a floor row, not a hero) */}
      <h3 className="tf-sec">Why it grades {result.overall_grade}</h3>
      <div className="tf-dims">
        {result.dimensions.map((d) => <DimensionRow key={d.key} d={d} weight={DIM_WEIGHT[d.key]} />)}
        <DimensionRow d={qualityRow} gateTag="floor" />
      </div>

      {/* WHERE HE FITS THE ROSTER — the need decomposition, sorted by need, tagged, with a takeaway */}
      {result.need_breakdown && result.need_breakdown.length > 0 && (
        <>
          <h3 className="tf-sec">Where he fits the roster</h3>
          <NeedSection 
            rows={result.need_breakdown} 
            summary={result.need_summary} 
            teamColor={teamColor} 
          />
        </>
      )}

      <p className="tf-caveat">
        Fit and quality are separate, and the model can’t see injuries, departures, cap, or locker
        room — weigh those yourself.
      </p>
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

  // Honesty: these are ranked by OVERALL fit grade. For a fixed player talent is constant, so the
  // ordering comes from team need + style. When no destination clears a B, don't imply a meaningful
  // ranking — say plainly that his best fits are all middling.
  const noStrongFit = !!data && data.length > 0 && !data.some((d) => 'AB'.includes((d.grade ?? '')[0]))

  return (
    <div className="tf-best">
      <div className="tf-best__head">
        <span className="tf-best__icon"><Sparkles size={16} /></span>
        <div>
          <h3 className="tf-best__title">Strong fits</h3>
          <p className="tf-best__sub">
            Ranked by overall fit grade. Talent is the same everywhere, so the differences come from
            each team’s need and style. Click a team to re-score the fit there.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="tf-best__loading"><SkeletonLoader /><span>Ranking teams…</span></div>
      ) : error ? (
        <p className="tf-best__msg">{error}</p>
      ) : data && data.length > 0 ? (
        <>
          {noStrongFit && (
            <p className="tf-best__note">
              His best fits are all middling — a below-average player doesn’t strongly fit anywhere.
            </p>
          )}
          <div className="tf-best__grid">
            {data.map((d) => {
              const t = byId(d.team_id)
              if (!t) return null
              return (
                <button key={d.team_id} className="tf-bestcard" onClick={() => onPick(t)}>
                  <span className="tf-bestcard__grade" style={{ color: gradeColor(d.grade) }}
                    title="Overall fit grade if traded here">
                    {d.grade ?? '—'}
                  </span>
                  <img className="tf-bestcard__logo" src={getTeamLogoUrl(t.abbrev)} alt=""
                    onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
                  <span className="tf-bestcard__name">{t.name}</span>
                  {d.reason && <span className="tf-bestcard__reason">{d.reason}</span>}
                </button>
              )
            })}
          </div>
        </>
      ) : (
        <p className="tf-best__msg">No clearly stronger fit elsewhere.</p>
      )}
    </div>
  )
}
