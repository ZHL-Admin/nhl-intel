import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts'
import { PageLayout, StatCard, Badge, SkeletonLoader, ComponentStackBar, ImpactValuePanel, IdentityHeader, PlayerAvatar, PlayerValueLadder, Tabs, Select } from '../components/common'
import type { StackSegment, PlayerValueLadderRow } from '../components/common'
import { COMPOSITE_COMPONENTS, GOALIE_VALUE_COMPONENTS } from '../config/metrics'
import ShotMap from '../components/visualizations/ShotMap'
import StripPlot from '../components/visualizations/StripPlot'
import SkillRadar from '../components/visualizations/SkillRadar'
import PlayerDraftLine from '../components/players/PlayerDraftLine'
import { Target, Activity, ArrowRight } from 'lucide-react'
import { familyRadar } from '../utils/radar'
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
  getPlayerValueNeighbors,
  getPlayerVerdict,
  getPlayerSituational,
  getPlayerShotQuality
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
  RadarSpoke,
  PlayerVerdict,
  PlayerSituational,
  PlayerShotQuality
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

// Seasons with value/radar/composite data (newest first). Drives the header season toggle.
const SEASONS = ['2025-26', '2024-25', '2023-24', '2022-23', '2021-22']

const spokePct = (spokes: RadarSpoke[], key: string): number | null =>
  spokes.find((s) => s.key === key)?.percentile ?? null

/** Special-teams role from a usage spoke percentile (heavy / some / light). */
const stRole = (p: number | null): string | null => (p == null ? null : p >= 66 ? 'heavy' : p >= 33 ? 'some' : 'light')

/** Usage descriptor from zone-start LEAN + PP/PK roles. Lean comes from the Edge OZ-start league
 *  percentile (preferred, league-relative) or the OZ-minus-DZ gap in points. Never a flat "above 50"
 *  test, since Edge includes neutral-zone starts in the denominator so the even point is not 50%. */
function usageDescriptor(ozPctile: number | null, ozGap: number | null, pp: string | null, pk: string | null): string | null {
  const parts: string[] = []
  if (ozPctile != null) {
    parts.push(ozPctile >= 0.66 ? 'offense-first deployment' : ozPctile <= 0.33 ? 'defensive-zone deployment' : 'balanced zone starts')
  } else if (ozGap != null) {
    parts.push(ozGap >= 10 ? 'offense-first deployment' : ozGap <= -10 ? 'defensive-zone deployment' : 'balanced zone starts')
  }
  if (pk === 'heavy') parts.push('penalty-kill role')
  else if (pp === 'heavy' && !parts.length) parts.push('power-play role')
  return parts.length ? parts.join(' · ') : null
}

/** Short usage lean for the Role-row USAGE cell ("Offense-first" / "Defensive" / "Balanced").
 *  Same Edge OZ-start source as usageDescriptor, so the chip and the cell never contradict. */
function usageLeanShort(ozPctile: number | null, ozGap: number | null): string | null {
  if (ozPctile != null) return ozPctile >= 0.66 ? 'Offense-first' : ozPctile <= 0.33 ? 'Defensive' : 'Balanced'
  if (ozGap != null) return ozGap >= 10 ? 'Offense-first' : ozGap <= -10 ? 'Defensive' : 'Balanced'
  return null
}

/** percentile (0-100) -> tier color token. Single source for production ranks, bars, strengths. */
const tierColorVar = (p: number): string => (p >= 66 ? 'var(--color-success)' : p >= 33 ? 'var(--color-warning)' : 'var(--color-danger)')
const tierBgVar = (p: number): string => (p >= 66 ? 'var(--color-success-bg)' : p >= 33 ? 'var(--color-warning-bg)' : 'var(--color-danger-bg)')
/** league rank -> percentile (round((1 - rank/pool)*100)); single tier function for the rank pills. */
const pctileFromRank = (rank?: number | null, pool?: number | null): number | null =>
  (rank != null && pool && pool > 0 ? Math.round((1 - rank / pool) * 100) : null)

