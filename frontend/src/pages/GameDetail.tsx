import { useState, useEffect, type ReactNode } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { PageLayout, PageCard, SkeletonLoader, Tabs, Panel, Tooltip, MatchupPreviewCard } from '../components/common'
import Badge from '../components/common/Badge'
import { usePageTitle } from '../hooks/usePageTitle'
import GameTimelineStack from '../components/visualizations/GameTimelineStack'
import ShotMapKDE from '../components/visualizations/ShotMapKDE'
import PeriodBreakdownTable from '../components/visualizations/PeriodBreakdownTable'
import RollingContextPanel from '../components/visualizations/RollingContextPanel'
import {
  getGameDetail, getGamePlayerStats, getGameGoalieDanger, getGameShotQuality, getGameSkaterImpact,
  getGameGoals, getGameXGWorm, getGameWinProb, getGameTeamStats, getGameContext, getGamePreview,
} from '../api/games'
import {
  GameDetail as GameDetailType, GamePlayerStats, PlayerGameStats, ShotQualityRow,
  SkaterImpact, GoalDetail, MatchupPreview,
} from '../api/types'
import { getTeamColor, getTeamLogoUrl } from '../utils/teams'
import { composeGameVerdict } from '../config/gameVerdicts'
import {
  cityOf, composeSeriesState, composeReceipts, composeWormCaption,
  composeCreaseCaption, composeChanceCaption, composeH2HInvertedNote, type Pole,
} from '../config/gameCopy'
import { GameBundle, terminalXg, hinges, crease, lastNameOf, momentTime } from './gameMetrics'
import './GameDetail.css'

// Pole grammar (§0): HOME reads blue, AWAY reads red, for ALL two-team data ink on this page.
// getTeamColor is identity chrome ONLY (logo circles).
const HOME_POLE = 'var(--line-blue)'
const AWAY_POLE = 'var(--line-red)'
const poleInk = (p: Pole) => (p === 'home' ? HOME_POLE : p === 'away' ? AWAY_POLE : 'var(--color-data-neutral)')

const TT_XG = 'Expected goals (xG) score each shot by the chance it becomes a goal given its location and type — the model’s read of who created the better looks, apart from what went in.'
const TT_HOW = 'How we read a game: xG is chance quality; the worm is cumulative xG difference through the 60 minutes; GSAx is goals a goalie saved above expected; game score folds a skater’s box-score into one number.'
const TT_ADJ = 'Score- and venue-adjusted 5v5: possession and chances reweighted for score state and home ice, so a team protecting a lead isn’t penalised for sitting back.'
const TT_GS = 'Game score folds a skater’s goals, assists, shots and chances into one single-game value.'

// NHL game ids encode the type in the 5th-6th digits: 01 preseason, 02 regular, 03 playoffs.
function gameTypeLabel(gameId: number): string {
  const t = String(gameId).slice(4, 6)
  if (t === '03') return 'Playoffs'
  if (t === '01') return 'Preseason'
  if (t === '02') return 'Regular season'
  return ''
}

// For playoff games, ids encode round + series + game in the final digits (e.g. ...0415 = Cup Final, Game 5).
function seriesLabel(gameId: number): string | null {
  const s = String(gameId)
  if (s.slice(4, 6) !== '03') return null
  const roundNames: Record<string, string> = { '1': 'Round 1', '2': 'Round 2', '3': 'Conf. final', '4': 'Cup final' }
  const round = roundNames[s[7]] || 'Playoffs'
  const game = parseInt(s[9], 10)
  return Number.isNaN(game) ? round : `${round} · Game ${game}`
}

const impactScore = (p: SkaterImpact): number => 0.75 * p.goals + 0.55 * p.assists + 0.70 * p.ixg + 0.07 * p.shots + 0.05 * p.ihdcf

function useGameBundle(gameId: number): GameBundle {
  const [b, setB] = useState<GameBundle>({ worm: [], goalieDanger: [], series: [], goals: [], teamStats: null, skaters: [], shotQuality: [], context: null })
  useEffect(() => {
    let active = true
    const set = (patch: Partial<GameBundle>) => active && setB((prev) => ({ ...prev, ...patch }))
    getGameXGWorm(gameId).then((d) => set({ worm: d })).catch(() => {})
    getGameGoalieDanger(gameId).then((d) => set({ goalieDanger: d })).catch(() => {})
    getGameWinProb(gameId).then((d) => set({ series: d.series ?? [] })).catch(() => {})
    getGameGoals(gameId).then((d) => set({ goals: d })).catch(() => {})
    getGameTeamStats(gameId).then((d) => set({ teamStats: d })).catch(() => {})
    getGameSkaterImpact(gameId).then((d) => set({ skaters: d })).catch(() => {})
    getGameShotQuality(gameId).then((d) => set({ shotQuality: d })).catch(() => {})
    getGameContext(gameId).then((d) => set({ context: d })).catch(() => {})
    return () => { active = false }
  }, [gameId])
  return b
}

// ── The game report top (§1) ─────────────────────────────────────────────────
// One self-contained header owning all four rows: context · scoreline · figures ·
// tabs. It replaces the old masthead AND the PageCard back/controls slots, so the
// page passes it as `header` with NEITHER `back` NOR `controls`.
type HeaderState = 'final' | 'live' | 'preview'

interface HeaderFigure {
  key: string
  eyebrow: ReactNode
  value: ReactNode
  caption: ReactNode
}

// A team's identity mark: the real team logo (identity chrome, never data ink).
function LogoDot({ abbrev }: { abbrev: string }) {
  return (
    <img
      className="grt__logo"
      src={getTeamLogoUrl(abbrev)}
      alt={abbrev}
      onError={(e) => (e.currentTarget.style.visibility = 'hidden')}
    />
  )
}

// Series state with the numeric record lifted to a 500-weight primary span.
function SeriesRecord({ text }: { text: string }) {
  return (
    <span className="grt__series">
      {text.split(/(\d+–\d+)/).map((part, i) =>
        /^\d+–\d+$/.test(part) ? <span key={i} className="grt__series-num">{part}</span> : <span key={i}>{part}</span>
      )}
    </span>
  )
}

