/**
 * DivisionStandings (Blueprint 2.6) — the standings the way fans parse the league: four division
 * tables (2×2 on desktop), each ranked with record + points, and the R9 playoff-cut line drawn after
 * the third team. Below, the wildcard race per conference. Frontend-only over getStandings.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { SkeletonLoader } from '../common'
import { getStandings } from '../../api/teams'
import { getTeamLogoUrl } from '../../utils/teams'
import type { StandingsRow } from '../../api/types'
import './DivisionStandings.css'

const DIVISION_ORDER = ['Atlantic', 'Metropolitan', 'Central', 'Pacific']
const CUT_RANK = 3 // top 3 per division make the playoffs

function Row({ t }: { t: StandingsRow }) {
  return (
    <Link to={`/teams/${t.team_id}`} className={`div-standings__row${t.division_rank === CUT_RANK ? ' is-cut' : ''}`}>
      <span className="div-standings__rank mono">{t.division_rank ?? '—'}</span>
      <img className="div-standings__logo" src={getTeamLogoUrl(t.team_abbrev)} alt="" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
      <span className="div-standings__abbrev">{t.team_abbrev}</span>
      <span className="div-standings__record mono">{t.wins}-{t.losses}-{t.otl}</span>
      <span className="div-standings__pts mono">{t.points}</span>
    </Link>
  )
}

export default function DivisionStandings() {
  const [rows, setRows] = useState<StandingsRow[] | null>(null)
  useEffect(() => { getStandings().then(setRows).catch(() => setRows([])) }, [])

  if (!rows) return <SkeletonLoader height={320} />
  if (rows.length === 0) return <p className="div-standings__empty">Standings aren’t available yet.</p>

  const divisions = DIVISION_ORDER.filter((d) => rows.some((r) => r.division === d))
  const extras = Array.from(new Set(rows.map((r) => r.division).filter((d): d is string => !!d && !divisions.includes(d))))
  const allDivs = [...divisions, ...extras]

  // Wildcard race: non-top-3 teams per conference, ranked by wildcard_rank, first two are "in".
  const conferences = Array.from(new Set(rows.map((r) => r.conference).filter((c): c is string => !!c)))

  return (
    <div className="div-standings">
      <div className="div-standings__grid">
        {allDivs.map((div) => {
          const teams = rows.filter((r) => r.division === div).sort((a, b) => (a.division_rank ?? 99) - (b.division_rank ?? 99))
          return (
            <section key={div} className="div-standings__table">
              <h3 className="page-region-title">{div}</h3>
              <div className="div-standings__rows">
                {teams.map((t) => <Row key={t.team_abbrev} t={t} />)}
              </div>
            </section>
          )
        })}
      </div>

      {conferences.length > 0 && (
        <div className="div-standings__wildcards">
          {conferences.map((conf) => {
            const wc = rows
              .filter((r) => r.conference === conf && (r.division_rank ?? 99) > CUT_RANK && r.wildcard_rank != null)
              .sort((a, b) => (a.wildcard_rank ?? 99) - (b.wildcard_rank ?? 99))
              .slice(0, 5)
            if (wc.length === 0) return null
            return (
              <section key={conf} className="div-standings__table">
                <h3 className="page-region-title">{conf} wild card</h3>
                <div className="div-standings__rows">
                  {wc.map((t) => (
                    <Link key={t.team_abbrev} to={`/teams/${t.team_id}`} className={`div-standings__row${t.wildcard_rank === 2 ? ' is-cut' : ''}`}>
                      <span className="div-standings__rank mono">WC{t.wildcard_rank}</span>
                      <img className="div-standings__logo" src={getTeamLogoUrl(t.team_abbrev)} alt="" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
                      <span className="div-standings__abbrev">{t.team_abbrev}</span>
                      <span className="div-standings__record mono">{t.wins}-{t.losses}-{t.otl}</span>
                      <span className="div-standings__pts mono">{t.points}</span>
                    </Link>
                  ))}
                </div>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
