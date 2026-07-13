import { useEffect, useMemo, useRef, useState } from 'react'
import { usePageTitle } from '../hooks/usePageTitle'
import { useSearchParams } from 'react-router-dom'
import { PageLayout, PageCard, Select, SkeletonLoader, ShareActions } from '../components/common'
import { getOffseasonBoard, getTeamOffseason } from '../api/offseason'
import { RosterForecastRow, OffseasonTeamDetail } from '../api/types'
import {
  getTeamName, getTeamColor, setTeamPrimaryColor, clearTeamPrimaryColor, DIVISIONS,
} from '../utils/teams'
import { nextSeasonOf } from '../utils/forecastFormat'
import { drawOffseasonCard } from '../utils/offseasonShareCard'
import OffseasonLeagueTable, {
  OffseasonSortKey, SortDir, DEFAULT_DIR,
} from '../components/forecast/OffseasonLeagueTable'
import TeamDossier from '../components/forecast/TeamDossier'
import '../components/forecast/forecast.css'
import './Offseason.css'

const ALL_TEAMS = DIVISIONS.flatMap((d) => d.teams) // { id, abbrev }
const SORT_KEYS: OffseasonSortKey[] = ['rank', 'points', 'from_moves', 'moves', 'war']
const DEFAULT_SORT = 'points:desc'

/** Verdict-kicker date stamp, e.g. "JUL 6" (browser-local; the share card echoes it). */
const shareStamp = () => new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()

function parseSort(raw: string | null): { key: OffseasonSortKey; dir: SortDir } {
  const [k, d] = (raw ?? DEFAULT_SORT).split(':')
  const key = (SORT_KEYS as string[]).includes(k) ? (k as OffseasonSortKey) : 'points'
  const dir: SortDir = d === 'asc' ? 'asc' : d === 'desc' ? 'desc' : DEFAULT_DIR[key]
  return { key, dir }
}

