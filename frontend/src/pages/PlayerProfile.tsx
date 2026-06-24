import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { PageLayout, StatCard, Badge, SkeletonLoader, ComponentStackBar, ImpactValuePanel, OverallSummary, IdentityHeader, PlayerAvatar, PlayerValueLadder, Tabs } from '../components/common'
import type { StackSegment, PlayerValueLadderRow } from '../components/common'
import { COMPOSITE_COMPONENTS, GOALIE_VALUE_COMPONENTS } from '../config/metrics'
import ShotMap from '../components/visualizations/ShotMap'
import StripPlot from '../components/visualizations/StripPlot'
import SkillRadar from '../components/visualizations/SkillRadar'
import { playerLabelsFromRadar } from '../api/labels'
import {
  getPlayerDetail,
  getPlayerTrends,
  getPlayerShots,
  getPlayerVsOpponent,
  getPlayerGamelog,
  getPlayerReconciliation,
  getPlayerTrajectory,
  getPlayerRadar,
  getPlayerPreview,
  getPlayerValueNeighbors
} from '../api/players'
import { getGoalieRadar, getGoalieSeason } from '../api/goalies'
import {
  PlayerDetail,
  PlayerTrends,
  PlayerShots,
  PlayerVsOpponent,
  PlayerGamelog,
  PlayerReconciliation,
  PlayerTrajectory,
  PlayerRadar,
  GoalieRadar,
  GoalieSeason,
  PlayerPreview,
  ValueNeighborhood,
  RadarSpoke
} from '../api/types'
import { setTeamPrimaryColor, clearTeamPrimaryColor, getTeamColor as getTeamColorByAbbrev } from '../utils/teams'
import { ordinal } from '../utils/format'
import './PlayerProfile.css'

// NHL team list for vs opponent dropdown
const NHL_TEAMS = [
  { id: 1, abbrev: 'NJD', name: 'New Jersey Devils' },
  { id: 2, abbrev: 'NYI', name: 'New York Islanders' },
  { id: 3, abbrev: 'NYR', name: 'New York Rangers' },
  { id: 4, abbrev: 'PHI', name: 'Philadelphia Flyers' },
  { id: 5, abbrev: 'PIT', name: 'Pittsburgh Penguins' },
  { id: 6, abbrev: 'BOS', name: 'Boston Bruins' },
  { id: 7, abbrev: 'BUF', name: 'Buffalo Sabres' },
  { id: 8, abbrev: 'MTL', name: 'Montreal Canadiens' },
  { id: 9, abbrev: 'OTT', name: 'Ottawa Senators' },
  { id: 10, abbrev: 'TOR', name: 'Toronto Maple Leafs' },
  { id: 12, abbrev: 'CAR', name: 'Carolina Hurricanes' },
  { id: 13, abbrev: 'FLA', name: 'Florida Panthers' },
  { id: 14, abbrev: 'TBL', name: 'Tampa Bay Lightning' },
  { id: 15, abbrev: 'WSH', name: 'Washington Capitals' },
  { id: 16, abbrev: 'CHI', name: 'Chicago Blackhawks' },
  { id: 17, abbrev: 'DET', name: 'Detroit Red Wings' },
  { id: 18, abbrev: 'NSH', name: 'Nashville Predators' },
  { id: 19, abbrev: 'STL', name: 'St. Louis Blues' },
  { id: 20, abbrev: 'CGY', name: 'Calgary Flames' },
  { id: 21, abbrev: 'COL', name: 'Colorado Avalanche' },
  { id: 22, abbrev: 'EDM', name: 'Edmonton Oilers' },
  { id: 23, abbrev: 'VAN', name: 'Vancouver Canucks' },
  { id: 24, abbrev: 'ANA', name: 'Anaheim Ducks' },
  { id: 25, abbrev: 'DAL', name: 'Dallas Stars' },
  { id: 26, abbrev: 'LAK', name: 'Los Angeles Kings' },
  { id: 28, abbrev: 'SJS', name: 'San Jose Sharks' },
  { id: 29, abbrev: 'CBJ', name: 'Columbus Blue Jackets' },
  { id: 30, abbrev: 'MIN', name: 'Minnesota Wild' },
  { id: 52, abbrev: 'WPG', name: 'Winnipeg Jets' },
  { id: 53, abbrev: 'ARI', name: 'Arizona Coyotes' },
  { id: 54, abbrev: 'VGK', name: 'Vegas Golden Knights' },
  { id: 55, abbrev: 'SEA', name: 'Seattle Kraken' }
]

type SortColumn = 'game_date' | 'toi' | 'points' | 'goals' | 'assists' | 'shots' | 'cf' | 'hdcf'
type SortDirection = 'asc' | 'desc'

const lowerFirst = (s: string) => (s ? s[0].toLowerCase() + s.slice(1) : s)

/** One-line scouting identity from the radar labels (archetype + deployment). No em dashes. */
function scoutingIdentity(off?: string | null, def?: string | null): string | null {
  const o = off?.trim(), d = def?.trim()
  if (o && d) return `${o} with ${lowerFirst(d)}.`
  if (o || d) return `${o || d}.`
  return null
}

// The five tabs (Overview default). Each is its own URL param (?tab=), mirroring the Team page.
const PLAYER_TABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'impact', label: 'Impact & Value' },
  { value: 'trends', label: 'Trends' },
  { value: 'gamelog', label: 'Game Log' },
  { value: 'shotmap', label: 'Shot Map' },
] as const
const TAB_VALUES = PLAYER_TABS.map((t) => t.value) as readonly string[]

const POS_WORD: Record<string, string> = { F: 'forwards', D: 'defensemen', G: 'goalies' }