type Signal = { title: React.ReactNode; explanation: string; tone: 'good' | 'caution' | 'neutral'; icon: 'finishing' | 'floor' }
/** Is-it-real signal: finishing vs expected shooting (the sharper player-level luck signal). */
function finishingSignal(actual?: number | null, expected?: number | null): Signal | null {
  if (actual == null || expected == null) return null
  const d = actual - expected
  const pts = Math.abs(d) * 100
  if (pts < 1) return {
    title: 'Finishing is real',
    explanation: 'Goals are tracking expected scoring chances, so the production is earned, not luck.',
    tone: 'neutral', icon: 'finishing' }
  return d < 0
    ? { title: 'Finishing should climb', explanation: `Goals trail the chances by ${pts.toFixed(0)}%; expect positive regression.`, tone: 'good', icon: 'finishing' }
    : { title: 'Finishing may cool', explanation: `Goals exceed the chances by ${pts.toFixed(0)}%; some regression is likely.`, tone: 'caution', icon: 'finishing' }
}
/** Is-it-real signal: game-to-game floor from the consistency index (0..1 within position). */
function floorSignal(idx?: number | null): Signal | null {
  if (idx == null) return null
  const p = Math.round(idx * 100)
  const pct = <span className="player-ov__sig-pct mono">{ordinal(p)}</span>
  if (idx >= 0.66) return { title: <>High, steady floor {pct}</>, explanation: 'Rarely has a quiet night; reliable game to game.', tone: 'good', icon: 'floor' }
  if (idx <= 0.33) return { title: <>Streaky floor {pct}</>, explanation: 'Production swings hard from game to game.', tone: 'caution', icon: 'floor' }
  return { title: <>Average floor {pct}</>, explanation: 'Middle-of-pack game-to-game consistency.', tone: 'neutral', icon: 'floor' }
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

  // Season toggle (header). Drives every season-scoped fetch on the page.
  const [season, setSeason] = useState<string>(SEASONS[0])

  // Data states
  const [playerDetail, setPlayerDetail] = useState<PlayerDetail | null>(null)
  const [radar, setRadar] = useState<PlayerRadar | null>(null)
  const [verdict, setVerdict] = useState<PlayerVerdict | null>(null)   // composed scouting read (B)
  const [situational, setSituational] = useState<PlayerSituational[] | null>(null)  // Impact tab breakdown
  const [shotQuality, setShotQuality] = useState<PlayerShotQuality | null>(null)    // Shot Map zone quality
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
        const data = await getPlayerDetail(parseInt(playerId), season)
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
  }, [playerId, season])

  // Skills radar (Part B): goalie vs skater radar based on detail position
  useEffect(() => {
    if (!playerId || !playerDetail) return
    let active = true
    setRadar(null); setGoalieRadar(null); setGoalieSeason(null); setVerdict(null)
    const pid = parseInt(playerId)
    if (playerDetail.position === 'G') {
      getGoalieRadar(pid, season).then(r => active && setGoalieRadar(r)).catch(() => {})
      // goalie value (GAR/WAR) + within-goalie Overall live on the goalie endpoint
      getGoalieSeason(pid, season).then(s => active && setGoalieSeason(s)).catch(() => {})
    } else {
      getPlayerRadar(pid, season).then(r => active && setRadar(r)).catch(() => {})
      // composed scouting read; null when not yet generated -> falls back to the radar descriptor
      getPlayerVerdict(pid, season).then(v => active && setVerdict(v)).catch(() => {})
      // situational breakdown (5v5/PP/PK/All) for the Impact & Value tab
      setSituational(null)
      getPlayerSituational(pid, season).then(s => active && setSituational(s)).catch(() => {})
      // shot-zone quality (by danger vs positional avg) for the Shot Map tab
      setShotQuality(null)
      getPlayerShotQuality(pid, season).then(q => active && setShotQuality(q)).catch(() => {})
    }
    return () => { active = false }
  }, [playerId, playerDetail, season])

  // Light bio (age, handedness) for the header, and the position-scoped total-value slice that
  // powers the header ranking module. Both degrade silently (header omits the piece if absent).
  useEffect(() => {
    if (!playerId) return
    let active = true
    setPreview(null); setNeighbors(null)
    const pid = parseInt(playerId)
    getPlayerPreview(pid, season).then((d) => active && setPreview(d)).catch(() => {})
    getPlayerValueNeighbors(pid, season).then((d) => active && setNeighbors(d)).catch(() => {})
    return () => { active = false }
  }, [playerId, season])

  // Fetch eye-test reconciliation (clutch + consistency + coach trust) — Phase 4.3
  useEffect(() => {
    if (!playerId) return
    let active = true
    setReconciliation(null)
    getPlayerReconciliation(parseInt(playerId), season)
      .then((d) => active && setReconciliation(d))
      .catch(() => { /* reconciliation is optional (e.g. low-minute or pre-2015) */ })
    return () => { active = false }
  }, [playerId, season])

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

  // ---- Shared deployment derivation: ONE source for the header usage chip and the Role-row cells,
  // so the chip can never contradict the Role row (must-fix 2). Durable archetype (must-fix 1) is the
  // modal-3yr label from the backend, matching the verdict.
  const rspokesTop = (radar ?? goalieRadar)?.spokes ?? []
  const ppRoleTop = stRole(spokePct(rspokesTop, 'pp_value'))
  const pkRoleTop = stRole(spokePct(rspokesTop, 'pk_role'))
  const edgeOzTop = playerDetail?.edge_oz_start_pct ?? null
  const edgeOzPTop = playerDetail?.edge_oz_start_pctile ?? null
  const ozGapTop = (edgeOzTop != null && playerDetail?.edge_dz_start_pct != null)
    ? (edgeOzTop - playerDetail.edge_dz_start_pct) * 100 : null
  const usageDesc = !isGoalie ? usageDescriptor(edgeOzPTop, ozGapTop, ppRoleTop, pkRoleTop) : null
  const usageShort = !isGoalie ? usageLeanShort(edgeOzPTop, ozGapTop) : null
  const durableArch = !isGoalie ? (playerDetail?.durable_archetype ?? null) : null
  // WAR chip tier from the within-position overall percentile.
  const warPct = overallPct != null ? Math.round(overallPct * 100) : null

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
                    {/* Chip row: WAR (filled, tier-tinted, percentile caption inside), then durable
                        archetype + usage descriptor as outline chips (one source as the Role row). */}
                    <div className="player-hd__chips">
                      {headerWar != null && (
                        <span className="player-hd__warchip"
                          style={warPct != null ? { color: tierColorVar(warPct), background: 'var(--color-bg-elevated)' } : undefined}>
                          <span className="player-hd__warchip-val mono">{(headerWar >= 0 ? '+' : '') + headerWar.toFixed(1)} WAR</span>
                          {warPct != null && <span className="player-hd__warchip-pct">p{warPct}</span>}
                        </span>
                      )}
                      {durableArch && (
                        <Link to={`/learn/archetypes?type=${encodeURIComponent(durableArch)}`}
                          className="player-hd__chip" title={`What is a ${durableArch}?`}>{durableArch}</Link>
                      )}
                      {usageDesc && <span className="player-hd__chip player-hd__chip--plain">{usageDesc}</span>}
                      {isGoalie && (goalieSeason?.games_played ?? playerDetail.games_played) != null && (
                        <span className="player-hd__chip player-hd__chip--plain">
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
              {/* Season selector lives here (far right of the tab row), not in the header. */}
              <span className="player-tabs-card__season">
                <Select value={season} ariaLabel="Season"
                  options={SEASONS.map((s) => ({ value: s, label: s }))} onChange={setSeason} />
              </span>
            </div>
            <div className="player-tabs-card__body">

              {/* ============================ OVERVIEW ============================ */}
              {currentTab === 'overview' && (() => {
                const rspokes = (radar ?? goalieRadar)?.spokes ?? []
                const fr = familyRadar(rspokes)
                const so = standoutSpokes(rspokes)
                const ppRole = stRole(spokePct(rspokes, 'pp_value'))
                const pkRole = stRole(spokePct(rspokes, 'pk_role'))
                // OZ start: prefer the per-player NHL Edge figure (official, all situations, neutral
                // included); fall back to the team faceoff proxy, labeled. Lean off the Edge OZ-start
                // percentile / OZ-minus-DZ gap, never a 50% threshold.
                const edgeOz = playerDetail.edge_oz_start_pct ?? null
                const edgeOzP = playerDetail.edge_oz_start_pctile ?? null
                const ozSource = edgeOz != null ? 'NHL Edge' : 'team proxy'
                const signals = [
                  finishingSignal(playerDetail.actual_shooting_pct, playerDetail.expected_shooting_pct),
                  floorSignal(reconciliation?.consistency?.consistency_index),
                ].filter(Boolean) as Signal[]
                const ovOverall = isGoalie ? goalieSeason?.overall : playerDetail.value?.overall
                const ovPct = ovOverall?.overall_percentile
                const posWord = isGoalie ? 'goalies' : playerDetail.position === 'D' ? 'defensemen' : 'forwards'
                // The composed scouting read (B) when generated; otherwise the archetype descriptor.
                const verdictProse = verdict?.long
                  ?? (!isGoalie && radar ? playerLabelsFromRadar(radar).descriptor : null)
                const stat = (k: string) => preview?.stats?.find((s) => s.key === k)?.value
                const pctileOf = (rank?: number | null, pool?: number | null) =>
                  (rank != null && pool && pool > 1 ? 1 - (rank - 1) / (pool - 1) : null)
                const ovN = ovPct != null ? Math.round(ovPct * 100) : null
                const suf = ovN == null ? '' : (ovN % 10 === 1 && ovN % 100 !== 11 ? 'st'
                  : ovN % 10 === 2 && ovN % 100 !== 12 ? 'nd'
                  : ovN % 10 === 3 && ovN % 100 !== 13 ? 'rd' : 'th')
                const SIG_ICON = { finishing: Target, floor: Activity }
                return (
                <div className="player-ov player-ov--stack">

                  {/* [2] Season totals: a labeled stat bar on a surface, each cell ranked league-wide */}
                  {(playerDetail.season_totals?.length ?? 0) > 0 && (() => {
                    const gp = playerDetail.games_played ?? goalieSeason?.games_played ?? (stat('gp') as number | undefined)
                    return (
                    <section className="player-ov__sec">
                      <div className="player-ov__totals-head">
                        <span className="player-ov__eyebrow">Season totals</span>
                        {gp != null && (
                          <span className="player-ov__totals-gp"><b className="mono">{gp}</b> games played</span>
                        )}
                        <span className="player-ov__totals-cap">rank among NHL {isGoalie ? 'goalies' : 'skaters'}</span>
                      </div>
                      <div className="player-ov__totals">
                        {playerDetail.season_totals!.map((t) => {
                          const p = pctileFromRank(t.rank, t.pool)
                          return (
                            <div className="player-ov__total" key={t.key}>
                              <div className="player-ov__total-label">{t.label}</div>
                              <div className="player-ov__total-row">
                                <span className="player-ov__total-val mono">{t.display}</span>
                                {t.rank != null && (
                                  <span className="player-ov__total-pill mono"
                                    style={p != null ? { color: tierColorVar(p), background: tierBgVar(p) } : undefined}>
                                    {ordinal(t.rank)}
                                  </span>
                                )}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </section>
                    )
                  })()}

                  {/* [3] HERO CARD: the verdict (left) and the shape (right) in one bordered card */}
                  {ovOverall && (
                    <div className="player-ov__hero">
                      {/* left: the read */}
                      <div className="player-ov__hero-left">
                        <div className="player-ov__eyebrow">The verdict</div>
                        <div className="player-ov__pctblock">
                          <span className="player-ov__pct mono">{ovN ?? '—'}<span className="player-ov__pct-suf">{suf}</span></span>
                          <span className="player-ov__pct-sub">overall percentile<br />among {posWord}</span>
                        </div>
                        <div className="player-ov__comp">
                          {ovOverall.components?.map((c) => {
                            const p = c.percentile != null ? Math.round(c.percentile * 100) : null
                            return (
                              <div key={c.key} className="player-ov__comp-row">
                                <div className="player-ov__comp-head"><span>{c.label}</span><span className="mono">{p ?? '—'}</span></div>
                                <div className="player-ov__bar" aria-hidden="true">
                                  {p != null && <span style={{ width: `${p}%`, background: 'var(--color-success)' }} />}
                                </div>
                              </div>
                            )
                          })}
                          {!isGoalie && playerDetail.value?.read && (
                            <span className={`player-ov__agree player-ov__agree--${playerDetail.value.read.case === 'aligned' ? 'ok' : 'warn'}`}>
                              {playerDetail.value.read.case === 'aligned' ? 'production and impact agree' : 'production and impact diverge'}
                            </span>
                          )}
                        </div>
                        {verdictProse
                          ? <p className="player-ov__hero-prose">{verdictProse}</p>
                          : <p className="player-ov__hero-prose player-ov__hero-prose--muted">Composed scouting read pending.</p>}
                        <button className="player-ov__hero-link" onClick={() => handleTabChange('impact')}>
                          Full impact breakdown <ArrowRight size={13} />
                        </button>
                      </div>
                      {/* right: the shape (stacked) */}
                      <div className="player-ov__hero-right">
                        <div className="player-ov__shape-title">
                          <span className="player-ov__eyebrow">Shape of game</span>
                          <span className="player-ov__shape-cap">percentile within {posWord}</span>
                        </div>
                        {rspokes.length > 0 && (
                          <div className="player-ov__shape-radar">
                            <SkillRadar spokes={fr.spokes} medianRing dimNonSkill hideLegend />
                          </div>
                        )}
                        {so && (
                          <div className="player-ov__readout">
                            <div className="player-ov__readout-col">
                              <div className="player-ov__readout-head">Strengths</div>
                              {so.top.map((s) => (
                                <div className="player-ov__readout-row" key={s.key}>
                                  <span className="player-ov__readout-name">{s.label}</span>
                                  <span className="player-ov__so-val player-ov__so-val--top mono">{Math.round(s.percentile as number)}</span>
                                </div>
                              ))}
                            </div>
                            {so.bottom.length > 0 && (
                              <div className="player-ov__readout-col player-ov__readout-col--r">
                                <div className="player-ov__readout-head">Watch-outs</div>
                                {so.bottom.map((s) => (
                                  <div className="player-ov__readout-row" key={s.key}>
                                    <span className="player-ov__readout-name">{s.label}</span>
                                    <span className="player-ov__so-val player-ov__so-val--bottom mono">{Math.round(s.percentile as number)}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* [4] Is it real?: a panel of substantive signal cards (hide when unbacked) */}
                  {signals.length > 0 && (
                    <section className="player-ov__sec">
                      <div className="player-ov__panel-head">
                        <span className="player-ov__eyebrow">Is it real?</span>
                        <button className="player-ov__vf-link" onClick={() => handleTabChange('trends')}>Season trends →</button>
                      </div>
                      <div className="player-ov__signals">
                        {signals.map((sig, i) => {
                          const Icon = SIG_ICON[sig.icon]
                          return (
                            <div key={i} className="player-ov__signal">
                              <span className={`player-ov__sig-badge player-ov__sig-badge--${sig.tone}`}><Icon size={16} /></span>
                              <div className="player-ov__sig-body">
                                <div className="player-ov__sig-title">{sig.title}</div>
                                <div className="player-ov__sig-exp">{sig.explanation}</div>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </section>
                  )}

                  {/* Draft value line (Handoff 5): renders nothing for undrafted players */}
                  {playerId && <PlayerDraftLine playerId={parseInt(playerId)} />}

                  {/* [5] Details row: Role & deployment (left) + Production rates (right) */}
                  {!isGoalie ? (
                    <div className="player-ov__details">
                      <section className="player-ov__sec player-ov__details-l">
                        <div className="player-ov__eyebrow">Role &amp; deployment</div>
                        <div className="player-ov__role">
                          {(playerDetail.edge_oz_start_pct != null || playerDetail.edge_dz_start_pct != null) && (() => {
                            const oz = (playerDetail.edge_oz_start_pct ?? 0) * 100
                            const nz = (playerDetail.edge_nz_start_pct ?? 0) * 100
                            const dz = (playerDetail.edge_dz_start_pct ?? 0) * 100
                            return (
                              <div className="player-ov__zone">
                                <div className="player-ov__zone-head">
                                  <span>Zone starts{edgeOzP != null ? ` · ${ordinal(Math.round(edgeOzP * 100))} pctile, ${ozSource}` : ''}</span>
                                  {usageShort && <span className="player-ov__zone-lean">{usageShort.toLowerCase()}</span>}
                                </div>
                                <div className="player-ov__zone-bar">
                                  <span className="player-ov__zone-seg player-ov__zone-seg--oz" style={{ width: `${oz}%` }} />
                                  <span className="player-ov__zone-seg player-ov__zone-seg--nz" style={{ width: `${nz}%` }} />
                                  <span className="player-ov__zone-seg player-ov__zone-seg--dz" style={{ width: `${dz}%` }} />
                                </div>
                                <div className="player-ov__zone-readouts">
                                  <span><b className="mono">{oz.toFixed(0)}%</b> OZ</span>
                                  <span><b className="mono">{nz.toFixed(0)}%</b> NZ</span>
                                  <span><b className="mono">{dz.toFixed(0)}%</b> DZ</span>
                                </div>
                              </div>
                            )
                          })()}
                          <div className="player-ov__role-cells">
                            {playerDetail.toi_per_gp != null && (() => {
                              const ri = rankInfo(playerDetail.toi_rank, playerDetail.rank_pool)
                              return (
                                <div className="player-ov__cell">
                                  <div className="player-ov__cell-label">TOI / GP</div>
                                  <div className="player-ov__cell-val mono">{formatTOI(playerDetail.toi_per_gp)}</div>
                                  {ri && <div className="player-ov__cell-cap">{ri.text}</div>}
                                </div>
                              )
                            })()}
                            <div className="player-ov__cell">
                              <div className="player-ov__cell-label">Power play</div>
                              <div className="player-ov__cell-val player-ov__cell-val--text">{ppRole ? ppRole[0].toUpperCase() + ppRole.slice(1) : '—'}</div>
                            </div>
                            <div className="player-ov__cell">
                              <div className="player-ov__cell-label">Penalty kill</div>
                              <div className="player-ov__cell-val player-ov__cell-val--text">{pkRole ? pkRole[0].toUpperCase() + pkRole.slice(1) : '—'}</div>
                            </div>
                          </div>
                        </div>
                      </section>
                      <section className="player-ov__sec player-ov__details-r">
                        <div className="player-ov__eyebrow">Production rates</div>
                        <div className="player-ov__prod">
                          {([
                            { label: 'Points/60', value: playerDetail.points_per60.toFixed(2), tip: 'Points per 60 minutes', rank: playerDetail.points_per60_rank },
                            { label: 'Goals/60', value: playerDetail.goals_per60.toFixed(2), tip: 'Goals per 60 minutes', rank: playerDetail.goals_per60_rank },
                            { label: 'Assists/60', value: playerDetail.assists_per60.toFixed(2), tip: 'Primary assists per 60 minutes', rank: playerDetail.assists_per60_rank },
                            { label: 'ixG/60', value: playerDetail.hdcf_per60.toFixed(2), tip: 'Individual expected goals per 60', rank: playerDetail.hdcf_per60_rank },
                          ] as { label: string; value: string; tip: string; rank?: number | null }[]).map((c) => {
                            const ri = rankInfo(c.rank, playerDetail.rank_pool)
                            return (
                              <StatCard key={c.label} label={c.label} value={c.value} tooltip={c.tip}
                                rankText={ri?.text} percentile={pctileOf(c.rank, playerDetail.rank_pool)} />
                            )
                          })}
                        </div>
                      </section>
                    </div>
                  ) : goalieSeason ? (
                    <section className="player-ov__sec">
                      <div className="player-ov__eyebrow">Goaltending</div>
                      <div className="player-ov__prod">
                        <StatCard label="GSAx" value={(goalieSeason.gsax >= 0 ? '+' : '') + goalieSeason.gsax.toFixed(1)} tooltip="Goals saved above expected (season)" />
                        {goalieSeason.our_hd_gsax != null && <StatCard label="HD GSAx" value={(goalieSeason.our_hd_gsax >= 0 ? '+' : '') + goalieSeason.our_hd_gsax.toFixed(1)} tooltip="High-danger goals saved above expected" />}
                        {goalieSeason.save_pct != null && <StatCard label="SV%" value={goalieSeason.save_pct.toFixed(3).replace(/^0/, '')} tooltip="Save percentage" />}
                        {goalieSeason.gaa != null && <StatCard label="GAA" value={goalieSeason.gaa.toFixed(2)} tooltip="Goals against average (per 60 in net)" />}
                      </div>
                    </section>
                  ) : null}
                </div>
                )
              })()}

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

                  {/* Situational breakdown (relocated from Overview): 5v5 / PP / PK / All */}
                  {!isGoalie && situational && situational.length > 0 && (() => {
                    const order = ['5v5', 'pp', 'pk', 'all']
                    const label: Record<string, string> = { '5v5': '5v5', pp: 'Power play', pk: 'Penalty kill', all: 'All situations' }
                    const rows = order
                      .map((s) => situational.find((r) => r.situation === s))
                      .filter(Boolean) as PlayerSituational[]
                    const num = (v: number | null | undefined, d = 2) => (v == null ? '—' : v.toFixed(d))
                    const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
                    return rows.length > 0 ? (
                      <div className="player-profile__section">
                        <h2 className="player-profile__section-title">Situational breakdown</h2>
                        <div className="player-sit">
                          <table className="player-sit__table">
                            <thead>
                              <tr>
                                <th className="player-sit__th player-sit__th--label">Situation</th>
                                <th className="player-sit__th">TOI/GP</th>
                                <th className="player-sit__th">P/60</th>
                                <th className="player-sit__th">ixG/60</th>
                                <th className="player-sit__th">CF%</th>
                                <th className="player-sit__th">HDCF/60</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rows.map((r) => (
                                <tr key={r.situation} className={r.situation === 'all' ? 'player-sit__tr--all' : undefined}>
                                  <td className="player-sit__td player-sit__td--label">{label[r.situation] ?? r.situation}</td>
                                  <td className="player-sit__td mono">{r.toi_per_gp == null ? '—' : formatTOI(r.toi_per_gp)}</td>
                                  <td className="player-sit__td mono">{num(r.points_per60)}</td>
                                  <td className="player-sit__td mono">{num(r.ixg_per60)}</td>
                                  <td className="player-sit__td mono">{pct(r.cf_pct)}</td>
                                  <td className="player-sit__td mono">{num(r.hdcf_per60, 1)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <p className="player-sit__note">Rates by strength state. Blank cells are not tracked for that situation.</p>
                        </div>
                      </div>
                    ) : null
                  })()}

                  {/* Clean empty state when no value/reconciliation data exists */}
                  {!playerDetail.value
                    && !(isGoalie && goalieSeason?.value)
                    && !(playerDetail.composite_components && playerDetail.composite_components.length > 0)
                    && !(reconciliation && (reconciliation.clutch || reconciliation.coach_trust))
                    && !(!isGoalie && situational && situational.length > 0) && (
                    <div className="player-profile__empty">No impact or value data available for this player.</div>
                  )}
                </div>
              )}

              {/* ============================ TRENDS ============================ */}
              {currentTab === 'trends' && (
                <div className="player-tab">
                  {/* Sustainability hero (relocated from Overview): Goals/60 vs ixG/60, 5-game rolling */}
                  {!isGoalie && playerTrends?.goals_per60_5gp && playerTrends.goals_per60_5gp.length > 0
                    && playerTrends.ixg_per60_5gp && playerTrends.ixg_per60_5gp.length > 0 && (() => {
                    const ixgByDate = new Map(playerTrends.ixg_per60_5gp!.map((p) => [p.game_date, p.value]))
                    const data = playerTrends.goals_per60_5gp!.map((p) => ({
                      date: formatDate(p.game_date), goals: p.value, ixg: ixgByDate.get(p.game_date) ?? null,
                    }))
                    const meanG = playerTrends.goals_per60_5gp!.reduce((a, p) => a + p.value, 0) / playerTrends.goals_per60_5gp!.length
                    const meanX = playerTrends.ixg_per60_5gp!.reduce((a, p) => a + p.value, 0) / playerTrends.ixg_per60_5gp!.length
                    const delta = meanG - meanX
                    const insight = Math.abs(delta) < 0.1
                      ? 'Goals are tracking expected scoring chances. Production looks sustainable.'
                      : delta > 0
                        ? `Goals are running above expected (${meanG.toFixed(2)} vs ${meanX.toFixed(2)} per 60). Some finishing regression is likely.`
                        : `Goals are running below expected (${meanG.toFixed(2)} vs ${meanX.toFixed(2)} per 60). Finishing may rebound if the chances hold.`
                    return (
                      <div className="player-profile__section">
                        <h2 className="player-profile__section-title">Is the scoring real?</h2>
                        <p className="trajectory__cap">{insight}</p>
                        <div className="player-profile__chart">
                          <ResponsiveContainer width="100%" height={300}>
                            <LineChart data={data}>
                              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.3} />
                              <XAxis dataKey="date" stroke="var(--color-text-muted)" style={{ fontSize: 'var(--text-xs)' }} />
                              <YAxis stroke="var(--color-text-muted)" style={{ fontSize: 'var(--text-xs)' }} />
                              <RechartsTooltip
                                contentStyle={{ backgroundColor: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-sm)' }}
                                labelStyle={{ color: 'var(--color-text-secondary)' }} />
                              <Legend wrapperStyle={{ fontSize: 'var(--text-xs)' }} />
                              <Line type="monotone" dataKey="goals" stroke={teamColor} strokeWidth={2} dot={false} name="Goals/60 (5-game)" connectNulls />
                              <Line type="monotone" dataKey="ixg" stroke="var(--color-text-muted)" strokeWidth={2} strokeDasharray="5 4" dot={false} name="Expected (ixG)/60" connectNulls />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )
                  })()}

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

                  {/* Shot-zone quality (relocated from Overview): shot diet by danger vs positional avg */}
                  {!isGoalie && shotQuality && shotQuality.bands.length > 0 && (() => {
                    const bandLabel: Record<string, string> = { high: 'High danger', medium: 'Medium danger', low: 'Low danger' }
                    const posWord = shotQuality.pos_group === 'D' ? 'defensemen' : 'forwards'
                    const maxShare = Math.max(0.01, ...shotQuality.bands.flatMap((b) => [b.share, b.league_share]))
                    return (
                      <div className="player-profile__section">
                        <h2 className="player-profile__section-title">Shot-zone quality</h2>
                        <p className="trajectory__cap">
                          Share of unblocked shot attempts by danger ({shotQuality.total_attempts} attempts),
                          with the average {posWord} for reference (the tick).
                        </p>
                        <div className="player-sq">
                          {shotQuality.bands.map((b) => (
                            <div key={b.band} className={`player-sq__row player-sq__row--${b.band}`}>
                              <span className="player-sq__label">{bandLabel[b.band] ?? b.band}</span>
                              <div className="player-sq__track">
                                <div className="player-sq__fill" style={{ width: `${(b.share / maxShare) * 100}%` }} />
                                <div className="player-sq__ref" style={{ left: `${(b.league_share / maxShare) * 100}%` }}
                                  title={`${posWord} average ${(b.league_share * 100).toFixed(1)}%`} />
                              </div>
                              <span className="player-sq__val mono">{(b.share * 100).toFixed(0)}%
                                <span className="player-sq__lg"> lg {(b.league_share * 100).toFixed(0)}%</span>
                              </span>
                              <span className="player-sq__g mono">{b.goals} G</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })()}
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
