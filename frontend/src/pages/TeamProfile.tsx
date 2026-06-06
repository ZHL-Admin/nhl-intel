import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { PageLayout, SkeletonLoader, StatCard, Badge } from '../components/common'
import { getTeamDetail, getTeamTrends, getTeamRoster, getTeamVsOpponent } from '../api/teams'
import { getTeamGames } from '../api/games'
import { TeamDetail, TeamTrends, TeamRoster, Game, TeamVsOpponent } from '../api/types'
import { getTeamLogoUrl, getTeamName, getTeamColor, formatDateForAPI } from '../utils/teams'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine, Label } from 'recharts'
import './TeamProfile.css'

function TeamProfile() {
  const { teamId } = useParams<{ teamId: string }>()
  const navigate = useNavigate()

  const [teamDetail, setTeamDetail] = useState<TeamDetail | null>(null)
  const [teamTrends, setTeamTrends] = useState<TeamTrends | null>(null)
  const [teamRoster, setTeamRoster] = useState<TeamRoster | null>(null)
  const [upcomingGame, setUpcomingGame] = useState<Game | null>(null)
  const [selectedOpponent, setSelectedOpponent] = useState<number | null>(null)
  const [opponentStats, setOpponentStats] = useState<TeamVsOpponent | null>(null)

  const [loading, setLoading] = useState(true)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [trendsError, setTrendsError] = useState<string | null>(null)
  const [rosterError, setRosterError] = useState<string | null>(null)
  const [opponentError, setOpponentError] = useState<string | null>(null)

  const [sortConfig, setSortConfig] = useState<{
    key: string
    direction: 'asc' | 'desc'
  }>({ key: 'points_per60', direction: 'desc' })

  useEffect(() => {
    if (!teamId) return

    const fetchData = async () => {
      setLoading(true)
      setDetailError(null)
      setTrendsError(null)
      setRosterError(null)

      try {
        const detail = await getTeamDetail(parseInt(teamId))
        setTeamDetail(detail)
      } catch (err) {
        console.error('Error fetching team detail:', err)
        setDetailError('Failed to load team details.')
      }

      // Fetch trends and roster independently
      try {
        const trends = await getTeamTrends(parseInt(teamId))
        setTeamTrends(trends)
      } catch (err) {
        console.error('Error fetching team trends:', err)
        setTrendsError('Failed to load team trends.')
      }

      try {
        const roster = await getTeamRoster(parseInt(teamId))
        setTeamRoster(roster)
      } catch (err) {
        console.error('Error fetching team roster:', err)
        setRosterError('Failed to load team roster.')
      }

      // Fetch upcoming games (next 7 days)
      try {
        const today = new Date()
        const nextWeek = new Date()
        nextWeek.setDate(today.getDate() + 7)

        const games = await getTeamGames(
          parseInt(teamId),
          formatDateForAPI(today),
          formatDateForAPI(nextWeek)
        )

        // Find the next preview game
        const nextGame = games.find(g => g.is_preview)
        if (nextGame) {
          setUpcomingGame(nextGame)
        }
      } catch (err) {
        console.error('Error fetching upcoming games:', err)
        // Not critical, don't set error state
      }

      setLoading(false)
    }

    fetchData()
  }, [teamId])

  const handleRetryDetail = () => {
    if (teamId) {
      window.location.reload()
    }
  }

  const handleRetryTrends = async () => {
    if (!teamId) return
    setTrendsError(null)
    try {
      const trends = await getTeamTrends(parseInt(teamId))
      setTeamTrends(trends)
    } catch (err) {
      setTrendsError('Failed to load team trends.')
    }
  }

  const handleRetryRoster = async () => {
    if (!teamId) return
    setRosterError(null)
    try {
      const roster = await getTeamRoster(parseInt(teamId))
      setTeamRoster(roster)
    } catch (err) {
      setRosterError('Failed to load team roster.')
    }
  }

  const handleOpponentSelect = async (opponentId: number) => {
    if (!teamId) return
    setSelectedOpponent(opponentId)
    setOpponentError(null)
    setOpponentStats(null)

    try {
      const stats = await getTeamVsOpponent(parseInt(teamId), opponentId)
      setOpponentStats(stats)
    } catch (err) {
      console.error('Error fetching opponent stats:', err)
      setOpponentError('Failed to load opponent stats.')
    }
  }

  const handleRetryOpponent = () => {
    if (selectedOpponent) {
      handleOpponentSelect(selectedOpponent)
    }
  }

  const handleSort = (key: string) => {
    let direction: 'asc' | 'desc' = 'desc'
    if (sortConfig.key === key && sortConfig.direction === 'desc') {
      direction = 'asc'
    }
    setSortConfig({ key, direction })
  }

  const sortPlayers = (players: any[]) => {
    if (!sortConfig.key) return players

    return [...players].sort((a, b) => {
      const aVal = a[sortConfig.key]
      const bVal = b[sortConfig.key]

      if (aVal === bVal) return 0

      const comparison = aVal > bVal ? 1 : -1
      return sortConfig.direction === 'asc' ? comparison : -comparison
    })
  }

  // Loading state
  if (loading) {
    return (
      <PageLayout>
        <div className="team-profile">
          {/* Header skeleton */}
          <div className="team-profile__header-skeleton">
            <SkeletonLoader height={120} />
          </div>

          {/* Stat cards skeleton */}
          <div className="team-profile__section">
            <h2 className="team-profile__section-title">Season Snapshot</h2>
            <div className="team-profile__stat-grid">
              {[...Array(8)].map((_, i) => (
                <SkeletonLoader key={i} height={100} />
              ))}
            </div>
          </div>

          {/* Charts skeleton */}
          <div className="team-profile__section">
            <SkeletonLoader height={300} />
          </div>
          <div className="team-profile__section">
            <SkeletonLoader height={300} />
          </div>

          {/* Roster skeleton */}
          <div className="team-profile__section">
            <SkeletonLoader height={400} />
          </div>
        </div>
      </PageLayout>
    )
  }

  // Error state for critical data
  if (detailError || !teamDetail) {
    return (
      <PageLayout>
        <div className="team-profile__error">
          <p className="team-profile__error-message">
            {detailError || 'Team not found'}
          </p>
          <button onClick={handleRetryDetail} className="team-profile__retry-button">
            Retry
          </button>
        </div>
      </PageLayout>
    )
  }

  const teamColor = getTeamColor(teamDetail.team_abbrev)
  const teamFullName = getTeamName(teamDetail.team_abbrev)

  return (
    <PageLayout>
      <div className="team-profile">
        {/* Team Header */}
        <div
          className="team-profile__header"
          style={{ backgroundColor: `${teamColor}14` }}
        >
          <img
            src={getTeamLogoUrl(teamDetail.team_abbrev)}
            alt={teamFullName}
            className="team-profile__logo"
          />
          <div className="team-profile__header-info">
            <h1 className="team-profile__team-name">{teamFullName}</h1>
            <div className="team-profile__record">
              <span className="mono">{teamDetail.wins}-{teamDetail.losses}-{teamDetail.otl}</span>
              <span className="team-profile__points">{teamDetail.points} PTS</span>
            </div>
          </div>
        </div>

        {/* Upcoming Game Strip (conditional) */}
        {upcomingGame && (
          <div
            className="team-profile__upcoming-game"
            onClick={() => navigate(`/games/${upcomingGame.game_id}`)}
          >
            <div className="team-profile__upcoming-game-label">
              Next Game
            </div>
            <div className="team-profile__upcoming-game-info">
              <div className="team-profile__upcoming-game-opponent">
                {upcomingGame.home_team_id === teamDetail.team_id ? 'vs' : '@'}{' '}
                <span className="team-profile__upcoming-game-opponent-name">
                  {upcomingGame.home_team_id === teamDetail.team_id
                    ? getTeamName(upcomingGame.away_team_abbrev)
                    : getTeamName(upcomingGame.home_team_abbrev)}
                </span>
              </div>
              <div className="team-profile__upcoming-game-date">
                {new Date(upcomingGame.game_date).toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'short',
                  day: 'numeric'
                })}
              </div>
            </div>
            <div className="team-profile__upcoming-game-arrow">→</div>
          </div>
        )}

        {/* Season Snapshot */}
        <div className="team-profile__section">
          <h2 className="team-profile__section-title">Season Snapshot</h2>
          <div className="team-profile__stat-grid">
            <StatCard
              label="CF%"
              value={(teamDetail.cf_pct * 100).toFixed(1) + '%'}
              rank={1}
            />
            <StatCard
              label="xGF%"
              value="50.0%"
              rank={15}
            />
            <StatCard
              label="HDCF/60"
              value={teamDetail.hdcf_per60.toFixed(2)}
              rank={8}
            />
            <StatCard
              label="HDCA/60"
              value={teamDetail.hdca_per60.toFixed(2)}
              rank={20}
            />
            <StatCard
              label="GF/GP"
              value={(teamDetail.total_goals_for / teamDetail.games_played).toFixed(2)}
              rank={5}
            />
            <StatCard
              label="GA/GP"
              value={(teamDetail.total_goals_against / teamDetail.games_played).toFixed(2)}
              rank={12}
            />
            <StatCard
              label="PDO"
              value="1.005"
              rank={16}
              tooltip="PDO measures shooting % + save % at 5v5. Values above 1.000 suggest good luck, below suggests bad luck. League average is 1.000."
            />
            <StatCard
              label="Zone Entry Success"
              value={teamDetail.zone_entry_success_rate ? `${(teamDetail.zone_entry_success_rate * 100).toFixed(1)}%` : 'N/A'}
              rank={undefined}
            />
          </div>
        </div>

        {/* Season Trends - Chart 1: CF% and xGF% */}
        <div className="team-profile__section">
          <h2 className="team-profile__section-title">Possession Trends (5-Game Rolling)</h2>
          {trendsError ? (
            <div className="team-profile__section-error">
              <p>{trendsError}</p>
              <button onClick={handleRetryTrends} className="team-profile__retry-button">
                Retry
              </button>
            </div>
          ) : teamTrends && teamTrends.cf_pct_5gp.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart
                data={teamTrends.cf_pct_5gp.map((point, i) => ({
                  date: new Date(point.game_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                  cf_pct: point.value * 100,
                  xgf_pct: teamTrends.xgf_pct_5gp[i]?.value * 100 || 50
                }))}
                margin={{ right: 60 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis
                  dataKey="date"
                  stroke="var(--color-text-muted)"
                  style={{ fontSize: 'var(--text-xs)' }}
                />
                <YAxis
                  stroke="var(--color-text-muted)"
                  style={{ fontSize: 'var(--text-xs)' }}
                  domain={[40, 60]}
                />
                <RechartsTooltip
                  formatter={(value: number) => `${value.toFixed(1)}%`}
                  contentStyle={{
                    backgroundColor: 'var(--color-bg-surface)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-md)'
                  }}
                />
                <ReferenceLine y={50} stroke="var(--color-text-muted)" strokeDasharray="3 3" />
                <Line
                  type="monotone"
                  dataKey="cf_pct"
                  stroke={teamColor}
                  strokeWidth={2}
                  dot={false}
                  name="CF%"
                >
                  <Label
                    value="CF%"
                    position="right"
                    fill={teamColor}
                    style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}
                  />
                </Line>
                <Line
                  type="monotone"
                  dataKey="xgf_pct"
                  stroke="var(--color-accent)"
                  strokeWidth={2}
                  dot={false}
                  name="xGF%"
                >
                  <Label
                    value="xGF%"
                    position="right"
                    fill="var(--color-accent)"
                    style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}
                  />
                </Line>
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="team-profile__no-data">Insufficient data for trends</div>
          )}
        </div>

        {/* Season Trends - Chart 2: HDCF/60 vs HDCA/60 */}
        <div className="team-profile__section">
          <h2 className="team-profile__section-title">High Danger Chances (5-Game Rolling)</h2>
          {trendsError ? (
            <div className="team-profile__section-error">
              <p>{trendsError}</p>
              <button onClick={handleRetryTrends} className="team-profile__retry-button">
                Retry
              </button>
            </div>
          ) : teamTrends && teamTrends.hdcf_per60_5gp.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart
                data={teamTrends.hdcf_per60_5gp.map((point) => ({
                  date: new Date(point.game_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                  hdcf: point.value,
                  hdca: point.value * 0.9 // Placeholder - backend doesn't have hdca rolling yet
                }))}
                margin={{ right: 80 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
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
                  formatter={(value: number) => value.toFixed(2)}
                  contentStyle={{
                    backgroundColor: 'var(--color-bg-surface)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-md)'
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="hdcf"
                  stroke="var(--color-data-positive)"
                  strokeWidth={2}
                  dot={false}
                  name="HDCF/60"
                >
                  <Label
                    value="HDCF/60"
                    position="right"
                    fill="var(--color-data-positive)"
                    style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}
                  />
                </Line>
                <Line
                  type="monotone"
                  dataKey="hdca"
                  stroke="var(--color-data-negative)"
                  strokeWidth={2}
                  dot={false}
                  name="HDCA/60"
                >
                  <Label
                    value="HDCA/60"
                    position="right"
                    fill="var(--color-data-negative)"
                    style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}
                  />
                </Line>
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="team-profile__no-data">Insufficient data for trends</div>
          )}
        </div>

        {/* vs Opponent Section */}
        <div className="team-profile__section">
          <h2 className="team-profile__section-title">vs Opponent</h2>
          {!selectedOpponent ? (
            <div className="team-profile__vs-opponent-prompt">
              <p>Select an opponent to view head-to-head stats</p>
              <select
                className="team-profile__vs-opponent-select"
                onChange={(e) => handleOpponentSelect(parseInt(e.target.value))}
                defaultValue=""
              >
                <option value="" disabled>
                  Choose opponent...
                </option>
                {/* NHL Teams - hardcoded for now */}
                <option value="1">New Jersey Devils</option>
                <option value="2">New York Islanders</option>
                <option value="3">New York Rangers</option>
                <option value="4">Philadelphia Flyers</option>
                <option value="5">Pittsburgh Penguins</option>
                <option value="6">Boston Bruins</option>
                <option value="7">Buffalo Sabres</option>
                <option value="8">Montreal Canadiens</option>
                <option value="9">Ottawa Senators</option>
                <option value="10">Toronto Maple Leafs</option>
              </select>
            </div>
          ) : opponentError ? (
            <div className="team-profile__section-error">
              <p>{opponentError}</p>
              <button onClick={handleRetryOpponent} className="team-profile__retry-button">
                Retry
              </button>
            </div>
          ) : opponentStats ? (
            <div className="team-profile__vs-opponent-stats">
              {opponentStats.small_sample && (
                <div className="team-profile__small-sample-badge">
                  <Badge variant="small-sample" />
                  <span className="team-profile__small-sample-text">
                    {opponentStats.games_played} {opponentStats.games_played === 1 ? 'game' : 'games'} played
                  </span>
                </div>
              )}
              <div className="team-profile__stat-grid">
                <StatCard
                  label="Record"
                  value={`${opponentStats.wins}-${opponentStats.losses}-${opponentStats.otl}`}
                />
                <StatCard
                  label="CF%"
                  value={opponentStats.cf_pct ? `${(opponentStats.cf_pct * 100).toFixed(1)}%` : 'N/A'}
                />
                <StatCard
                  label="HDCF/60"
                  value={opponentStats.hdcf_per60?.toFixed(2) || 'N/A'}
                />
                <StatCard
                  label="xGF/60"
                  value={opponentStats.xgf_per60?.toFixed(2) || 'N/A'}
                />
              </div>
              <button
                className="team-profile__vs-opponent-change"
                onClick={() => setSelectedOpponent(null)}
              >
                Change Opponent
              </button>
            </div>
          ) : (
            <div className="team-profile__no-data">Loading opponent stats...</div>
          )}
        </div>

        {/* Roster */}
        <div className="team-profile__section">
          <h2 className="team-profile__section-title">Roster</h2>
          {rosterError ? (
            <div className="team-profile__section-error">
              <p>{rosterError}</p>
              <button onClick={handleRetryRoster} className="team-profile__retry-button">
                Retry
              </button>
            </div>
          ) : teamRoster ? (
            <div className="team-profile__roster">
              {/* Forwards */}
              {teamRoster.forwards.length > 0 && (
                <div className="team-profile__roster-section">
                  <h3 className="team-profile__roster-heading">Forwards</h3>
                  <table className="team-profile__roster-table">
                    <thead>
                      <tr>
                        <th onClick={() => handleSort('player_name')} className="team-profile__roster-sortable">
                          Player {sortConfig.key === 'player_name' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th onClick={() => handleSort('games_played')} className="team-profile__roster-table-number team-profile__roster-sortable">
                          GP {sortConfig.key === 'games_played' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th onClick={() => handleSort('toi_per_gp')} className="team-profile__roster-table-number team-profile__roster-sortable">
                          TOI/GP {sortConfig.key === 'toi_per_gp' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th onClick={() => handleSort('points_per60')} className="team-profile__roster-table-number team-profile__roster-sortable">
                          PTS/60 {sortConfig.key === 'points_per60' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th onClick={() => handleSort('cf_pct')} className="team-profile__roster-table-number team-profile__roster-sortable hide-mobile">
                          CF% {sortConfig.key === 'cf_pct' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortPlayers(teamRoster.forwards).map((player) => (
                        <tr
                          key={player.player_id}
                          className="team-profile__roster-row"
                          onClick={() => navigate(`/players/${player.player_id}`)}
                        >
                          <td>{player.player_name}</td>
                          <td className="team-profile__roster-table-number mono">{player.games_played}</td>
                          <td className="team-profile__roster-table-number mono">{player.toi_per_gp.toFixed(1)}</td>
                          <td className="team-profile__roster-table-number mono">{player.points_per60.toFixed(2)}</td>
                          <td className="team-profile__roster-table-number mono hide-mobile">
                            {(player.cf_pct * 100).toFixed(1)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Defensemen */}
              {teamRoster.defensemen.length > 0 && (
                <div className="team-profile__roster-section">
                  <h3 className="team-profile__roster-heading">Defensemen</h3>
                  <table className="team-profile__roster-table">
                    <thead>
                      <tr>
                        <th onClick={() => handleSort('player_name')} className="team-profile__roster-sortable">
                          Player {sortConfig.key === 'player_name' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th onClick={() => handleSort('games_played')} className="team-profile__roster-table-number team-profile__roster-sortable">
                          GP {sortConfig.key === 'games_played' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th onClick={() => handleSort('toi_per_gp')} className="team-profile__roster-table-number team-profile__roster-sortable">
                          TOI/GP {sortConfig.key === 'toi_per_gp' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th onClick={() => handleSort('points_per60')} className="team-profile__roster-table-number team-profile__roster-sortable">
                          PTS/60 {sortConfig.key === 'points_per60' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th onClick={() => handleSort('cf_pct')} className="team-profile__roster-table-number team-profile__roster-sortable hide-mobile">
                          CF% {sortConfig.key === 'cf_pct' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortPlayers(teamRoster.defensemen).map((player) => (
                        <tr
                          key={player.player_id}
                          className="team-profile__roster-row"
                          onClick={() => navigate(`/players/${player.player_id}`)}
                        >
                          <td>{player.player_name}</td>
                          <td className="team-profile__roster-table-number mono">{player.games_played}</td>
                          <td className="team-profile__roster-table-number mono">{player.toi_per_gp.toFixed(1)}</td>
                          <td className="team-profile__roster-table-number mono">{player.points_per60.toFixed(2)}</td>
                          <td className="team-profile__roster-table-number mono hide-mobile">
                            {(player.cf_pct * 100).toFixed(1)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Goalies */}
              {teamRoster.goalies.length > 0 && (
                <div className="team-profile__roster-section">
                  <h3 className="team-profile__roster-heading">Goalies</h3>
                  <table className="team-profile__roster-table">
                    <thead>
                      <tr>
                        <th onClick={() => handleSort('player_name')} className="team-profile__roster-sortable">
                          Player {sortConfig.key === 'player_name' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th onClick={() => handleSort('games_played')} className="team-profile__roster-table-number team-profile__roster-sortable">
                          GP {sortConfig.key === 'games_played' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th onClick={() => handleSort('toi_per_gp')} className="team-profile__roster-table-number team-profile__roster-sortable">
                          TOI/GP {sortConfig.key === 'toi_per_gp' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                        </th>
                        <th className="team-profile__roster-table-number hide-mobile">SV%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortPlayers(teamRoster.goalies).map((player) => (
                        <tr
                          key={player.player_id}
                          className="team-profile__roster-row"
                          onClick={() => navigate(`/players/${player.player_id}`)}
                        >
                          <td>{player.player_name}</td>
                          <td className="team-profile__roster-table-number mono">{player.games_played}</td>
                          <td className="team-profile__roster-table-number mono">{player.toi_per_gp.toFixed(1)}</td>
                          <td className="team-profile__roster-table-number mono hide-mobile">N/A</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <div className="team-profile__no-data">No roster data available</div>
          )}
        </div>
      </div>
    </PageLayout>
  )
}

export default TeamProfile
