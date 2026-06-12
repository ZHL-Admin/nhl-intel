import { getTeamLogoUrl } from '../../utils/teams';
import './PeriodGrid.css';

interface PeriodGridProps {
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeStats: {
    gf_p1?: number | null;
    gf_p2?: number | null;
    gf_p3?: number | null;
    score?: number | null;
  };
  awayStats: {
    gf_p1?: number | null;
    gf_p2?: number | null;
    gf_p3?: number | null;
    score?: number | null;
  };
}

export default function PeriodGrid({ homeTeamAbbrev, awayTeamAbbrev, homeStats, awayStats }: PeriodGridProps) {
  return (
    <div className="period-grid">
      <table className="period-grid__table">
        <thead>
          <tr>
            <th className="period-grid__header period-grid__header--team"></th>
            <th className="period-grid__header">1</th>
            <th className="period-grid__header">2</th>
            <th className="period-grid__header">3</th>
            <th className="period-grid__header">T</th>
          </tr>
        </thead>
        <tbody>
          <tr className="period-grid__row">
            <td className="period-grid__team">
              <img
                src={getTeamLogoUrl(awayTeamAbbrev)}
                alt={awayTeamAbbrev}
                className="period-grid__logo"
              />
              <span className="period-grid__abbrev">{awayTeamAbbrev}</span>
            </td>
            <td className="period-grid__value mono">{awayStats.gf_p1 ?? '—'}</td>
            <td className="period-grid__value mono">{awayStats.gf_p2 ?? '—'}</td>
            <td className="period-grid__value mono">{awayStats.gf_p3 ?? '—'}</td>
            <td className="period-grid__value period-grid__value--total mono">{awayStats.score ?? '—'}</td>
          </tr>
          <tr className="period-grid__row">
            <td className="period-grid__team">
              <img
                src={getTeamLogoUrl(homeTeamAbbrev)}
                alt={homeTeamAbbrev}
                className="period-grid__logo"
              />
              <span className="period-grid__abbrev">{homeTeamAbbrev}</span>
            </td>
            <td className="period-grid__value mono">{homeStats.gf_p1 ?? '—'}</td>
            <td className="period-grid__value mono">{homeStats.gf_p2 ?? '—'}</td>
            <td className="period-grid__value mono">{homeStats.gf_p3 ?? '—'}</td>
            <td className="period-grid__value period-grid__value--total mono">{homeStats.score ?? '—'}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
