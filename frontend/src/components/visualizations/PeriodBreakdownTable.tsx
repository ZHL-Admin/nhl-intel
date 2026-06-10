import ChartPanel from '../common/ChartPanel';
import './PeriodBreakdownTable.css';

interface PeriodBreakdownTableProps {
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeTeamColor: string;
  awayTeamColor: string;
  homeStats: {
    cf_pct_p1?: number | null;
    cf_pct_p2?: number | null;
    cf_pct_p3?: number | null;
    xgf_p1?: number | null;
    xgf_p2?: number | null;
    xgf_p3?: number | null;
    xga_p1?: number | null;
    xga_p2?: number | null;
    xga_p3?: number | null;
    gf_p1?: number | null;
    gf_p2?: number | null;
    gf_p3?: number | null;
    ga_p1?: number | null;
    ga_p2?: number | null;
    ga_p3?: number | null;
    cf_pct?: number | null;
    xgf?: number | null;
    xga?: number | null;
  };
  awayStats: {
    cf_pct_p1?: number | null;
    cf_pct_p2?: number | null;
    cf_pct_p3?: number | null;
    xgf_p1?: number | null;
    xgf_p2?: number | null;
    xgf_p3?: number | null;
    xga_p1?: number | null;
    xga_p2?: number | null;
    xga_p3?: number | null;
    gf_p1?: number | null;
    gf_p2?: number | null;
    gf_p3?: number | null;
    ga_p1?: number | null;
    ga_p2?: number | null;
    ga_p3?: number | null;
    cf_pct?: number | null;
    xgf?: number | null;
    xga?: number | null;
  };
}

function generateTitle(
  homeStats: PeriodBreakdownTableProps['homeStats'],
  awayStats: PeriodBreakdownTableProps['awayStats'],
  homeTeamAbbrev: string,
  awayTeamAbbrev: string
): string {
  // Find period with largest CF% gap
  const periods = [
    { period: 1, homeCF: homeStats.cf_pct_p1, awayCF: awayStats.cf_pct_p1 },
    { period: 2, homeCF: homeStats.cf_pct_p2, awayCF: awayStats.cf_pct_p2 },
    { period: 3, homeCF: homeStats.cf_pct_p3, awayCF: awayStats.cf_pct_p3 },
  ];

  let maxGap = 0;
  let maxGapPeriod = 1;
  let dominantTeam = homeTeamAbbrev;

  periods.forEach(p => {
    if (p.homeCF !== null && p.homeCF !== undefined && p.awayCF !== null && p.awayCF !== undefined) {
      const gap = Math.abs(p.homeCF - p.awayCF);
      if (gap > maxGap) {
        maxGap = gap;
        maxGapPeriod = p.period;
        dominantTeam = p.homeCF > p.awayCF ? homeTeamAbbrev : awayTeamAbbrev;
      }
    }
  });

  if (maxGap < 0.1) {
    return `${homeTeamAbbrev} and ${awayTeamAbbrev} maintained consistent possession across all periods`;
  }

  const periodName = maxGapPeriod === 1 ? 'first' : maxGapPeriod === 2 ? 'second' : 'third';
  const cfPct = Math.round(maxGap * 100);

  return `${dominantTeam} took control in the ${periodName} period with ${cfPct}% CF advantage`;
}

