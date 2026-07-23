import { useEffect, useState } from 'react'
import Shell from '../shell/Shell'
import { getRatings, type RatingsPayload } from '../../api/rankings'
import { getTeamColor, getTeamName } from '../../utils/teams'
import { fmtSigned, fmtLuck, fmtStamp } from './ratingsFormat'
import './ratings.css'

/**
 * Power Ratings (§3.4) — the site's KenPom table. One table, all 32 teams,
 * backed by GET /ratings. The stamp reads "DATA THROUGH <date>" (recency from
 * MAX(game_date)), not "LAST RUN".
 */
export default function Ratings() {
  const [data, setData] = useState<RatingsPayload | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    document.title = 'Power Ratings · Rink Theory'
    getRatings().then(setData).catch(() => setError(true))
  }, [])

  return (
    <Shell>
      <h1 className="rt-pagetitle">Power Ratings</h1>
      <p className="rt-stamp">
        Updated nightly · {data?.data_through ? `Data through ${fmtStamp(data.data_through)}` : '…'}
      </p>
      <p className="rt-intro">
        One number per team, built from how each club actually plays rather than how its results have
        bounced. The last column is the gap between the real standings and a re-simulated season.
      </p>

      {error && <p className="rt-intro">Ratings are unavailable right now.</p>}

      {data && (
        <table className="rt-rttable">
          <thead>
            <tr>
              <th className="rk">Rk</th>
              <th className="team">Team</th>
              <th>Rating</th>
              <th>5v5 Play</th>
              <th>Finishing</th>
              <th>Goalie</th>
              <th>Spec. Teams</th>
              <th>Luck</th>
              <th className="pad" />
            </tr>
          </thead>
          <tbody>
            {data.teams.map((t) => {
              const abbr = t.team_abbrev ?? ''
              const luckClass = t.luck == null ? '' : t.luck >= 0 ? 'ahead' : 'behind'
              return (
                <tr key={t.team_id}>
                  <td className="rk">{t.rank}</td>
                  <td className="team">
                    <span className="rt-team">
                      <span className="rt-team__dot" style={{ background: getTeamColor(abbr) }} />
                      <span className="rt-team__name">{getTeamName(abbr) || abbr}</span>
                    </span>
                  </td>
                  <td className="rating">{fmtSigned(t.rating)}</td>
                  <td className="comp">{fmtSigned(t.comp_5v5)}</td>
                  <td className="comp">{fmtSigned(t.comp_finishing)}</td>
                  <td className="comp">{fmtSigned(t.comp_goaltending)}</td>
                  <td className="comp">{fmtSigned(t.comp_special_teams)}</td>
                  <td className={`luck ${luckClass}`}>{fmtLuck(t.luck)}</td>
                  <td className="pad" />
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      <p className="rt-tablenote">
        Luck in points vs the deserved record. Orange = results ahead of the play, blue = behind.
      </p>
    </Shell>
  )
}