/** A within-position rank rendered as "4th of 248", with a color tier from its percentile. */
function rankInfo(rank?: number | null, pool?: number | null): { text: string; tier: 'top' | 'mid' | 'bottom' } | null {
  if (rank == null || !pool) return null
  const p = rank / pool   // 0 = best
  const tier = p <= 0.15 ? 'top' : p >= 0.75 ? 'bottom' : 'mid'
  return { text: `${ordinal(rank)} of ${pool}`, tier }
}

/** The player's defining radar spokes: top 3 and bottom 2 by percentile (0-100). Fills the radar
 *  card's right side with a concrete strengths/weaknesses readout. */
function standoutSpokes(spokes: RadarSpoke[]): { top: RadarSpoke[]; bottom: RadarSpoke[] } | null {
  const usable = spokes.filter((s) => s.percentile != null).sort((a, b) => (b.percentile! - a.percentile!))
  if (usable.length < 3) return null
  const top = usable.slice(0, 3)
  const bottom = usable.length >= 5 ? usable.slice(-2).reverse() : []   // weakest first; skip if too few
  return { top, bottom }
}

function PlayerProfile() {
  const { playerId } = useParams<{ playerId: string }>()
  const navigate = useNavigate()

  // URL-addressable tabs (mirrors the Team page). Default to Overview; ignore unknown values.
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab') || 'overview'
  const currentTab = TAB_VALUES.includes(tabParam) ? tabParam : 'overview'
  // Remember each tab's scroll position so returning to a tab restores where you were.
  const scrollByTab = useRef<Record<string, number>>({})
  const handleTabChange = (tab: string) => {
    scrollByTab.current[currentTab] = window.scrollY
    setSearchParams({ tab }, { replace: false })
    requestAnimationFrame(() => window.scrollTo({ top: scrollByTab.current[tab] ?? 0 }))
  }

  // Data states
  const [playerDetail, setPlayerDetail] = useState<PlayerDetail | null>(null)
  const [radar, setRadar] = useState<PlayerRadar | null>(null)
  const [goalieRadar, setGoalieRadar] = useState<GoalieRadar | null>(null)
  const [goalieSeason, setGoalieSeason] = useState<GoalieSeason | null>(null)
  const [preview, setPreview] = useState<PlayerPreview | null>(null)            // light bio (age, shoots)
  const [neighbors, setNeighbors] = useState<ValueNeighborhood | null>(null)     // header value-ranking slice
  const [reconciliation, setReconciliation] = useState<PlayerReconciliation | null>(null)
  const [trajectory, setTrajectory] = useState<PlayerTrajectory | null>(null)
  const [playerTrends, setPlayerTrends] = useState<PlayerTrends | null>(null)
  const [playerShots, setPlayerShots] = useState<PlayerShots | null>(null)
  const [playerGamelog, setPlayerGamelog] = useState<PlayerGamelog | null>(null)
  const [vsOpponentData, setVsOpponentData] = useState<PlayerVsOpponent | null>(null)

  // UI states
  const [selectedOpponent, setSelectedOpponent] = useState<number | null>(null)
  const [sortColumn, setSortColumn] = useState<SortColumn>('game_date')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  // Loading states
  const [loadingDetail, setLoadingDetail] = useState(true)
  const [loadingTrends, setLoadingTrends] = useState(true)
  const [loadingShots, setLoadingShots] = useState(true)
  const [loadingGamelog, setLoadingGamelog] = useState(true)
  const [loadingVsOpponent, setLoadingVsOpponent] = useState(false)

  // Error states
  const [errorDetail, setErrorDetail] = useState<string | null>(null)
  const [, setErrorTrends] = useState<string | null>(null)
  const [, setErrorShots] = useState<string | null>(null)
  const [, setErrorGamelog] = useState<string | null>(null)
  const [errorVsOpponent, setErrorVsOpponent] = useState<string | null>(null)

  // Fetch player detail
  useEffect(() => {
    if (!playerId) return

    const fetchPlayerDetail = async () => {
      try {
        setLoadingDetail(true)
        setErrorDetail(null)
        const data = await getPlayerDetail(parseInt(playerId))
        setPlayerDetail(data)
        // Set team primary color for contextual theming
        setTeamPrimaryColor(getTeamColorByAbbrev(data.team_abbrev))
      } catch (error) {
        setErrorDetail('Failed to load player details')
        console.error('Error fetching player detail:', error)
      } finally {
        setLoadingDetail(false)
      }
    }

    fetchPlayerDetail()

    // Cleanup: reset team primary color when leaving page
    return () => {
      clearTeamPrimaryColor()
    }
  }, [playerId])

  // Skills radar (Part B): goalie vs skater radar based on detail position
  useEffect(() => {
    if (!playerId || !playerDetail) return
    let active = true
    setRadar(null); setGoalieRadar(null); setGoalieSeason(null)
    const pid = parseInt(playerId)
    if (playerDetail.position === 'G') {
      getGoalieRadar(pid).then(r => active && setGoalieRadar(r)).catch(() => {})
      // goalie value (GAR/WAR) + within-goalie Overall live on the goalie endpoint
      getGoalieSeason(pid).then(s => active && setGoalieSeason(s)).catch(() => {})
    } else {
      getPlayerRadar(pid).then(r => active && setRadar(r)).catch(() => {})
    }
    return () => { active = false }
  }, [playerId, playerDetail])

  // Light bio (age, handedness) for the header, and the position-scoped total-value slice that
  // powers the header ranking module. Both degrade silently (header omits the piece if absent).
  useEffect(() => {
    if (!playerId) return
    let active = true
    setPreview(null); setNeighbors(null)
    const pid = parseInt(playerId)
    getPlayerPreview(pid).then((d) => active && setPreview(d)).catch(() => {})
    getPlayerValueNeighbors(pid).then((d) => active && setNeighbors(d)).catch(() => {})
    return () => { active = false }
  }, [playerId])

  // Fetch eye-test reconciliation (clutch + consistency + coach trust) — Phase 4.3
  useEffect(() => {
    if (!playerId) return
    let active = true
    setReconciliation(null)
    getPlayerReconciliation(parseInt(playerId))
      .then((d) => active && setReconciliation(d))
      .catch(() => { /* reconciliation is optional (e.g. low-minute or pre-2015) */ })
    return () => { active = false }
  }, [playerId])

  // Fetch career trajectory (aging curve + twins + physical overlay) — Phase 4.4
  useEffect(() => {
    if (!playerId) return
    let active = true
    setTrajectory(null)
    getPlayerTrajectory(parseInt(playerId))
      .then((d) => active && setTrajectory(d))
      .catch(() => { /* optional */ })
    return () => { active = false }
  }, [playerId])

  // Fetch player trends
  useEffect(() => {
    if (!playerId) return

    const fetchPlayerTrends = async () => {
      try {
        setLoadingTrends(true)
        setErrorTrends(null)
        const data = await getPlayerTrends(parseInt(playerId))
        setPlayerTrends(data)
      } catch (error) {
        setErrorTrends('Failed to load player trends')
        console.error('Error fetching player trends:', error)
      } finally {
        setLoadingTrends(false)
      }
    }

    fetchPlayerTrends()
  }, [playerId])

  // Fetch player shots
  useEffect(() => {
    if (!playerId || !playerDetail || playerDetail.position === 'G') return

    const fetchPlayerShots = async () => {
      try {
        setLoadingShots(true)
        setErrorShots(null)
        const data = await getPlayerShots(parseInt(playerId))
        setPlayerShots(data)
      } catch (error) {
        setErrorShots('Failed to load shot data')
        console.error('Error fetching player shots:', error)
      } finally {
        setLoadingShots(false)
      }
    }

    fetchPlayerShots()
  }, [playerId, playerDetail])

  // Fetch player gamelog
  useEffect(() => {
    if (!playerId) return

    const fetchPlayerGamelog = async () => {
      try {
        setLoadingGamelog(true)
        setErrorGamelog(null)
        const data = await getPlayerGamelog(parseInt(playerId))
        setPlayerGamelog(data)
      } catch (error) {
        setErrorGamelog('Failed to load game log')
        console.error('Error fetching player gamelog:', error)
      } finally {
        setLoadingGamelog(false)
      }
    }

    fetchPlayerGamelog()
  }, [playerId])

  // Fetch vs opponent data when opponent is selected
  useEffect(() => {
    if (!playerId || !selectedOpponent) return

    const fetchVsOpponent = async () => {
      try {
        setLoadingVsOpponent(true)
        setErrorVsOpponent(null)
        const data = await getPlayerVsOpponent(parseInt(playerId), selectedOpponent)
        setVsOpponentData(data)
      } catch (error) {
        setErrorVsOpponent('Failed to load vs opponent data')
        console.error('Error fetching vs opponent:', error)
      } finally {
        setLoadingVsOpponent(false)
      }
    }

    fetchVsOpponent()
  }, [playerId, selectedOpponent])

  // Helper: Format TOI from minutes to MM:SS
  const formatTOI = (minutes: number): string => {
    const mins = Math.floor(minutes)
    const secs = Math.round((minutes - mins) * 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  // Helper: Format date
  const formatDate = (dateString: string): string => {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  // Helper: Sort gamelog
  const sortedGamelog = React.useMemo(() => {
    if (!playerGamelog) return []

    const sorted = [...playerGamelog.games].sort((a, b) => {
      const aValue = a[sortColumn]
      const bValue = b[sortColumn]

      if (sortColumn === 'game_date') {
        const aDate = new Date(aValue as string).getTime()
        const bDate = new Date(bValue as string).getTime()
        return sortDirection === 'asc' ? aDate - bDate : bDate - aDate
      }

      const aNum = Number(aValue) || 0
      const bNum = Number(bValue) || 0
      return sortDirection === 'asc' ? aNum - bNum : bNum - aNum
    })

    // Limit to last 20 games
    return sorted.slice(0, 20)
  }, [playerGamelog, sortColumn, sortDirection])

  // Handler: Sort column
  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortColumn(column)
      setSortDirection('desc')
    }
  }

  // Handler: Navigate to game detail
  const handleGameClick = (gameId: number) => {
    navigate(`/games/${gameId}`)
  }

  // Handler: Navigate to team profile
  const handleTeamClick = (e: React.MouseEvent, teamId: number) => {
    e.stopPropagation()
    navigate(`/teams/${teamId}`)
  }

  const isGoalie = playerDetail?.position === 'G'
  const teamColor = playerDetail ? getTeamColorByAbbrev(playerDetail.team_abbrev) : 'var(--color-accent)'

  // ---- Header module derived values (mirrors the Team page header) ----
  const headerLabels = radar ? playerLabelsFromRadar(radar) : null
  // Prefer the data-grounded scouting sentence (generated from the radar spokes); fall back to the
  // label-based line only if it is absent.
  const identity = !isGoalie
    ? (radar?.identity_line ?? scoutingIdentity(headerLabels?.offensive, headerLabels?.defensive))
    : null
  // Headline value: WAR for the latest available season (last completed season in the offseason,
  // the in-progress season otherwise, since the value block always resolves to the latest one),
  // with the within-position overall percentile carried as a small note.
  const overallPct = isGoalie
    ? goalieSeason?.overall?.overall_percentile ?? null
    : playerDetail?.value?.overall?.overall_percentile ?? null
  const headerWar = isGoalie ? goalieSeason?.value?.war ?? null : playerDetail?.value?.war ?? null
  const ladderRows: PlayerValueLadderRow[] = (neighbors?.neighbors ?? []).map((n) => ({
    rank: n.rank, playerId: n.player_id, name: n.player_name, value: n.war, isCurrent: n.is_current,
  }))

  return (
    <PageLayout>
      <div className="player-profile">
        {/* Player Header */}
        {loadingDetail ? (
          <div className="player-profile__header">
            <SkeletonLoader width={150} height={150} borderRadius="50%" />
            <div style={{ flex: 1 }}>
              <SkeletonLoader width={200} height={32} />
              <div style={{ marginTop: 8 }}>
                <SkeletonLoader width={150} height={20} />
              </div>
            </div>
          </div>
        ) : errorDetail ? (
          <div className="player-profile__error">{errorDetail}</div>
        ) : playerDetail ? (
          <div className="player-hd-row">
            <IdentityHeader
              teamColors={{ home: teamColor }}
              leftContent={
                <div className="player-hd">
                  <PlayerAvatar id={playerDetail.player_id} team={playerDetail.team_abbrev}
                    name={playerDetail.player_name} size={200} showTeamLogo={false} />
                  <div className="player-hd__id">
                    <h1 className="player-hd__name">{playerDetail.player_name}</h1>
                    <div className="player-hd__context">
                      <span className="player-hd__team" onClick={(e) => handleTeamClick(e, playerDetail.team_id)}>
                        {playerDetail.team_abbrev}
                      </span>
                      <span className="player-hd__sep">·</span>
                      <span>{playerDetail.position}</span>
                      {preview?.age != null && (<><span className="player-hd__sep">·</span><span>Age: {preview.age}</span></>)}
                      {preview?.shoots && (<><span className="player-hd__sep">·</span><span>Shoots: {preview.shoots}</span></>)}
                    </div>
                    <hr className="player-hd__divider" />
                    <div className="player-hd__headline">
                      {headerWar != null && (
                        <span className="player-hd__stat">
                          <b className="mono">{(headerWar >= 0 ? '+' : '') + headerWar.toFixed(1)}</b> WAR
                          {overallPct != null && (
                            <span className="player-hd__statnote">{ordinal(Math.round(overallPct * 100))} pctile</span>
                          )}
                        </span>
                      )}
                      {/* Skaters: real all-situations TOI/GP (now sourced from shift charts).
                          Goalies: GP (a goalie's whole-game TOI is not a useful headline). */}
                      {!isGoalie && playerDetail.toi_per_gp != null && (
                        <span className="player-hd__stat">
                          <b className="mono">{formatTOI(playerDetail.toi_per_gp)}</b> TOI/GP
                        </span>
                      )}
                      {isGoalie && (goalieSeason?.games_played ?? playerDetail.games_played) != null && (
                        <span className="player-hd__stat">
                          <b className="mono">{goalieSeason?.games_played ?? playerDetail.games_played}</b> GP
                        </span>
                      )}
                    </div>
                    {identity && <p className="player-hd__identity">{identity}</p>}
                  </div>
                </div>
              }
            />
            {ladderRows.length > 0 && neighbors && (
              <PlayerValueLadder label={neighbors.scope_label} rows={ladderRows} />
            )}
          </div>
        ) : null}

        {/* Tabbed content (mirrors the Team detail page): pill tabs sticky below the header,
            URL-addressable via ?tab=, Overview default. One tab renders at a time and data is
            fetched once per player, so switching tabs never refetches already-loaded data. */}
        {playerDetail && (
          <div className="player-tabs-card">
            <div className="player-tabs-card__nav">
              <Tabs
                options={PLAYER_TABS.map((t) => ({ value: t.value, label: t.label }))}
                value={currentTab}
                onChange={handleTabChange}
              />
            </div>
            <div className="player-tabs-card__body">

              {/* ============================ OVERVIEW ============================ */}
              {currentTab === 'overview' && (
                <div className="player-ov">
                  {/* 1. Skills radar hero. Right column carries the archetype labels AND a concrete
                      standout readout (top 3 / bottom 2 spokes) so the card has no dead space. */}
                  {(radar || goalieRadar) ? (
                    <div className="player-profile__radar">
                      <div className="player-profile__radar-chart">
                        <SkillRadar
                          spokes={(radar ?? goalieRadar)!.spokes}
                          baseline={(radar ?? goalieRadar)!.baseline}
                        />
                        <p className="player-ov__radar-key">
                          Each spoke is a percentile within {POS_WORD[isGoalie ? 'G' : (playerDetail.position === 'D' ? 'D' : 'F')]}.
                          Tags mark each spoke as a measured <strong>skill</strong>, a <strong>usage</strong> (how he is
                          deployed), a <strong>style</strong> trait, or a derived <strong>proxy</strong>.
                        </p>
                      </div>
                      <div className="player-profile__radar-labels">
                        {radar && (() => {
                          const labels = playerLabelsFromRadar(radar)   // single source for player labels (B6)
                          return (
                            <>
                              {labels.overall && (
                                <div className="player-profile__radar-overall">{labels.overall}</div>
                              )}
                              <div className="player-profile__radar-chips">
                                {labels.offensive && (
                                  <Link to={`/learn/archetypes?type=${encodeURIComponent(labels.offensive)}`}
                                    className="player-profile__radar-chip" title={`What is a ${labels.offensive}?`}>
                                    {labels.offensive}
                                  </Link>
                                )}
                                {labels.defensive && (
                                  <Link to={`/learn/archetypes?type=${encodeURIComponent(labels.defensive)}`}
                                    className="player-profile__radar-chip player-profile__radar-chip--def"
                                    title={`What is a ${labels.defensive}?`}>
                                    {labels.defensive}
                                  </Link>
                                )}
                              </div>
                              {labels.descriptor && (
                                <p className="player-profile__radar-descriptor">{labels.descriptor}</p>
                              )}
                            </>
                          )
                        })()}
                        {/* standout readout: top 3 + bottom 2 spokes by percentile, with values */}
                        {(() => {
                          const so = standoutSpokes((radar ?? goalieRadar)!.spokes)
                          if (!so) return null
                          const row = (s: RadarSpoke, kind: 'top' | 'bottom') => (
                            <div className="player-ov__so-row" key={s.key}>
                              <span className="player-ov__so-label">{s.label}</span>
                              <span className={`player-ov__so-val player-ov__so-val--${kind} mono`}>
                                {Math.round(s.percentile as number)}
                              </span>
                            </div>
                          )
                          return (
                            <div className="player-ov__standout">
                              <div className="player-ov__so-group">
                                <span className="player-ov__so-head">Strengths</span>
                                {so.top.map((s) => row(s, 'top'))}
                              </div>
                              {so.bottom.length > 0 && (
                                <div className="player-ov__so-group">
                                  <span className="player-ov__so-head">Weaknesses</span>
                                  {so.bottom.map((s) => row(s, 'bottom'))}
                                </div>
                              )}
                            </div>
                          )
                        })()}
                      </div>
                    </div>
                  ) : (
                    <div className="player-profile__empty">No skills radar available for this player.</div>
                  )}

                  {/* 2 + 3 paired on the grid: Overall build block (left) and the rate-stat snapshot
                      (right, 2x3) read as one composed unit rather than two stacked full-width bands.
                      Snapshot values read off the REAL all-situations TOI denominator. */}
                  {!isGoalie ? (
                    <div className="player-ov__pair">
                      {playerDetail.value?.overall && (
                        <div className="player-ov__overall">
                          <OverallSummary overall={playerDetail.value.overall} read={playerDetail.value.read} />
                        </div>
                      )}
                      <div className="player-ov__snapshot">
                        {([
                          { label: 'TOI/GP', value: formatTOI(playerDetail.toi_per_gp), tip: 'Time on ice per game, all situations', rank: playerDetail.toi_rank },
                          { label: 'Points/60', value: playerDetail.points_per60.toFixed(2), tip: 'Points per 60 minutes', rank: playerDetail.points_per60_rank },
                          { label: 'Goals/60', value: playerDetail.goals_per60.toFixed(2), tip: 'Goals per 60 minutes', rank: playerDetail.goals_per60_rank },
                          { label: 'Assists/60', value: playerDetail.assists_per60.toFixed(2), tip: 'Primary assists per 60 minutes', rank: playerDetail.assists_per60_rank },
                          { label: 'CF%', value: `${(playerDetail.cf_pct * 100).toFixed(1)}%`, tip: 'On-ice shot-attempt share (Corsi for)', rank: playerDetail.cf_pct_rank },
                          { label: 'HDCF/60', value: playerDetail.hdcf_per60.toFixed(2), tip: 'Individual high-danger chances (ixG) per 60', rank: playerDetail.hdcf_per60_rank },
                        ] as { label: string; value: string; tip: string; rank?: number | null }[]).map((c) => {
                          const ri = rankInfo(c.rank, playerDetail.rank_pool)
                          return (
                            <StatCard key={c.label} label={c.label} value={c.value} tooltip={c.tip}
                              rankText={ri?.text} rankTier={ri?.tier} />
                          )
                        })}
                      </div>
                    </div>
                  ) : (
                    goalieSeason?.overall && <OverallSummary overall={goalieSeason.overall} />
                  )}
                </div>
              )}

              {/* ======================= IMPACT & VALUE ======================= */}
              {currentTab === 'impact' && (
                <div className="player-tab">
                  {/* Impact (RAPM) vs Value (GAR) — the two scalar verdicts (Phase 6 GAR) */}
                  {!isGoalie && playerDetail.value && (
                    <ImpactValuePanel value={playerDetail.value} name={playerDetail.player_name} />
                  )}

                  {/* Goalie value (GAR/WAR, cross-position scale) */}
                  {isGoalie && goalieSeason?.value && (() => {
                    const gv = goalieSeason.value!
                    const segs: StackSegment[] = GOALIE_VALUE_COMPONENTS.map((c) => ({
                      key: c.key, label: c.label,
                      value: gv.components.find((x) => x.key === c.key)?.value ?? 0, color: c.color,
                    }))
                    const posSum = segs.filter((s) => s.value > 0).reduce((a, s) => a + s.value, 0)
                    const negSum = segs.filter((s) => s.value < 0).reduce((a, s) => a + s.value, 0)
                    const d = Math.max(2, posSum, Math.abs(negSum))
                    return (
                      <div className="player-profile__composite">
                        <div className="player-profile__composite-head">
                          <span className="player-profile__composite-title">Goalie value (goals saved above a backup)</span>
                          <span className="player-profile__composite-total">
                            {(gv.war >= 0 ? '+' : '') + gv.war.toFixed(1)}
                            <span className="player-profile__composite-sd"> ± {gv.war_sd.toFixed(1)}</span> WAR
                          </span>
                        </div>
                        <ComponentStackBar segments={segs} total={gv.gar} domain={[-d, d]} se={gv.gar_sd ?? undefined} height={26} />
                        <div className="player-profile__composite-legend">
                          {GOALIE_VALUE_COMPONENTS.map((c) => (
                            <span key={c.key} className="player-profile__composite-legitem">
                              <span className="player-profile__composite-swatch" style={{ background: c.color }} />{c.label}
                            </span>
                          ))}
                        </div>
                        <p className="ovr__note" style={{ marginTop: 'var(--space-3)' }}>
                          On the same goals-per-win scale as skater WAR, so the two share one cross-position
                          leaderboard. Goaltending is low-signal year to year, so this estimate is regressed
                          toward the mean by its measured reliability
                          {gv.raw_war != null && <> (raw, pre-regression: {(gv.raw_war >= 0 ? '+' : '') + gv.raw_war.toFixed(1)} WAR)</>}
                          ; the band stays wide.
                        </p>
                      </div>
                    )
                  })()}

                  {/* Composite total-value stack (Phase 4.2) */}
                  {playerDetail.composite_components && playerDetail.composite_components.length > 0 && (() => {
                    const segs: StackSegment[] = COMPOSITE_COMPONENTS.map((c) => ({
                      key: c.key, label: c.label,
                      value: playerDetail.composite_components!.find((x) => x.key === c.key)?.value ?? 0,
                      color: c.color,
                    }))
                    const posSum = segs.filter((s) => s.value > 0).reduce((a, s) => a + s.value, 0)
                    const negSum = segs.filter((s) => s.value < 0).reduce((a, s) => a + s.value, 0)
                    const d = Math.max(2, posSum, Math.abs(negSum))
                    return (
                      <div className="player-profile__composite">
                        <div className="player-profile__composite-head">
                          <span className="player-profile__composite-title">Total value</span>
                          <span className="player-profile__composite-total">
                            {((playerDetail.composite_total ?? 0) >= 0 ? '+' : '') + (playerDetail.composite_total ?? 0).toFixed(1)}
                            {playerDetail.composite_total_sd != null && (
                              <span className="player-profile__composite-sd"> ± {playerDetail.composite_total_sd.toFixed(1)}</span>
                            )} goals
                          </span>
                        </div>
                        <ComponentStackBar segments={segs} total={playerDetail.composite_total ?? 0}
                          domain={[-d, d]} se={playerDetail.composite_total_sd} height={26} />
                        <div className="player-profile__composite-legend">
                          {COMPOSITE_COMPONENTS.map((c) => (
                            <span key={c.key} className="player-profile__composite-legitem">
                              <span className="player-profile__composite-swatch" style={{ background: c.color }} />{c.label}
                            </span>
                          ))}
                        </div>
                      </div>
                    )
                  })()}

                  {/* Reconciliation cards: clutch + coach trust (consistency strip lives under Trends) */}
                  {reconciliation && (reconciliation.clutch || reconciliation.coach_trust) && (
                    <div className="player-profile__section">
                      <h2 className="player-profile__section-title">Reconciliation</h2>
                      <div className="reconciliation">
                        {reconciliation.clutch && (
                          <div className="reconciliation__panel">
                            <div className="reconciliation__panel-title">Clutch (leverage-weighted)</div>
                            <div className="reconciliation__big">
                              {(reconciliation.clutch.clutch_delta >= 0 ? '+' : '') + reconciliation.clutch.clutch_delta.toFixed(2)} xG
                            </div>
                            <p className="reconciliation__note">
                              In the highest-leverage moments he produces {reconciliation.clutch.clutch_delta >= 0 ? 'more' : 'less'} than
                              his overall rate, {reconciliation.clutch.confidence}.
                            </p>
                            <div className="reconciliation__sub">
                              raw {reconciliation.clutch.raw_ixg.toFixed(1)} to weighted {reconciliation.clutch.clutch_ixg.toFixed(1)} xG
                              · {reconciliation.clutch.n_shots} shots
                            </div>
                          </div>
                        )}
                        {reconciliation.coach_trust && (
                          <div className="reconciliation__panel">
                            <div className="reconciliation__panel-title">Coach trust (deployment)</div>
                            <div className="reconciliation__big">
                              {(reconciliation.coach_trust.trust_score >= 0 ? '+' : '') + reconciliation.coach_trust.trust_score.toFixed(2)}
                            </div>
                            <p className="reconciliation__note">Deployment trust vs position average (z-score).</p>
                            <div className="reconciliation__sub">
                              PK {(reconciliation.coach_trust.pk_share * 100).toFixed(0)}% of TOI ·
                              road/home {reconciliation.coach_trust.road_home_ratio.toFixed(2)}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Clean empty state when no value/reconciliation data exists */}
                  {!playerDetail.value
                    && !(isGoalie && goalieSeason?.value)
                    && !(playerDetail.composite_components && playerDetail.composite_components.length > 0)
                    && !(reconciliation && (reconciliation.clutch || reconciliation.coach_trust)) && (
                    <div className="player-profile__empty">No impact or value data available for this player.</div>
                  )}
                </div>
              )}

              {/* ============================ TRENDS ============================ */}
              {currentTab === 'trends' && (
                <div className="player-tab">
                  {/* Performance trends */}
                  {!isGoalie && (
                    <div className="player-profile__section">
                      <h2 className="player-profile__section-title">Performance Trends</h2>
                      {loadingTrends ? (
                        <SkeletonLoader height={300} />
                      ) : playerTrends && playerTrends.points_per60_5gp.length > 0 ? (
                        <div className="player-profile__chart">
                          <ResponsiveContainer width="100%" height={300}>
                            <LineChart data={playerTrends.points_per60_5gp.map(point => ({
                              date: formatDate(point.game_date),
                              fullDate: point.game_date,
                              value: point.value
                            }))}>
                              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.3} />
                              <XAxis dataKey="date" stroke="var(--color-text-muted)" style={{ fontSize: 'var(--text-xs)' }} />
                              <YAxis stroke="var(--color-text-muted)" style={{ fontSize: 'var(--text-xs)' }} />
                              <RechartsTooltip
                                contentStyle={{
                                  backgroundColor: 'var(--color-bg-elevated)',
                                  border: '1px solid var(--color-border)',
                                  borderRadius: 'var(--radius-sm)',
                                  fontSize: 'var(--text-sm)'
                                }}
                                labelStyle={{ color: 'var(--color-text-secondary)' }}
                              />
                              <Line type="monotone" dataKey="value" stroke={teamColor} strokeWidth={2}
                                dot={{ fill: teamColor, r: 3 }} activeDot={{ r: 5 }} name="Points/60 (5-game rolling)" />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      ) : (
                        <div className="player-profile__empty">No trend data available.</div>
                      )}
                    </div>
                  )}

                  {/* Consistency strip (game scores) */}
                  {reconciliation?.consistency && (
                    <div className="player-profile__section">
                      <h2 className="player-profile__section-title">Consistency</h2>
                      <div className="reconciliation__consistency">
                        <div className="reconciliation__panel-title">
                          Index {ordinal(reconciliation.consistency.consistency_index * 100)} pctile ·
                          good games {(reconciliation.consistency.good_game_share * 100).toFixed(0)}% ·
                          no-shows {(reconciliation.consistency.no_show_share * 100).toFixed(0)}%
                        </div>
                        <StripPlot
                          values={reconciliation.consistency.game_scores.map((g) => g.game_score)}
                          mean={reconciliation.consistency.mean_gs}
                          color={teamColor}
                        />
                        <div className="reconciliation__sub">Each dot is one game's game score; the line is the season mean.</div>
                      </div>
                    </div>
                  )}

                  {/* Career trajectory (aging curve + twins + physical overlay) */}
                  {trajectory && (trajectory.curve.length > 0 || trajectory.twins.length > 0) && (() => {
                    const byAge = new Map<number, { age: number; curve?: number; player?: number }>()
                    for (const c of trajectory.curve) byAge.set(c.age, { age: c.age, curve: c.curve_value })
                    for (const pt of trajectory.path) {
                      const e = byAge.get(pt.age) ?? { age: pt.age }
                      e.player = pt.points82; byAge.set(pt.age, e)
                    }
                    const data = Array.from(byAge.values()).sort((a, b) => a.age - b.age)
                    return (
                      <div className="player-profile__section">
                        <h2 className="player-profile__section-title">Career Trajectory</h2>
                        {trajectory.curve.length > 0 && (
                          <>
                            <p className="trajectory__cap">
                              Points/82 by age vs the {trajectory.curve_label} aging curve
                              {trajectory.curve_label !== trajectory.archetype && trajectory.archetype
                                ? ` (position fallback, ${trajectory.archetype} has too little pre-tracking history)` : ''}.
                            </p>
                            <div className="player-profile__chart">
                              <ResponsiveContainer width="100%" height={280}>
                                <LineChart data={data}>
                                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                                  <XAxis dataKey="age" tick={{ fontSize: 12 }} />
                                  <YAxis tick={{ fontSize: 12 }} />
                                  <RechartsTooltip />
                                  <Line type="monotone" dataKey="curve" name="Archetype curve" stroke="#94a3b8"
                                    strokeDasharray="5 4" dot={false} connectNulls />
                                  <Line type="monotone" dataKey="player" name="This player" stroke={teamColor}
                                    strokeWidth={2} connectNulls />
                                </LineChart>
                              </ResponsiveContainer>
                            </div>
                          </>
                        )}
                        {trajectory.twins.length > 0 && (
                          <div className="trajectory__twins">
                            <div className="trajectory__sub">
                              Career twins through age {trajectory.twins[0].through_age} (most similar paths)
                            </div>
                            {trajectory.twins.map((t) => (
                              <div key={t.twin_id} className="trajectory__twin">
                                <span className="trajectory__twin-name">{t.twin_name ?? t.twin_id}</span>
                                <span className="trajectory__twin-sim">{(t.similarity * 100).toFixed(0)}% match</span>
                                {t.reduced_features && <span className="trajectory__tag">pre-tracking comparable</span>}
                                {t.next3_points82 != null && (
                                  <span className="trajectory__twin-out">{t.next3_points82.toFixed(0)} pts/82 next 3 yrs</span>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                        {trajectory.physical.length > 0 && (
                          <p className="trajectory__sub">
                            Skating: bursts/60 {trajectory.physical.map((p) => (p.burst_rate ?? 0).toFixed(1)).join(' to ')}
                            {!trajectory.burst_flag_enabled && ' (burst-decline early-warning not shown; it did not predict production decline in our data)'}
                          </p>
                        )}
                      </div>
                    )
                  })()}

                  {/* Clean empty state when there is nothing trend-like to show */}
                  {!(!isGoalie && playerTrends && playerTrends.points_per60_5gp.length > 0)
                    && !loadingTrends
                    && !reconciliation?.consistency
                    && !(trajectory && (trajectory.curve.length > 0 || trajectory.twins.length > 0)) && (
                    <div className="player-profile__empty">No trend data available for this player.</div>
                  )}
                </div>
              )}

              {/* =========================== GAME LOG =========================== */}
              {currentTab === 'gamelog' && (
                <div className="player-tab">
                  {/* vs Opponent selector */}
                  <div className="player-profile__section">
                    <h2 className="player-profile__section-title">vs Opponent</h2>
                    <div className="player-profile__vs-opponent">
                      <select
                        className="player-profile__opponent-select"
                        value={selectedOpponent || ''}
                        onChange={(e) => setSelectedOpponent(e.target.value ? parseInt(e.target.value) : null)}
                      >
                        <option value="">Select opponent...</option>
                        {NHL_TEAMS.filter(team => team.id !== playerDetail?.team_id)
                          .sort((a, b) => a.name.localeCompare(b.name))
                          .map(team => (
                            <option key={team.id} value={team.id}>{team.name}</option>
                          ))}
                      </select>

                      {selectedOpponent && (
                        <>
                          {loadingVsOpponent ? (
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
                              <SkeletonLoader height={80} />
                              <SkeletonLoader height={80} />
                              <SkeletonLoader height={80} />
                            </div>
                          ) : errorVsOpponent ? (
                            <div className="player-profile__empty">No matchup data available.</div>
                          ) : vsOpponentData ? (
                            <>
                              {vsOpponentData.small_sample && (
                                <div style={{ marginTop: 'var(--space-3)' }}>
                                  <Badge variant="small-sample" />
                                </div>
                              )}
                              <div className="player-profile__vs-stats">
                                <StatCard label="Games Played" value={vsOpponentData.games_played} />
                                {vsOpponentData.toi_per_gp !== null && (
                                  <StatCard label="TOI/GP" value={formatTOI(vsOpponentData.toi_per_gp)} />
                                )}
                                {vsOpponentData.points_per60 !== null && (
                                  <StatCard label="Points/60" value={vsOpponentData.points_per60.toFixed(2)} />
                                )}
                                {vsOpponentData.cf_pct !== null && (
                                  <StatCard label="CF%" value={`${(vsOpponentData.cf_pct * 100).toFixed(1)}%`} />
                                )}
                              </div>
                            </>
                          ) : null}
                        </>
                      )}
                    </div>
                  </div>

                  {/* Game Log table (last 20 games) */}
                  <div className="player-profile__section">
                    <h2 className="player-profile__section-title">Game Log (Last 20 Games)</h2>
                    {loadingGamelog ? (
                      <SkeletonLoader height={400} />
                    ) : playerGamelog && playerGamelog.games.length > 0 ? (
                      <div className="player-profile__table-container">
                        <table className="player-profile__table">
                          <thead>
                            <tr>
                              <th onClick={() => handleSort('game_date')}>
                                Date {sortColumn === 'game_date' && (sortDirection === 'asc' ? '↑' : '↓')}
                              </th>
                              <th>Opponent</th>
                              <th onClick={() => handleSort('toi')}>
                                TOI {sortColumn === 'toi' && (sortDirection === 'asc' ? '↑' : '↓')}
                              </th>
                              <th onClick={() => handleSort('goals')}>
                                G {sortColumn === 'goals' && (sortDirection === 'asc' ? '↑' : '↓')}
                              </th>
                              <th onClick={() => handleSort('assists')}>
                                A {sortColumn === 'assists' && (sortDirection === 'asc' ? '↑' : '↓')}
                              </th>
                              <th onClick={() => handleSort('points')}>
                                P {sortColumn === 'points' && (sortDirection === 'asc' ? '↑' : '↓')}
                              </th>
                              <th onClick={() => handleSort('shots')}>
                                SOG {sortColumn === 'shots' && (sortDirection === 'asc' ? '↑' : '↓')}
                              </th>
                              <th onClick={() => handleSort('cf')}>
                                CF {sortColumn === 'cf' && (sortDirection === 'asc' ? '↑' : '↓')}
                              </th>
                              <th onClick={() => handleSort('hdcf')}>
                                HDCF {sortColumn === 'hdcf' && (sortDirection === 'asc' ? '↑' : '↓')}
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {sortedGamelog.map((game) => (
                              <tr key={game.game_id} className="player-profile__table-row"
                                onClick={() => handleGameClick(game.game_id)}>
                                <td>{formatDate(game.game_date)}</td>
                                <td className="player-profile__opponent-cell">vs {game.opponent_abbrev}</td>
                                <td className="mono">{formatTOI(game.toi)}</td>
                                <td className="mono">{game.goals}</td>
                                <td className="mono">{game.assists}</td>
                                <td className="mono">{game.points}</td>
                                <td className="mono">{game.shots}</td>
                                <td className="mono">{game.cf}</td>
                                <td className="mono">{game.hdcf}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="player-profile__empty">No games played this season.</div>
                    )}
                  </div>
                </div>
              )}

              {/* =========================== SHOT MAP =========================== */}
              {currentTab === 'shotmap' && (
                <div className="player-tab">
                  <div className="player-profile__section">
                    <h2 className="player-profile__section-title">Shot Locations</h2>
                    {isGoalie ? (
                      <div className="player-profile__empty">Shot map is available for skaters.</div>
                    ) : loadingShots ? (
                      <SkeletonLoader height={400} />
                    ) : playerShots && playerShots.shot_locations.length > 0 ? (
                      <ShotMap
                        mode="player"
                        playerShots={playerShots.shot_locations.map(shot => ({
                          x: shot.x,
                          y: shot.y,
                          outcome: shot.is_goal ? 'goal' : 'shot_on_goal',
                          situation: '1551',
                          team_id: playerDetail?.team_id || 0
                        }))}
                        playerTeamColor={teamColor}
                        playerName={playerDetail?.player_name || ''}
                      />
                    ) : (
                      <div className="player-profile__empty">No shot data available.</div>
                    )}
                  </div>
                </div>
              )}

            </div>
          </div>
        )}
      </div>
    </PageLayout>
  )
}

export default PlayerProfile