export default function PeriodBreakdownTable(props: PeriodBreakdownTableProps) {
  const { homeTeamAbbrev, awayTeamAbbrev, homeTeamColor, awayTeamColor, homeStats, awayStats } = props;

  const title = generateTitle(homeStats, awayStats, homeTeamAbbrev, awayTeamAbbrev);

  const periods = [
    { label: 'P1', period: 1 },
    { label: 'P2', period: 2 },
    { label: 'P3', period: 3 },
  ];

  const getStatForPeriod = (stats: typeof homeStats, stat: string, period: number) => {
    const key = `${stat}_p${period}` as keyof typeof stats;
    return stats[key];
  };

  const calculateXgfPct = (xgf: number | null | undefined, xga: number | null | undefined) => {
    if (xgf === null || xgf === undefined || xga === null || xga === undefined) return null;
    if (xgf + xga === 0) return null;
    return ((xgf / (xgf + xga)) * 100).toFixed(1);
  };

  const totalHomeXgf = (homeStats.xgf_p1 || 0) + (homeStats.xgf_p2 || 0) + (homeStats.xgf_p3 || 0);
  const totalHomeXga = (homeStats.xga_p1 || 0) + (homeStats.xga_p2 || 0) + (homeStats.xga_p3 || 0);
  const totalAwayXgf = (awayStats.xgf_p1 || 0) + (awayStats.xgf_p2 || 0) + (awayStats.xgf_p3 || 0);
  const totalAwayXga = (awayStats.xga_p1 || 0) + (awayStats.xga_p2 || 0) + (awayStats.xga_p3 || 0);

  return (
    <ChartPanel
      sectionNumber="04"
      title={title}
      subtitle="Period-by-period statistical breakdown"
      expandable={false}
    >
      <div className="period-breakdown">
        <div className="period-breakdown__tables">
          {/* Away Team Table */}
          <div className="period-breakdown__table">
            <div
              className="period-breakdown__table-header"
              style={{ backgroundColor: `${awayTeamColor}1A` }}
            >
              {awayTeamAbbrev}
            </div>
            <table className="period-table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th>CF%</th>
                  <th>xGF%</th>
                  <th>GF</th>
                  <th>GA</th>
                </tr>
              </thead>
              <tbody>
                {periods.map(p => (
                  <tr key={p.period}>
                    <td className="period-table__period">{p.label}</td>
                    <td className="mono">
                      {getStatForPeriod(awayStats, 'cf_pct', p.period) !== null &&
                      getStatForPeriod(awayStats, 'cf_pct', p.period) !== undefined
                        ? ((getStatForPeriod(awayStats, 'cf_pct', p.period) as number) * 100).toFixed(1) + '%'
                        : '-'}
                    </td>
                    <td className="mono">
                      {calculateXgfPct(
                        getStatForPeriod(awayStats, 'xgf', p.period) as number,
                        getStatForPeriod(awayStats, 'xga', p.period) as number
                      ) !== null
                        ? calculateXgfPct(
                            getStatForPeriod(awayStats, 'xgf', p.period) as number,
                            getStatForPeriod(awayStats, 'xga', p.period) as number
                          ) + '%'
                        : '-'}
                    </td>
                    <td className="mono">{getStatForPeriod(awayStats, 'gf', p.period) ?? '-'}</td>
                    <td className="mono">{getStatForPeriod(awayStats, 'ga', p.period) ?? '-'}</td>
                  </tr>
                ))}
                <tr className="period-table__total">
                  <td className="period-table__period">Final</td>
                  <td className="mono">
                    {awayStats.cf_pct !== null && awayStats.cf_pct !== undefined ? (awayStats.cf_pct * 100).toFixed(1) + '%' : '-'}
                  </td>
                  <td className="mono">
                    {calculateXgfPct(totalAwayXgf, totalAwayXga) !== null
                      ? calculateXgfPct(totalAwayXgf, totalAwayXga) + '%'
                      : '-'}
                  </td>
                  <td className="mono">
                    {(awayStats.gf_p1 || 0) + (awayStats.gf_p2 || 0) + (awayStats.gf_p3 || 0)}
                  </td>
                  <td className="mono">
                    {(awayStats.ga_p1 || 0) + (awayStats.ga_p2 || 0) + (awayStats.ga_p3 || 0)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Home Team Table */}
          <div className="period-breakdown__table">
            <div
              className="period-breakdown__table-header"
              style={{ backgroundColor: `${homeTeamColor}1A` }}
            >
              {homeTeamAbbrev}
            </div>
            <table className="period-table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th>CF%</th>
                  <th>xGF%</th>
                  <th>GF</th>
                  <th>GA</th>
                </tr>
              </thead>
              <tbody>
                {periods.map(p => (
                  <tr key={p.period}>
                    <td className="period-table__period">{p.label}</td>
                    <td className="mono">
                      {getStatForPeriod(homeStats, 'cf_pct', p.period) !== null &&
                      getStatForPeriod(homeStats, 'cf_pct', p.period) !== undefined
                        ? ((getStatForPeriod(homeStats, 'cf_pct', p.period) as number) * 100).toFixed(1) + '%'
                        : '-'}
                    </td>
                    <td className="mono">
                      {calculateXgfPct(
                        getStatForPeriod(homeStats, 'xgf', p.period) as number,
                        getStatForPeriod(homeStats, 'xga', p.period) as number
                      ) !== null
                        ? calculateXgfPct(
                            getStatForPeriod(homeStats, 'xgf', p.period) as number,
                            getStatForPeriod(homeStats, 'xga', p.period) as number
                          ) + '%'
                        : '-'}
                    </td>
                    <td className="mono">{getStatForPeriod(homeStats, 'gf', p.period) ?? '-'}</td>
                    <td className="mono">{getStatForPeriod(homeStats, 'ga', p.period) ?? '-'}</td>
                  </tr>
                ))}
                <tr className="period-table__total">
                  <td className="period-table__period">Final</td>
                  <td className="mono">
                    {homeStats.cf_pct !== null && homeStats.cf_pct !== undefined ? (homeStats.cf_pct * 100).toFixed(1) + '%' : '-'}
                  </td>
                  <td className="mono">
                    {calculateXgfPct(totalHomeXgf, totalHomeXga) !== null
                      ? calculateXgfPct(totalHomeXgf, totalHomeXga) + '%'
                      : '-'}
                  </td>
                  <td className="mono">
                    {(homeStats.gf_p1 || 0) + (homeStats.gf_p2 || 0) + (homeStats.gf_p3 || 0)}
                  </td>
                  <td className="mono">
                    {(homeStats.ga_p1 || 0) + (homeStats.ga_p2 || 0) + (homeStats.ga_p3 || 0)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </ChartPanel>
  );
}
