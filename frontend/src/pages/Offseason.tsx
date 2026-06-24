import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Pencil, Info } from 'lucide-react'
import { PageLayout, Tabs, Select, SkeletonLoader } from '../components/common'
import { getOffseasonBoard, getTeamOffseason } from '../api/offseason'
import { RosterForecastRow, OffseasonTeamDetail } from '../api/types'
import {
  getTeamLogoUrl, getTeamName, getTeamColor, setTeamPrimaryColor, clearTeamPrimaryColor, DIVISIONS,
} from '../utils/teams'
import { nextSeasonOf } from '../utils/forecastFormat'
import ForecastHeroStats from '../components/forecast/ForecastHeroStats'
import LeagueRail from '../components/forecast/LeagueRail'
import MoveLedger from '../components/forecast/MoveLedger'
import ComponentBars from '../components/forecast/ComponentBars'
import ProjectedLineup from '../components/forecast/ProjectedLineup'
import OffseasonLeagueTable from '../components/forecast/OffseasonLeagueTable'
import QuietState from '../components/forecast/QuietState'
import '../components/forecast/forecast.css'
import './Offseason.css'

const ALL_TEAMS = DIVISIONS.flatMap((d) => d.teams) // { id, abbrev }

function SectionHead({ n, title }: { n: string; title: string }) {
  return (
    <div className="sec__head">
      <span className="sec__num mono">{n}</span>
      <h2 className="sec__title">{title}</h2>
    </div>
  )
}

function TeamDetail({ detail, loading, error, onRetry }: {
  detail: OffseasonTeamDetail | null; loading: boolean; error: boolean; onRetry: () => void
}) {
  if (error) return <p className="off-msg">Could not load this team. <button className="off-retry" onClick={onRetry}>Retry</button></p>
  if (loading || !detail) {
    return (
      <div className="off-detail">
        <SkeletonLoader height={90} /><SkeletonLoader height={180} /><SkeletonLoader height={140} />
      </div>
    )
  }
  const f = detail.forecast
  const arrivals = new Set(
    detail.moves.filter((m) => m.move_type === 'arrival' && m.player_id != null).map((m) => m.player_id as number))
  // Supporting note = largest driver (NOT the style note, which lives only in §02).
  const driverNote = detail.reasons.find((r) => r !== detail.style_note)

  return (
    <div className="off-detail">
      <section className="sec">
        <SectionHead n="01" title="The verdict" />
        <p className="verdict__lead">{detail.verdict}</p>
        {driverNote && <p className="verdict__note"><span className="verdict__dot" />{driverNote}</p>}
      </section>

      <section className="sec">
        <SectionHead n="02" title="What moved the number" />
        {f.negligible
          ? <QuietState nextSeason={nextSeasonOf(f.transition)} />
          : <MoveLedger moves={detail.moves} styleNote={detail.style_note}
              netWar={f.net_delta_war} netGoals={f.delta} />}
      </section>

      <section className="sec">
        <SectionHead n="03" title="Where the strength lives" />
        <ComponentBars components={detail.base_components} />
      </section>

      <section className="sec">
        <SectionHead n="04" title="Projected lineup" />
        <ProjectedLineup lineup={detail.projected_lineup} arrivals={arrivals} />
      </section>

      <div className="off-caption">
        <Info size={18} className="off-caption__icon" aria-hidden />
        <p>{detail.limitations}</p>
      </div>
    </div>
  )
}