export default function Offseason() {
  usePageTitle('Offseason forecast')
  const [params, setParams] = useSearchParams()
  const [board, setBoard] = useState<RosterForecastRow[] | null>(null)
  const [boardErr, setBoardErr] = useState(false)
  const [details, setDetails] = useState<Record<number, OffseasonTeamDetail>>({})
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailErr, setDetailErr] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const tableRef = useRef<HTMLDivElement>(null)

  const { key: sortKey, dir: sortDir } = parseSort(params.get('sort'))

  // Load the league board once.
  useEffect(() => {
    getOffseasonBoard()
      .then((rows) => setBoard(rows))
      .catch(() => setBoardErr(true))
  }, [])

  // 301: old Team-lens URLs (?view=team&team=ABBR) collapse to ?team=ABBR (auto-expands + scrolls).
  useEffect(() => {
    if (params.get('view')) {
      const next = new URLSearchParams(params)
      next.delete('view')
      setParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The expanded team (one at a time): ?team=ABBR resolved against the board.
  const expanded = useMemo(() => {
    if (!board?.length) return null
    const abbr = params.get('team')?.toUpperCase()
    return abbr ? board.find((r) => r.team_abbrev === abbr) ?? null : null
  }, [board, params])
  const expandedId = expanded?.team_id ?? null

  const setTeam = (abbr: string | null) => {
    const next = new URLSearchParams(params)
    if (abbr) next.set('team', abbr); else next.delete('team')
    next.delete('player') // one player open at a time; a new team clears any open decision
    setParams(next, { replace: true })
  }
  const toggleTeam = (teamId: number) => {
    const row = board?.find((r) => r.team_id === teamId)
    if (!row?.team_abbrev) return
    setTeam(expandedId === teamId ? null : row.team_abbrev)
  }
  const onSort = (col: OffseasonSortKey) => {
    const dir: SortDir = col === sortKey ? (sortDir === 'asc' ? 'desc' : 'asc') : DEFAULT_DIR[col]
    const next = new URLSearchParams(params)
    const value = `${col}:${dir}`
    if (value === DEFAULT_SORT) next.delete('sort'); else next.set('sort', value)
    setParams(next, { replace: true })
  }

  // Team color wash follows the expanded team.
  useEffect(() => {
    if (expanded?.team_abbrev) setTeamPrimaryColor(getTeamColor(expanded.team_abbrev))
    return () => clearTeamPrimaryColor()
  }, [expanded?.team_abbrev])

  // Fetch the expanded team's decomposition (cached per team).
  const loadDetail = (teamId: number) => {
    setDetailLoading(true); setDetailErr(false)
    getTeamOffseason(teamId)
      .then((d) => setDetails((m) => ({ ...m, [teamId]: d })))
      .catch(() => setDetailErr(true))
      .finally(() => setDetailLoading(false))
  }
  useEffect(() => {
    if (expandedId == null || details[expandedId]) { setDetailErr(false); return }
    loadDetail(expandedId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandedId])

  // Auto-scroll the expanded row into view (deep links + jump-to-team).
  useEffect(() => {
    if (expandedId == null) return
    if (!showAll && board) {
      // Ensure the target row is rendered if it sits past the 16-row cap.
      const rank = expanded?.projected_rank ?? 99
      if (rank > 16) setShowAll(true)
    }
    const t = window.setTimeout(() => {
      tableRef.current?.querySelector('.olt__row[aria-selected="true"]')
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 60)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandedId])

  const teamOptions = useMemo(
    () => [{ value: '', label: 'Jump to a team' },
      ...ALL_TEAMS.map((t) => ({ value: t.abbrev, label: getTeamName(t.abbrev) }))
        .sort((a, b) => a.label.localeCompare(b.label))],
    [])

  const season = board?.length ? nextSeasonOf(board[0].transition) : ''
  const stamp = shareStamp()
  const kicker = `OFFSEASON FORECAST · ${stamp}`
  // The share card follows what's open: a team's forecast card when expanded, else the generic verdict.
  const expandedDetail = expandedId != null ? details[expandedId] : undefined

  return (
    <PageLayout>
      <div className="off">
        <PageCard
          eyebrow="Studio"
          title="Offseason forecast"
          subtitle={`Projected standings for ${season || 'next season'}, and the summer's open decisions, priced.`}
          controls={
            <div className="off__toolbar">
              <Select ariaLabel="Jump to a team" value={params.get('team')?.toUpperCase() ?? ''}
                options={teamOptions} onChange={(v) => setTeam(v || null)} />
              <span className="off__updated">Updated daily as moves land</span>
              <ShareActions className="off__share" kicker={kicker}
                verdict={expandedDetail?.verdict ?? `Projected standings for ${season || 'next season'}.`}
                shareName={`rink-theory-offseason${expanded?.team_abbrev ? `-${expanded.team_abbrev.toLowerCase()}` : ''}`}
                renderCard={expandedDetail && expanded
                  ? () => drawOffseasonCard({
                      row: expandedDetail.forecast, moves: expandedDetail.moves,
                      nextSeason: nextSeasonOf(expandedDetail.forecast.transition), dateStamp: stamp,
                    })
                  : undefined} />
            </div>
          }
        >
          {boardErr && <p className="off-msg">The offseason forecast is unavailable right now.</p>}
          {!board && !boardErr && <SkeletonLoader height={480} />}

          {board && (
            <div ref={tableRef}>
              <OffseasonLeagueTable
                rows={board}
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={onSort}
                expandedTeamId={expandedId}
                onToggle={toggleTeam}
                showAll={showAll}
                onShowAll={() => setShowAll(true)}
                dossier={(r) => (
                  <TeamDossier row={r}
                    detail={details[r.team_id] ?? null}
                    loading={detailLoading && !details[r.team_id]}
                    error={detailErr && !details[r.team_id]}
                    onRetry={() => loadDetail(r.team_id)} />
                )}
              />
            </div>
          )}
        </PageCard>
      </div>
    </PageLayout>
  )
}