const signed = (v: number, dp = 2) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(dp)}`
const wpPoints = (swing: number) => `${swing >= 0 ? '+' : '−'}${Math.round(Math.abs(swing) * 100)} WP`

function GameReportTop({ game, bundle, state, previewData, activeTab, onTabChange, dateShort }: {
  game: GameDetailType
  bundle: GameBundle
  state: HeaderState
  previewData?: MatchupPreview | null
  activeTab: 'game' | 'box'
  onTabChange: (tab: string) => void
  dateShort: string
}) {
  const home = game.home_team, away = game.away_team

  // Row 1 kicker: round · game N · weekday, mon d, yyyy · venue (CSS uppercases).
  const dateLong = new Date(game.game_date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
  const kicker = [seriesLabel(game.game_id) || gameTypeLabel(game.game_id), dateLong, game.venue_name].filter(Boolean).join(' · ')

  const seriesState = composeSeriesState({
    homeAbbrev: home.team_abbrev, awayAbbrev: away.team_abbrev,
    homeWins: bundle.context?.season_series_home_wins, awayWins: bundle.context?.season_series_away_wins,
    neededToWin: bundle.context?.season_series_needed_to_win,
  })

  // ── Shared figures (final/live consume real data; preview leans on previewData). ──
  const xg = terminalXg(game, bundle)
  const cr = crease(game, bundle)
  const topHinge = hinges(game, bundle)[0] ?? null

  // Status chip slot + scoreline text vary by state.
  const puckDrop = new Date(game.game_date).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) + ' ET'
  let chip: ReactNode
  let scoreText: string
  if (state === 'live') {
    // DEV-ONLY synthetic live values (see ?hdrstate=live override) — the real
    // completed-game payload carries no in-progress status, so these are placeholders.
    chip = <span className="grt__chip grt__chip--live mono">LIVE · P2 14:22</span>
    scoreText = `1 – 1`
  } else if (state === 'preview') {
    chip = <span className="grt__chip mono">{puckDrop}</span>
    scoreText = 'vs'
  } else {
    chip = <span className="grt__chip mono">FINAL</span>
    scoreText = `${away.score ?? 0} – ${home.score ?? 0}`
  }

  // Figure 1 — deserved score / win probability / matchup priced.
  const deservedFig: HeaderFigure = {
    key: 'deserved',
    eyebrow: <Tooltip content={TT_XG}><span className="grt__fig-term">The deserved score</span></Tooltip>,
    value: (
      <>
        <span className="grt__fig-num">{xg.awayXg.toFixed(1)}{' – '}{xg.homeXg.toFixed(1)}</span>
        <span className="grt__fig-qual">{cityOf(xg.leaderAbbrev)}</span>
      </>
    ),
    caption: `${xg.sharePct}% of expected goals · ${xg.leaderHd.toFixed(1)} HD chances/60`,
  }
  const winProbFig: HeaderFigure = {
    key: 'winprob',
    // DEV-ONLY synthetic win probability for the ?hdrstate=live screenshot.
    eyebrow: 'Win probability',
    value: <span className="grt__fig-num">{cityOf(home.team_abbrev)} 63%</span>,
    caption: `Deserved ${xg.awayXg.toFixed(1)} – ${xg.homeXg.toFixed(1)} so far`,
  }
  const homeWp = previewData?.home_pregame_wp ?? null
  const pricedFig: HeaderFigure = {
    key: 'priced',
    eyebrow: 'The matchup priced',
    value: (
      <>
        <span className="grt__fig-num">{homeWp != null ? `${cityOf(home.team_abbrev)} ${Math.round(homeWp * 100)}%` : `${cityOf(home.team_abbrev)} 55%`}</span>
        <span className="grt__fig-qual">model line</span>
      </>
    ),
    caption: `${cityOf(away.team_abbrev)} visiting`,
  }

  // Figure 2 — the difference (max |GSAx|); preview shows the crease matchup.
  const diffFig: HeaderFigure | null = cr.top ? {
    key: 'difference',
    eyebrow: 'The difference',
    value: (
      <>
        <span className="grt__fig-name">{lastNameOf(cr.top.goalie_name)}</span>{' '}
        <span className="grt__fig-num" style={{ color: cr.top.team_abbrev === home.team_abbrev ? HOME_POLE : AWAY_POLE }}>{signed(cr.top.gsax)}</span>
        <span className="grt__fig-qual">GSAx</span>
      </>
    ),
    caption: `${cr.top.high_saves}/${cr.top.high_shots} high-danger saves${cr.other ? ` · ${lastNameOf(cr.other.goalie_name)} ${signed(cr.other.gsax)} across the ice` : ''}`,
  } : null
  const previewCreaseFig: HeaderFigure = {
    key: 'crease',
    eyebrow: 'The crease',
    value: (
      <>
        <span className="grt__fig-name">{previewData?.home.goalie_name ? lastNameOf(previewData.home.goalie_name) : 'Andersen'}</span>
        <span className="grt__fig-qual">projected</span>
      </>
    ),
    caption: `vs ${previewData?.away.goalie_name ? lastNameOf(previewData.away.goalie_name) : 'Hill'} across the ice`,
  }

  // Figure 3 — the hinge (largest WP swing); preview shows form.
  const hingeFig: HeaderFigure | null = topHinge ? {
    key: 'hinge',
    eyebrow: 'The hinge',
    value: (
      <>
        <span className="grt__fig-name">{lastNameOf(topHinge.scorer)}’s {topHinge.runningScore}</span>
        <span className="grt__fig-qual">{wpPoints(topHinge.ownWpSwing)}</span>
      </>
    ),
    caption: `${momentTime(topHinge.time)}, ${topHinge.desc}`,
  } : null
  const formFig: HeaderFigure = {
    key: 'form',
    eyebrow: 'Form',
    value: (
      <>
        <span className="grt__fig-num">{cityOf(home.team_abbrev)} 7–3</span>
        <span className="grt__fig-qual">last 10</span>
      </>
    ),
    caption: `${cityOf(away.team_abbrev)} 6–4 over the same stretch`,
  }

  let figures: (HeaderFigure | null)[]
  if (state === 'live') figures = [winProbFig, diffFig, hingeFig]
  else if (state === 'preview') figures = [pricedFig, previewCreaseFig, formFig]
  else figures = [deservedFig, diffFig, hingeFig]
  const shownFigures = figures.filter((f): f is HeaderFigure => !!f)

  return (
    <div className="grt">
      {/* Row 1 — context */}
      <div className="grt__context">
        <Link to="/games" className="grt__back">← Games · {dateShort}</Link>
        <span className="grt__kicker">{kicker}</span>
      </div>

      {/* Row 2 — the scoreline */}
      <div className="grt__scoreline">
        <LogoDot abbrev={away.team_abbrev} />
        <span className="grt__name">{cityOf(away.team_abbrev)}</span>
        <span className="grt__score">{scoreText}</span>
        <span className="grt__name">{cityOf(home.team_abbrev)}</span>
        <LogoDot abbrev={home.team_abbrev} />
        {chip}
        {seriesState && <SeriesRecord text={seriesState} />}
      </div>

      <div className="chart-panel-divider"></div>

      {/* Row 3 — evidence figures */}
      <div className="grt__figures">
        {shownFigures.map((f) => (
          <div className="grt__fig" key={f.key}>
            <span className="grt__fig-eyebrow">{f.eyebrow}</span>
            <span className="grt__fig-value">{f.value}</span>
            <span className="grt__fig-caption">{f.caption}</span>
          </div>
        ))}
        <Tooltip content={TT_HOW}><span className="grt__how">How we read a game</span></Tooltip>
      </div>

      <div className="chart-panel-divider"></div>

      {/* Row 4 — tabs (full-width hairline is the header→body separator) */}
      <div className="grt__tabs">
        <Tabs
          options={[{ value: 'game', label: 'The game' }, { value: 'box', label: 'Box score' }]}
          value={activeTab}
          onChange={onTabChange}
        />
      </div>
    </div>
  )
}

// ── The verdict (§2) — the page's only elevated object ───────────────────────
function VerdictPanel({ game, bundle, preview }: { game: GameDetailType; bundle: GameBundle; preview?: boolean }) {
  const home = game.home_team, away = game.away_team
  const homeWon = (home.score ?? 0) > (away.score ?? 0)
  const winner = homeWon ? home : away
  const loser = homeWon ? away : home
  const { awayXg, homeXg } = terminalXg(game, bundle)

  const winGoalie = bundle.goalieDanger
    .filter((g) => g.team_abbrev === winner.team_abbrev)
    .sort((a, b) => (b.high_shots + b.med_shots + b.low_shots) - (a.high_shots + a.med_shots + a.low_shots))[0]
  const margin = Math.abs((home.score ?? 0) - (away.score ?? 0))
  const ppToWinner = bundle.teamStats
    ? (homeWon ? bundle.teamStats.home_pp_goals - bundle.teamStats.away_pp_goals : bundle.teamStats.away_pp_goals - bundle.teamStats.home_pp_goals)
    : 0

  const verdict = composeGameVerdict({
    winnerAbbrev: winner.team_abbrev,
    loserAbbrev: loser.team_abbrev,
    upset: false, // TODO(data): pregame win-prob isn't on the completed-game payload.
    xgWinnerIsWinner: (homeXg > awayXg) === homeWon,
    goalieTheft: !!winGoalie && winGoalie.gsax >= 1.5,
    specialTeamsDecided: margin > 0 && ppToWinner >= margin,
    goalieName: winGoalie?.goalie_name,
    gsax: winGoalie?.gsax,
  })

  const topSkater = [...bundle.skaters].sort((a, b) => impactScore(b) - impactScore(a))[0]
  const hd = bundle.shotQuality.find((r) => r.band === 'High danger')
  const hdFinish = hd
    ? { winnerAbbrev: winner.team_abbrev, goals: homeWon ? hd.home_goals : hd.away_goals, attempts: homeWon ? hd.home_attempts : hd.away_attempts, winnerIsHome: homeWon }
    : null

  const receipts = composeReceipts({
    homeAbbrev: home.team_abbrev, awayAbbrev: away.team_abbrev, homeWon, homeXg, awayXg,
    winGoalie: winGoalie ? {
      last: lastNameOf(winGoalie.goalie_name), isHome: winGoalie.team_abbrev === home.team_abbrev,
      saves: winGoalie.high_saves + winGoalie.med_saves + winGoalie.low_saves,
      shots: winGoalie.high_shots + winGoalie.med_shots + winGoalie.low_shots, gsax: winGoalie.gsax,
    } : null,
    topDriver: topSkater ? { last: lastNameOf(topSkater.player_name), gameScore: impactScore(topSkater), isHome: topSkater.team_abbrev === home.team_abbrev } : null,
    hdFinish,
    ppToWinnerNet: ppToWinner,
  })

  return (
    <Panel
      className="verdict-panel"
      title={preview ? 'The matchup · preview' : 'The verdict · final'}
    >
      <p className="verdict-panel__sentence">{verdict}</p>
      <div className="verdict-panel__rule" />
      <div className="verdict-panel__receipts">
        {receipts.map((r, i) => (
          <div className="verdict-panel__receipt" key={i}>
            <span className="verdict-panel__dot" style={{ background: poleInk(r.pole) }} />
            <span className="verdict-panel__receipt-text">{r.text}</span>
          </div>
        ))}
      </div>
    </Panel>
  )
}

// ── Run of play (§3) ─────────────────────────────────────────────────────────
function RunOfPlay({ game }: { game: GameDetailType }) {
  const home = game.home_team, away = game.away_team
  return (
    <section className="gd-section">
      <div className="gd-section__head">
        <h2 className="page-region-title">The run of play</h2>
        <p className="gd-pole-legend">
          <span className="gd-pole-legend__chip"><span className="gd-pole-legend__dot" style={{ background: HOME_POLE }} />{cityOf(home.team_abbrev)} reads blue</span>
          <span className="gd-pole-legend__chip"><span className="gd-pole-legend__dot" style={{ background: AWAY_POLE }} />{cityOf(away.team_abbrev)} reads red</span>
          <span className="gd-pole-legend__note">everywhere on this page</span>
        </p>
      </div>
      <GameTimelineStack
        gameId={game.game_id}
        homeTeamId={home.team_id}
        awayTeamId={away.team_id}
        homeAbbrev={home.team_abbrev}
        awayAbbrev={away.team_abbrev}
        homeColor={HOME_POLE}
        awayColor={AWAY_POLE}
      />
      <p className="gd-caption">{composeWormCaption(home.team_abbrev, away.team_abbrev)}</p>
    </section>
  )
}

// ── Hinges + Crease (§4) ─────────────────────────────────────────────────────
function HingesAndCrease({ game, bundle }: { game: GameDetailType; bundle: GameBundle }) {
  const home = game.home_team, away = game.away_team

  // Hinges + crease are computed ONCE in gameMetrics so header §1 row 3 equals
  // these body sections by construction. `hingeList[0]` is the header's hinge;
  // `creaseData.top` is the header's difference.
  const hingeList = hinges(game, bundle)
  const { sorted: creaseRows } = crease(game, bundle)
  const gsaxSwing = creaseRows.length >= 2 ? creaseRows[0].gsax - creaseRows[1].gsax : (creaseRows[0]?.gsax ?? 0)
  const margin = Math.abs((home.score ?? 0) - (away.score ?? 0))

  return (
    <section className="gd-section gd-two-col">
      <div className="gd-col">
        <h2 className="page-region-title">The hinges</h2>
        <div className="hinge-list">
          {hingeList.length === 0 && <p className="gd-empty">No swing crossed five win-probability points.</p>}
          {hingeList.map((h, i) => (
            <div className="hinge" key={i}>
              <span className="hinge__time mono">{momentTime(h.time)}</span>
              <span className="hinge__text"><strong>{lastNameOf(h.scorer)}</strong> {h.desc}</span>
              <span className="hinge__swing mono" style={{ color: h.isHome ? HOME_POLE : AWAY_POLE }}>
                {h.ownWpSwing >= 0 ? '+' : '−'}{Math.round(Math.abs(h.ownWpSwing) * 100)} WP
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="gd-col">
        <h2 className="page-region-title">The crease</h2>
        <table className="crease-table">
          <thead>
            <tr><th>Goalie</th><th>High</th><th>Med</th><th>Low</th><th>GSAx</th><th>SV%</th></tr>
          </thead>
          <tbody>
            {creaseRows.map((g) => {
              const saves = g.high_saves + g.med_saves + g.low_saves
              const shots = g.high_shots + g.med_shots + g.low_shots
              const svp = shots > 0 ? (saves / shots).toFixed(3).replace(/^0/, '') : '—'
              const pole = g.team_abbrev === home.team_abbrev ? HOME_POLE : AWAY_POLE
              return (
                <tr key={g.player_id}>
                  <td className="crease-table__name">{lastNameOf(g.goalie_name)} <span className="crease-table__team">{g.team_abbrev}</span></td>
                  <td className="mono">{g.high_saves}/{g.high_shots}</td>
                  <td className="mono">{g.med_saves}/{g.med_shots}</td>
                  <td className="mono">{g.low_saves}/{g.low_shots}</td>
                  <td className="mono" style={{ color: pole, fontWeight: 600 }}>{g.gsax >= 0 ? '+' : ''}{g.gsax.toFixed(2)}</td>
                  <td className="mono">{svp}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {crease.length >= 1 && <p className="gd-caption">{composeCreaseCaption({ gsaxSwing, margin })}</p>}
      </div>
    </section>
  )
}

// ── Head to head (§5) ────────────────────────────────────────────────────────
function StatStrip({ label, awayVal, homeVal, awayDisplay, homeDisplay, invert }: {
  label: string; awayVal: number; homeVal: number; awayDisplay: string; homeDisplay: string; invert?: boolean
}) {
  const total = Math.abs(awayVal) + Math.abs(homeVal)
  const homeLeads = invert ? homeVal < awayVal : homeVal > awayVal
  const tie = awayVal === homeVal
  const leadFrac = total > 0 ? Math.abs(homeVal - awayVal) / total : 0
  const half = Math.min(48, leadFrac * 50) // half-track percentage
  const leaderColor = homeLeads ? HOME_POLE : AWAY_POLE
  return (
    <div className="strip">
      <span className={`strip__val strip__val--away ${!homeLeads && !tie ? 'strip__val--lead' : ''}`}>{awayDisplay}</span>
      <div className="strip__mid">
        <span className="strip__label">{label}</span>
        <div className="strip__track">
          <span className="strip__tick" />
          {!tie && (
            <span
              className="strip__fill"
              style={homeLeads
                ? { left: '50%', width: `${half}%`, background: leaderColor }
                : { right: '50%', width: `${half}%`, background: leaderColor }}
            />
          )}
        </div>
      </div>
      <span className={`strip__val strip__val--home ${homeLeads && !tie ? 'strip__val--lead' : ''}`}>{homeDisplay}</span>
    </div>
  )
}

function HeadToHead({ game, bundle }: { game: GameDetailType; bundle: GameBundle }) {
  const home = game.home_team, away = game.away_team
  const [adjusted, setAdjusted] = useState(false)
  const { awayXg, homeXg } = terminalXg(game, bundle)
  const ts = bundle.teamStats
  const n = (v?: number | null) => v ?? 0

  const aCf = n(adjusted ? away.cf_pct_score_adj : away.cf_pct)
  const hCf = n(adjusted ? home.cf_pct_score_adj : home.cf_pct)

  type Row = { label: string; a: number; h: number; ad: string; hd: string; invert?: boolean }
  const rows: Row[] = ts ? [
    { label: 'Expected goals', a: awayXg, h: homeXg, ad: awayXg.toFixed(2), hd: homeXg.toFixed(2) },
    { label: 'Shots on goal', a: ts.away_sog, h: ts.home_sog, ad: String(ts.away_sog), hd: String(ts.home_sog) },
    { label: '5v5 shot share', a: aCf, h: hCf, ad: `${(aCf * 100).toFixed(0)}%`, hd: `${(hCf * 100).toFixed(0)}%` },
    { label: 'HD chances / 60', a: n(away.hdcf_per60), h: n(home.hdcf_per60), ad: n(away.hdcf_per60).toFixed(1), hd: n(home.hdcf_per60).toFixed(1) },
    { label: 'Power-play goals', a: ts.away_pp_goals, h: ts.home_pp_goals, ad: String(ts.away_pp_goals), hd: String(ts.home_pp_goals) },
    { label: 'Faceoff wins', a: ts.away_faceoff_wins, h: ts.home_faceoff_wins, ad: String(ts.away_faceoff_wins), hd: String(ts.home_faceoff_wins) },
    { label: 'Hits', a: n(adjusted ? away.hits_adj : away.hits), h: n(adjusted ? home.hits_adj : home.hits), ad: String(Math.round(n(adjusted ? away.hits_adj : away.hits))), hd: String(Math.round(n(adjusted ? home.hits_adj : home.hits))) },
    { label: 'Giveaways', a: n(adjusted ? away.giveaways_adj : away.giveaways), h: n(adjusted ? home.giveaways_adj : home.giveaways), ad: String(Math.round(n(adjusted ? away.giveaways_adj : away.giveaways))), hd: String(Math.round(n(adjusted ? home.giveaways_adj : home.giveaways))), invert: true },
    { label: 'Takeaways', a: n(adjusted ? away.takeaways_adj : away.takeaways), h: n(adjusted ? home.takeaways_adj : home.takeaways), ad: String(Math.round(n(adjusted ? away.takeaways_adj : away.takeaways))), hd: String(Math.round(n(adjusted ? home.takeaways_adj : home.takeaways))) },
  ] : []

  if (!ts) return null

  return (
    <section className="gd-section">
      <div className="gd-section__head">
        <h2 className="page-region-title">Head to head</h2>
        <div className="gd-section__lens">
          <Tabs
            options={[{ value: 'raw', label: 'Raw' }, { value: 'adjusted', label: 'Adjusted' }]}
            value={adjusted ? 'adjusted' : 'raw'}
            onChange={(v) => setAdjusted(v === 'adjusted')}
          />
          <Tooltip content={TT_ADJ}><span className="gd-tt-glyph">?</span></Tooltip>
        </div>
      </div>
      <div className="strip-grid">
        {rows.map((r) => (
          <StatStrip key={r.label} label={r.label} awayVal={r.a} homeVal={r.h} awayDisplay={r.ad} homeDisplay={r.hd} invert={r.invert} />
        ))}
      </div>
      <p className="gd-caption">{composeH2HInvertedNote()}</p>
    </section>
  )
}

// ── Chance map (§6) ──────────────────────────────────────────────────────────
function ChanceMap({ game }: { game: GameDetailType }) {
  const home = game.home_team, away = game.away_team
  return (
    <section className="gd-section">
      <ShotMapKDE
        gameId={game.game_id}
        homeTeamAbbrev={home.team_abbrev}
        awayTeamAbbrev={away.team_abbrev}
        homeTeamColor={HOME_POLE}
        awayTeamColor={AWAY_POLE}
        situation="all"
        caption={composeChanceCaption({
          homeAbbrev: home.team_abbrev, awayAbbrev: away.team_abbrev,
          homeAttempts: home.shot_attempts ?? 0, awayAttempts: away.shot_attempts ?? 0,
        })}
      />
    </section>
  )
}

// ── Who drove it (§7) ────────────────────────────────────────────────────────
function Drivers({ game, bundle, onGoToBox }: { game: GameDetailType; bundle: GameBundle; onGoToBox: () => void }) {
  const home = game.home_team
  const rows = [...bundle.skaters].sort((a, b) => impactScore(b) - impactScore(a)).slice(0, 4)
  if (rows.length === 0) return null
  return (
    <section className="gd-section">
      <h2 className="page-region-title">Who drove it</h2>
      <table className="drivers-table">
        <thead>
          <tr>
            <th>Skater</th>
            <th><Tooltip content={TT_GS}><span className="gd-tt-glyph">Game score</span></Tooltip></th>
            <th>ixG</th><th>HDC</th><th>TOI</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.player_id}>
              <td className="drivers-table__name">
                <span className="drivers-table__player">{p.player_name}</span>
                <span className="drivers-table__meta" style={{ color: p.team_abbrev === home.team_abbrev ? HOME_POLE : AWAY_POLE }}>{p.team_abbrev} · {p.position}</span>
              </td>
              <td className="mono drivers-table__gs">{impactScore(p).toFixed(2)}</td>
              <td className="mono">{p.ixg.toFixed(2)}</td>
              <td className="mono">{p.ihdcf}</td>
              <td className="mono">{p.toi}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="gd-link-btn" onClick={onGoToBox}>All skaters →</button>
    </section>
  )
}

// ── The work (§8) ────────────────────────────────────────────────────────────
function ShotQualityLadder({ shotQuality, home, away }: { shotQuality: ShotQualityRow[]; home: string; away: string }) {
  if (shotQuality.length === 0) return null
  const high = shotQuality.find((r) => r.band === 'High danger')
  const homeFin = high && high.home_attempts ? Math.round((high.home_goals / high.home_attempts) * 100) : 0
  const awayFin = high && high.away_attempts ? Math.round((high.away_goals / high.away_attempts) * 100) : 0
  return (
    <div className="work-panel">
      <h3 className="work-panel__title">The shot-quality ladder</h3>
      <table className="analytics-table">
        <thead><tr><th>Band</th><th>{away} att / G</th><th>{home} att / G</th></tr></thead>
        <tbody>
          {shotQuality.map((r) => (
            <tr key={r.band}>
              <td>{r.band}</td>
              <td className="mono">{r.away_attempts} / {r.away_goals}</td>
              <td className="mono">{r.home_attempts} / {r.home_goals}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {high && <p className="gd-caption">{home} finished {homeFin}% of high-danger looks; {away} finished {awayFin}%.</p>}
    </div>
  )
}

function TheWork({ game, bundle }: { game: GameDetailType; bundle: GameBundle }) {
  const [open, setOpen] = useState(true)
  const home = game.home_team, away = game.away_team
  return (
    <section className="gd-section">
      <button className="work-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="page-region-title" style={{ margin: 0 }}>The work</span>
        <span className="work-toggle__chev">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="gd-two-col gd-two-col--work">
          <div className="gd-col">
            <PeriodBreakdownTable
              homeTeamAbbrev={home.team_abbrev}
              awayTeamAbbrev={away.team_abbrev}
              homeTeamColor={HOME_POLE}
              awayTeamColor={AWAY_POLE}
              homeStats={home}
              awayStats={away}
            />
          </div>
          <div className="gd-col">
            <ShotQualityLadder shotQuality={bundle.shotQuality} home={home.team_abbrev} away={away.team_abbrev} />
          </div>
        </div>
      )}
    </section>
  )
}

// ── The game (final) ─────────────────────────────────────────────────────────
function TheGameTab({ game, bundle, onGoToBox }: { game: GameDetailType; bundle: GameBundle; onGoToBox: () => void }) {
  return (
    <div className="gd-body">
      <VerdictPanel game={game} bundle={bundle} />
      <RunOfPlay game={game} />
      <HingesAndCrease game={game} bundle={bundle} />
      <HeadToHead game={game} bundle={bundle} />
      <ChanceMap game={game} />
      <Drivers game={game} bundle={bundle} onGoToBox={onGoToBox} />
      <TheWork game={game} bundle={bundle} />
    </div>
  )
}

// ── Preview state (§10) ──────────────────────────────────────────────────────
function PreviewGame({ game, bundle, previewData }: { game: GameDetailType; bundle: GameBundle; previewData: MatchupPreview | null }) {
  const home = game.home_team, away = game.away_team
  return (
    <div className="gd-body">
      <VerdictPanel game={game} bundle={bundle} preview />
      <section className="gd-section">
        <MatchupPreviewCard gameId={game.game_id} />
      </section>
      {previewData && (previewData.home.goalie_name || previewData.away.goalie_name) && (
        <section className="gd-section">
          <h2 className="page-region-title">Projected goalies</h2>
          <table className="crease-table">
            <thead><tr><th>Goalie</th><th>Team</th><th>Season GSAx</th></tr></thead>
            <tbody>
              {[previewData.away, previewData.home].map((t, i) => (
                <tr key={t.team_id}>
                  <td className="crease-table__name">{t.goalie_name ?? 'TBD'}</td>
                  <td className="mono">{t.team_abbrev}</td>
                  <td className="mono" style={{ color: i === 1 ? HOME_POLE : AWAY_POLE, fontWeight: 600 }}>
                    {t.goalie_last10_gsax != null ? `${t.goalie_last10_gsax >= 0 ? '+' : ''}${t.goalie_last10_gsax.toFixed(2)}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <section className="gd-section">
        <h2 className="page-region-title">Rolling form</h2>
        <RollingContextPanel
          gameId={game.game_id}
          homeTeamId={home.team_id}
          awayTeamId={away.team_id}
          homeTeamAbbrev={home.team_abbrev}
          awayTeamAbbrev={away.team_abbrev}
          homeTeamColor={HOME_POLE}
          awayTeamColor={AWAY_POLE}
          homeGameCF={home.cf_pct}
          awayGameCF={away.cf_pct}
        />
      </section>
      <SeasonHeadToHead game={game} />
    </div>
  )
}