export default function Offseason() {
  const [params, setParams] = useSearchParams()
  const [board, setBoard] = useState<RosterForecastRow[] | null>(null)
  const [boardErr, setBoardErr] = useState(false)
  const [detail, setDetail] = useState<OffseasonTeamDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailErr, setDetailErr] = useState(false)

  const view = params.get('view') === 'league' ? 'league' : 'team'

  // Load the league board once.
  useEffect(() => {
    getOffseasonBoard()
      .then((rows) => setBoard(rows))
      .catch(() => setBoardErr(true))
  }, [])

  // Resolve the selected team: ?team=ABBR, else the top-ranked team.
  const selected = useMemo(() => {
    if (!board?.length) return null
    const abbr = params.get('team')?.toUpperCase()
    return board.find((r) => r.team_abbrev === abbr)
      ?? [...board].sort((a, b) => (a.projected_rank ?? 99) - (b.projected_rank ?? 99))[0]
  }, [board, params])

  const selectTeam = (teamId: number, toTeamView = false) => {
    const row = board?.find((r) => r.team_id === teamId)
    const next = new URLSearchParams(params)
    if (row?.team_abbrev) next.set('team', row.team_abbrev)
    if (toTeamView) next.set('view', 'team')
    setParams(next, { replace: true })
  }
  const setView = (v: string) => {
    const next = new URLSearchParams(params)
    if (v === 'league') next.set('view', 'league'); else next.delete('view')
    setParams(next, { replace: true })
  }

  // Team color wash follows the selected team.
  useEffect(() => {
    if (selected?.team_abbrev) setTeamPrimaryColor(getTeamColor(selected.team_abbrev))
    return () => clearTeamPrimaryColor()
  }, [selected?.team_abbrev])

  const loadDetail = (teamId: number) => {
    setDetailLoading(true); setDetailErr(false)
    getTeamOffseason(teamId)
      .then((d) => setDetail(d))
      .catch(() => setDetailErr(true))
      .finally(() => setDetailLoading(false))
  }
  useEffect(() => {
    if (view !== 'team' || !selected) return
    loadDetail(selected.team_id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, selected?.team_id])

  const teamOptions = useMemo(
    () => ALL_TEAMS.map((t) => ({ value: String(t.id), label: `${t.abbrev} — ${getTeamName(t.abbrev)}` })),
    [])

  return (
    <PageLayout>
      <div className="off">
        <div className="off__head">
          <div>
            <h1 className="off__title mono">Offseason Forecast</h1>
            <p className="off__desc">
              How good each team projects next season from the moves it has made — value over last
              season's roster, with the model's honest uncertainty shown throughout.
            </p>
          </div>
          <Tabs value={view} onChange={setView}
            options={[{ value: 'team', label: 'Team' }, { value: 'league', label: 'League' }]} />
        </div>

        {boardErr && <p className="off-msg">The offseason forecast is unavailable right now.</p>}
        {!board && !boardErr && <SkeletonLoader height={360} />}

        {board && view === 'team' && selected && (
          <>
            <header className="fid">
              <span className="fid__wash" aria-hidden />
              <div className="fid__row">
                <img className="fid__logo" src={getTeamLogoUrl(selected.team_abbrev ?? '')} alt="" aria-hidden />
                <span className="fid__name">{getTeamName(selected.team_abbrev ?? '')}</span>
                <span className="fid__pick">
                  <Select ariaLabel="Choose team" value={String(selected.team_id)} options={teamOptions}
                    onChange={(v) => selectTeam(Number(v), true)} />
                </span>
                <button className="fid__edit" onClick={() => { /* TODO: wire to move-entry flow when it exists */ }}>
                  <Pencil size={14} /> Edit moves
                </button>
              </div>
              <p className="fid__context">
                Projected for {nextSeasonOf(selected.transition)} · {selected.n_moves} move{selected.n_moves === 1 ? '' : 's'} logged · updated today
              </p>
              <div className="fid__divider" />
              <ForecastHeroStats f={selected} />
            </header>

            <div className="off-grid">
              <aside className="off-grid__rail">
                <LeagueRail rows={board} selectedId={selected.team_id}
                  onSelect={(id) => selectTeam(id, true)} onSeeAll={() => setView('league')} />
              </aside>
              <div className="off-grid__detail">
                <TeamDetail detail={detail} loading={detailLoading} error={detailErr}
                  onRetry={() => loadDetail(selected.team_id)} />
              </div>
            </div>
          </>
        )}

        {board && view === 'league' && (
          <section className="off-league">
            <div className="off-league__head">
              <h2 className="off-league__title">Projected standings, {nextSeasonOf(board[0]?.transition ?? '')}</h2>
              <p className="off-league__sub">All 32 teams by projected rating. Select a team for its full forecast.</p>
            </div>
            <OffseasonLeagueTable rows={board} onSelect={(id) => selectTeam(id, true)} />
          </section>
        )}
      </div>
    </PageLayout>
  )
}
