import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { PageLayout, StatCard, Badge, SkeletonLoader, ComponentStackBar, ImpactValuePanel, OverallSummary } from '../components/common'
import type { StackSegment } from '../components/common'
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
  getPlayerRadar
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
  GoalieSeason
} from '../api/types'
import { setTeamPrimaryColor, clearTeamPrimaryColor, getTeamColor as getTeamColorByAbbrev } from '../utils/teams'
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

function PlayerProfile() {
  const { playerId } = useParams<{ playerId: string }>()
  const navigate = useNavigate()

  // Data states
  const [playerDetail, setPlayerDetail] = useState<PlayerDetail | null>(null)
  const [radar, setRadar] = useState<PlayerRadar | null>(null)
  const [goalieRadar, setGoalieRadar] = useState<GoalieRadar | null>(null)
  const [goalieSeason, setGoalieSeason] = useState<GoalieSeason | null>(null)
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
  const [errorTrends, setErrorTrends] = useState<string | null>(null)
  const [errorShots, setErrorShots] = useState<string | null>(null)
  const [errorGamelog, setErrorGamelog] = useState<string | null>(null)
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

  // Helper: Get player initials for headshot fallback
  const getPlayerInitials = (name: string): string => {
    const parts = name.split(' ')
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
    }
    return name.slice(0, 2).toUpperCase()
  }

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

  return (
    <PageLayout>
      <div className="player-profile">
        {/* Back Navigation */}
        <button className="player-profile__back" onClick={() => navigate(-1)}>
          <ArrowLeft size={20} />
          <span>Back</span>
        </button>

        {/* Player Header */}
        {loadingDetail ? (
          <div className="player-profile__header">
            <SkeletonLoader width={80} height={80} borderRadius="50%" />
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
          <div className="player-profile__header" style={{ borderLeftColor: teamColor }}>
            <div className="player-profile__headshot">
              <div className="player-profile__headshot-fallback">
                {getPlayerInitials(playerDetail.player_name)}
              </div>
            </div>
            <div className="player-profile__header-info">
              <h1 className="player-profile__name">{playerDetail.player_name}</h1>
              <div className="player-profile__meta">
                <span
                  className="player-profile__team"
                  onClick={(e) => handleTeamClick(e, playerDetail.team_id)}
                >
                  {playerDetail.team_abbrev}
                </span>
                <span className="player-profile__separator">•</span>
                <span className="player-profile__position">{playerDetail.position}</span>
                {/* TODO: Add age, handedness, jersey number when available in API */}
              </div>
              {playerDetail.archetypes && playerDetail.archetypes.length > 0 && (
                <div className="player-profile__archetype">
                  {playerDetail.archetypes.slice(0, 3)
                    .map((a) => `${Math.round(a.weight * 100)}% ${a.archetype}`)
                    .join(' · ')}
                </div>
              )}
            </div>
          </div>
        ) : null}

        {/* Skills radar — primary header visual (Part B) */}
        {(radar || goalieRadar) && (
          <div className="player-profile__radar">
            <div className="player-profile__radar-chart">
              <SkillRadar
                spokes={(radar ?? goalieRadar)!.spokes}
                baseline={(radar ?? goalieRadar)!.baseline}
              />
            </div>
            {radar && (() => {
              const labels = playerLabelsFromRadar(radar)   // single source for player labels (B6)
              return (
                <div className="player-profile__radar-labels">
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
                </div>
              )
            })()}
          </div>
        )}

        {/* Impact (RAPM) vs Value (GAR) — the two scalar verdicts under the radar (Phase 6 GAR) */}
        {playerDetail?.value && (
          <div className="player-profile__impact-value">
            <ImpactValuePanel value={playerDetail.value} name={playerDetail.player_name} />
            {/* Per-player Overall — within-position summary, shown WITH its component percentiles
                (the same lenses as the panel above) and the reused Impact-vs-Value read. */}
            {playerDetail.value.overall && (
              <OverallSummary overall={playerDetail.value.overall} read={playerDetail.value.read} />
            )}
          </div>
        )}

        {/* Goalie value (GAR/WAR, cross-position scale) + within-goalie Overall (Phase 6 GAR) */}
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
            <div className="player-profile__impact-value">
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
              {goalieSeason.overall && <OverallSummary overall={goalieSeason.overall} />}
            </div>
          )
        })()}

        {/* Composite value stack (Phase 4.2) — depth 2 */}
        {playerDetail && playerDetail.composite_components && playerDetail.composite_components.length > 0 && (() => {
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

        {/* Season Stat Cards */}
        {loadingDetail ? (
          <div className="player-profile__stats-grid">
            {Array.from({ length: isGoalie ? 6 : 10 }).map((_, i) => (
              <SkeletonLoader key={i} height={100} />
            ))}
          </div>
        ) : errorDetail ? null : playerDetail ? (
          <div className="player-profile__stats-grid">
            {isGoalie ? (
              // TODO: Goalie stats not yet available in API
              // Placeholder for: GAA, SV%, xSV%, GSAX, HDSA, HD SV%
              <>
                <StatCard label="GAA" value="—" tooltip="Goals Against Average (not yet available)" />
                <StatCard label="SV%" value="—" tooltip="Save Percentage (not yet available)" />
                <StatCard label="xSV%" value="—" tooltip="Expected Save Percentage (not yet available)" />
                <StatCard label="GSAX" value="—" tooltip="Goals Saved Above Expected (not yet available)" />
                <StatCard label="HDSA" value="—" tooltip="High Danger Shots Against (not yet available)" />
                <StatCard label="HD SV%" value="—" tooltip="High Danger Save Percentage (not yet available)" />
              </>
            ) : (
              // Skater stats
              <>
                <StatCard
                  label="TOI/GP"
                  value={formatTOI(playerDetail.toi_per_gp)}
                  tooltip="Time on Ice per Game"
                />
                <StatCard
                  label="Points/60"
                  value={playerDetail.points_per60.toFixed(2)}
                  tooltip="Points per 60 minutes"
                />
                <StatCard
                  label="Goals/60"
                  value={playerDetail.goals_per60.toFixed(2)}
                  tooltip="Goals per 60 minutes"
                />
                <StatCard
                  label="Assists/60"
                  value={playerDetail.assists_per60.toFixed(2)}
                  tooltip="Assists per 60 minutes"
                />
                <StatCard
                  label="CF%"
                  value={`${(playerDetail.cf_pct * 100).toFixed(1)}%`}
                  tooltip="Corsi For Percentage"
                />
                <StatCard
                  label="HDCF/60"
                  value={playerDetail.hdcf_per60.toFixed(2)}
                  tooltip="High Danger Chances For per 60 minutes"
                />
                {/* TODO: Add more stats when available: ixG/60 with hot/cold badge, on-ice xGF%, relative CF% */}
              </>
            )}
          </div>
        ) : null}

        {/* Eye-test reconciliation (Phase 4.3) */}
        {reconciliation && (reconciliation.clutch || reconciliation.consistency || reconciliation.coach_trust) && (
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
                    his overall rate — {reconciliation.clutch.confidence}.
                  </p>
                  <div className="reconciliation__sub">
                    raw {reconciliation.clutch.raw_ixg.toFixed(1)} → weighted {reconciliation.clutch.clutch_ixg.toFixed(1)} xG
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
            {reconciliation.consistency && (
              <div className="reconciliation__consistency">
                <div className="reconciliation__panel-title">
                  Consistency · index {(reconciliation.consistency.consistency_index * 100).toFixed(0)}th pctile ·
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
            )}
          </div>
        )}

        {/* Career trajectory (Phase 4.4) */}
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
                      ? ` (position fallback — ${trajectory.archetype} has too little pre-tracking history)` : ''}.
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
                        <span className="trajectory__twin-out">→ {t.next3_points82.toFixed(0)} pts/82 next 3 yrs</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {trajectory.physical.length > 0 && (
                <p className="trajectory__sub">
                  Skating: bursts/60 {trajectory.physical.map((p) => (p.burst_rate ?? 0).toFixed(1)).join(' → ')}
                  {!trajectory.burst_flag_enabled && ' (burst-decline early-warning not shown — it did not predict production decline in our data)'}
                </p>
              )}
            </div>
          )
        })()}

        {/* Primary Trend Chart */}
        {!isGoalie && (
          <div className="player-profile__section">
            <h2 className="player-profile__section-title">Performance Trends</h2>
            {loadingTrends ? (
              <SkeletonLoader height={300} />
            ) : errorTrends ? (
              <div className="player-profile__error">{errorTrends}</div>
            ) : playerTrends && playerTrends.points_per60_5gp.length > 0 ? (
              <div className="player-profile__chart">
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={playerTrends.points_per60_5gp.map(point => ({
                    date: formatDate(point.game_date),
                    fullDate: point.game_date,
                    value: point.value
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.3} />
                    <XAxis
                      dataKey="date"
                      stroke="var(--color-text-muted)"
                      style={{ fontSize: 'var(--text-xs)' }}
                    />
                    <YAxis
                      stroke="var(--color-text-muted)"
                      style={{ fontSize: 'var(--text-xs)' }}
                    />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: 'var(--color-bg-elevated)',
                        border: '1px solid var(--color-border)',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: 'var(--text-sm)'
                      }}
                      labelStyle={{ color: 'var(--color-text-secondary)' }}
                    />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke={teamColor}
                      strokeWidth={2}
                      dot={{ fill: teamColor, r: 3 }}
                      activeDot={{ r: 5 }}
                      name="Points/60 (5-game rolling)"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="player-profile__empty">No trend data available</div>
            )}
          </div>
        )}

        {/* Shot Location Map (Skaters Only) */}
        {!isGoalie && (
          <div className="player-profile__section">
            <h2 className="player-profile__section-title">Shot Locations</h2>
            {loadingShots ? (
              <SkeletonLoader height={400} />
            ) : errorShots ? (
              <div className="player-profile__error">{errorShots}</div>
            ) : playerShots && playerShots.shot_locations.length > 0 ? (
              <ShotMap
                mode="player"
                playerShots={playerShots.shot_locations.map(shot => ({
                  x: shot.x,
                  y: shot.y,
                  outcome: shot.is_goal ? 'goal' : 'shot_on_goal',
                  situation: '1551', // Default to 5v5, TODO: add actual situation data
                  team_id: playerDetail?.team_id || 0
                }))}
                playerTeamColor={teamColor}
                playerName={playerDetail?.player_name || ''}
              />
            ) : (
              <div className="player-profile__empty">No shot data available</div>
            )}
          </div>
        )}

        {/* vs Opponent Section */}
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
                  <div className="player-profile__error">{errorVsOpponent}</div>
                ) : vsOpponentData ? (
                  <>
                    {vsOpponentData.small_sample && (
                      <div style={{ marginTop: 'var(--space-3)' }}>
                        <Badge variant="small-sample" />
                      </div>
                    )}
                    <div className="player-profile__vs-stats">
                      <StatCard
                        label="Games Played"
                        value={vsOpponentData.games_played}
                      />
                      {vsOpponentData.toi_per_gp !== null && (
                        <StatCard
                          label="TOI/GP"
                          value={formatTOI(vsOpponentData.toi_per_gp)}
                        />
                      )}
                      {vsOpponentData.points_per60 !== null && (
                        <StatCard
                          label="Points/60"
                          value={vsOpponentData.points_per60.toFixed(2)}
                        />
                      )}
                      {vsOpponentData.cf_pct !== null && (
                        <StatCard
                          label="CF%"
                          value={`${(vsOpponentData.cf_pct * 100).toFixed(1)}%`}
                        />
                      )}
                    </div>
                  </>
                ) : null}
              </>
            )}
          </div>
        </div>

        {/* Game Log Table */}
        <div className="player-profile__section">
          <h2 className="player-profile__section-title">Game Log (Last 20 Games)</h2>
          {loadingGamelog ? (
            <SkeletonLoader height={400} />
          ) : errorGamelog ? (
            <div className="player-profile__error">{errorGamelog}</div>
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
                    <tr
                      key={game.game_id}
                      className="player-profile__table-row"
                      onClick={() => handleGameClick(game.game_id)}
                    >
                      <td>{formatDate(game.game_date)}</td>
                      <td className="player-profile__opponent-cell">
                        vs {game.opponent_abbrev}
                      </td>
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
            <div className="player-profile__empty">No games played this season</div>
          )}
        </div>
      </div>
    </PageLayout>
  )
}

export default PlayerProfile