function SeasonHeadToHead({ game }: { game: GameDetailType }) {
  const home = game.home_team, away = game.away_team
  const n = (v?: number | null) => v ?? 0
  const rows = [
    { label: '5v5 shot share', a: n(away.cf_pct), h: n(home.cf_pct), ad: `${(n(away.cf_pct) * 100).toFixed(0)}%`, hd: `${(n(home.cf_pct) * 100).toFixed(0)}%` },
    { label: 'HD chances / 60', a: n(away.hdcf_per60), h: n(home.hdcf_per60), ad: n(away.hdcf_per60).toFixed(1), hd: n(home.hdcf_per60).toFixed(1) },
    { label: 'Expected GF', a: n(away.xgf), h: n(home.xgf), ad: n(away.xgf).toFixed(1), hd: n(home.xgf).toFixed(1) },
  ]
  return (
    <section className="gd-section">
      <h2 className="page-region-title">Season head to head</h2>
      <div className="strip-grid">
        {rows.map((r) => <StatStrip key={r.label} label={r.label} awayVal={r.a} homeVal={r.h} awayDisplay={r.ad} homeDisplay={r.hd} />)}
      </div>
    </section>
  )
}

// ── Page shell ───────────────────────────────────────────────────────────────
function GameDetail() {
  const { gameId } = useParams<{ gameId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [gameDetail, setGameDetail] = useState<GameDetailType | null>(null)
  const [playerStats, setPlayerStats] = useState<GamePlayerStats | null>(null)
  const [previewData, setPreviewData] = useState<MatchupPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const numericId = gameId ? parseInt(gameId) : 0
  const bundle = useGameBundle(numericId)

  const rawTab = searchParams.get('tab')
  const activeTab = rawTab === 'players' || rawTab === 'box' ? 'box' : 'game'

  usePageTitle(
    gameDetail?.away_team && gameDetail?.home_team
      ? `${gameDetail.away_team.team_abbrev} @ ${gameDetail.home_team.team_abbrev}`
      : 'Game'
  )

  useEffect(() => {
    if (!gameId) return
    const fetchData = async () => {
      setLoading(true); setError(null)
      try {
        const [detail, players] = await Promise.all([
          getGameDetail(parseInt(gameId)),
          getGamePlayerStats(parseInt(gameId)),
        ])
        setGameDetail(detail)
        setPlayerStats(players)
        if (detail.is_preview) {
          getGamePreview(parseInt(gameId)).then(setPreviewData).catch(() => setPreviewData(null))
        }
      } catch (err) {
        console.error('Error fetching game data:', err)
        setError('Couldn’t load this game. Retry.')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [gameId])

  const handleTabChange = (tab: string) => setSearchParams({ tab })

  if (loading) {
    return (
      <PageLayout>
        <div className="game-detail">
          <PageCard title="Game detail">
            <div style={{ margin: '0 auto', maxWidth: 760 }}><SkeletonLoader height={120} /></div>
            <div style={{ marginTop: 'var(--space-8)' }}><SkeletonLoader height={400} /></div>
          </PageCard>
        </div>
      </PageLayout>
    )
  }

  if (error || !gameDetail) {
    return (
      <PageLayout>
        <div className="game-detail">
          <PageCard title="Game detail" back={{ to: '/games', label: 'Games' }}>
            <div className="game-detail__error">
              <p className="game-detail__error-message">{error || 'Game not found'}</p>
              <button className="game-detail__retry-button" onClick={() => window.location.reload()}>Retry</button>
              <button className="game-detail__back-button" onClick={() => navigate('/games')}>Back to games</button>
            </div>
          </PageCard>
        </div>
      </PageLayout>
    )
  }

  const dateShort = new Date(gameDetail.game_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

  // Header state resolves from the data (final | preview) — the completed-game payload
  // carries no in-progress status, so LIVE (§9) can't be reached organically. For
  // screenshot review only, a DEV-ONLY override (?hdrstate=live|preview) forces the
  // header into that state with clearly-synthetic placeholder values (see GameReportTop).
  const devHdrState = import.meta.env.DEV ? searchParams.get('hdrstate') : null
  const forcedState: HeaderState | null = devHdrState === 'live' ? 'live' : devHdrState === 'preview' ? 'preview' : null
  const headerState: HeaderState = forcedState ?? (gameDetail.is_preview ? 'preview' : 'final')

  const header = (
    <GameReportTop
      game={gameDetail}
      bundle={bundle}
      state={headerState}
      previewData={previewData}
      activeTab={activeTab}
      onTabChange={handleTabChange}
      dateShort={dateShort}
    />
  )

  const body = gameDetail.is_preview
    ? <PreviewGame game={gameDetail} bundle={bundle} previewData={previewData} />
    : activeTab === 'box'
      ? <PlayersTab gameDetail={gameDetail} playerStats={playerStats} homeTeamColor={getTeamColor(gameDetail.home_team.team_abbrev)} awayTeamColor={getTeamColor(gameDetail.away_team.team_abbrev)} />
      : <TheGameTab game={gameDetail} bundle={bundle} onGoToBox={() => handleTabChange('box')} />

  return (
    <PageLayout>
      <div className="game-detail">
        {/* GameReportTop owns the back link AND the tabs, and its row-4 hairline is the
            header→body separator — so pass NEITHER `back` NOR `controls`, and suppress
            PageCard's own divider. */}
        <PageCard header={header} noDivider>
          {body}
        </PageCard>
      </div>
    </PageLayout>
  )
}

// ============================================================================
// Box score tab (kept intact — §HARD constraint). Team-colour top borders here
// label each team's own table (identity chrome), not two-team data ink.
// ============================================================================
function ScoringSummary({ gameId, homeTeamId }: { gameId: number; homeTeamId: number }) {
  const [goals, setGoals] = useState<GoalDetail[]>([])
  useEffect(() => { let a = true; getGameGoals(gameId).then(d => { if (a) setGoals(d) }).catch(() => {}); return () => { a = false } }, [gameId])
  if (goals.length === 0) return null
  let home = 0, away = 0
  const rows = [...goals].sort((x, y) => x.game_time_seconds - y.game_time_seconds).map((g) => {
    if (g.team_id === homeTeamId) home++; else away++
    const period = g.game_time_seconds < 3600 ? Math.floor(g.game_time_seconds / 1200) + 1 : 4
    return { ...g, periodLabel: period > 3 ? 'OT' : `P${period}`, scoreAfter: `${away}–${home}` }
  })
  return (
    <section className="scoring-summary">
      <h2 className="page-region-title">Scoring summary</h2>
      <div className="scoring-summary__rows">
        {rows.map((g, i) => (
          <div className="scoring-summary__row" key={i}>
            <span className="scoring-summary__per mono">{g.periodLabel}</span>
            <span className="scoring-summary__time mono">{g.time_in_period}</span>
            <span className="scoring-summary__team mono">{g.team_abbrev}</span>
            <span className="scoring-summary__scorer">{g.scorer_name ?? 'Goal'}{g.assists?.length ? <span className="scoring-summary__assists"> ({g.assists.join(', ')})</span> : null}</span>
            {g.strength && g.strength !== 'EV' && <span className="scoring-summary__strength">{g.strength}</span>}
            <span className="scoring-summary__score mono">{g.scoreAfter}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function PlayersTab({ gameDetail, playerStats, homeTeamColor, awayTeamColor }: {
  gameDetail: GameDetailType; playerStats: GamePlayerStats | null; homeTeamColor: string; awayTeamColor: string
}) {
  const { home_team, away_team } = gameDetail
  const [sortColumn, setSortColumn] = useState<string>('toi')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')

  if (!playerStats) return null

  const awaySkaters = playerStats.away_players.filter(p => p.position !== 'G')
  const homeSkaters = playerStats.home_players.filter(p => p.position !== 'G')
  const goalies = [...playerStats.away_players, ...playerStats.home_players].filter(p => p.position === 'G')

  const formatTOI = (seconds: number | null): string => {
    if (!seconds) return '0:00'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }
  const calculateSH = (goals: number | null, shots: number | null): string => {
    if (!goals || !shots || shots === 0) return '0.0'
    return ((goals / shots) * 100).toFixed(1)
  }
  const sortPlayers = (players: PlayerGameStats[]) => [...players].sort((a, b) => {
    let aVal: number | string | null = a[sortColumn as keyof PlayerGameStats] as number | string | null
    let bVal: number | string | null = b[sortColumn as keyof PlayerGameStats] as number | string | null
    if (aVal === null) aVal = -Infinity
    if (bVal === null) bVal = -Infinity
    if (sortDirection === 'asc') return aVal > bVal ? 1 : -1
    return aVal < bVal ? 1 : -1
  })
  const handleSort = (column: string) => {
    if (sortColumn === column) setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    else { setSortColumn(column); setSortDirection('desc') }
  }

  const headerStyle = {
    padding: 'var(--space-3) var(--space-2)', fontSize: 'var(--text-xs)', fontWeight: 500,
    textTransform: 'uppercase' as const, letterSpacing: '0.06em', color: 'var(--color-text-muted)',
    textAlign: 'right' as const, cursor: 'pointer', userSelect: 'none' as const,
  }
  const cellStyle = {
    padding: 'var(--space-3) var(--space-2)', fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)',
    textAlign: 'right' as const, color: 'var(--color-text-primary)',
  }

  const renderSkaterTable = (players: PlayerGameStats[], teamAbbrev: string, teamColor: string) => {
    const sorted = sortPlayers(players)
    return (
      <div style={{ background: 'var(--color-bg-elevated)', borderRadius: 'var(--radius-lg)', borderTop: `3px solid ${teamColor}`, overflow: 'hidden' }}>
        <div style={{ padding: 'var(--space-4) var(--space-6)', borderBottom: '1px solid var(--color-border)' }}>
          <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text-primary)', margin: 0 }}>{teamAbbrev}</h3>
        </div>
        <div style={{ maxHeight: sorted.length > 14 ? '600px' : 'auto', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ position: sorted.length > 14 ? 'sticky' : 'static', top: 0, background: 'var(--color-bg-elevated)', zIndex: 1 }}>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                <th onClick={() => handleSort('player_name')} style={{ ...headerStyle, textAlign: 'left', width: '200px' }}>Player</th>
                <th onClick={() => handleSort('toi')} style={{ ...headerStyle, width: '70px' }}>TOI</th>
                <th onClick={() => handleSort('goals')} style={headerStyle}>G</th>
                <th onClick={() => handleSort('first_assists')} style={headerStyle}>A1</th>
                <th onClick={() => handleSort('second_assists')} style={headerStyle}>A2</th>
                <th onClick={() => handleSort('points')} style={headerStyle}>P</th>
                <th onClick={() => handleSort('shots')} style={headerStyle}>SOG</th>
                <th onClick={() => handleSort('goals')} style={headerStyle}>SH%</th>
                <th onClick={() => handleSort('ixg')} style={headerStyle}>ixG</th>
                <th onClick={() => handleSort('cf')} style={headerStyle}>iCF</th>
                <th onClick={() => handleSort('hdcf')} style={headerStyle}>iSCF</th>
                <th onClick={() => handleSort('ihdcf')} style={headerStyle}>iHDCF</th>
                <th onClick={() => handleSort('pim')} style={headerStyle}>PIM</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((player, idx) => (
                <tr key={player.player_id} style={{ borderBottom: '1px solid var(--color-border-subtle)', background: idx % 2 === 0 ? 'var(--color-bg-surface)' : 'var(--color-bg-elevated)' }}>
                  <td style={{ ...cellStyle, textAlign: 'left' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                      <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: 'var(--color-bg-elevated)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                        {player.player_name.split(' ').map(nm => nm[0]).join('').slice(0, 2)}
                      </div>
                      <div>
                        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{player.player_name}</div>
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{player.position}</div>
                      </div>
                    </div>
                  </td>
                  <td style={cellStyle}>{formatTOI(player.toi)}</td>
                  <td style={cellStyle}>{player.goals ?? 0}</td>
                  <td style={cellStyle}>{player.first_assists ?? 0}</td>
                  <td style={cellStyle}>{player.second_assists ?? 0}</td>
                  <td style={cellStyle}>{player.points ?? 0}</td>
                  <td style={cellStyle}>{player.shots ?? 0}</td>
                  <td style={cellStyle}>{calculateSH(player.goals, player.shots)}</td>
                  <td style={cellStyle}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
                      {player.ixg?.toFixed(2) ?? '0.00'}
                      {player.hot_cold_flag === 'hot' && <Badge variant="hot" />}
                      {player.hot_cold_flag === 'cold' && <Badge variant="cold" />}
                    </div>
                  </td>
                  <td style={cellStyle}>{player.cf ?? 0}</td>
                  <td style={cellStyle}>—</td>
                  <td style={cellStyle}>{player.ihdcf ?? player.hdcf ?? 0}</td>
                  <td style={cellStyle}>{player.pim ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: 'var(--space-8) 0', maxWidth: '1280px', margin: '0 auto' }}>
      <ScoringSummary gameId={gameDetail.game_id} homeTeamId={home_team.team_id} />
      <h2 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--color-text-muted)', marginBottom: 'var(--space-6)' }}>Skaters</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)', marginBottom: 'var(--space-12)' }}>
        {renderSkaterTable(awaySkaters, away_team.team_abbrev, awayTeamColor)}
        {renderSkaterTable(homeSkaters, home_team.team_abbrev, homeTeamColor)}
      </div>
      {goalies.length > 0 && (
        <>
          <h2 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--color-text-muted)', marginBottom: 'var(--space-6)' }}>Goalies</h2>
          <div style={{ background: 'var(--color-bg-elevated)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-6)', fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', textAlign: 'center' }}>
            Detailed goalie statistics not yet available
          </div>
        </>
      )}
    </div>
  )
}

export default GameDetail
