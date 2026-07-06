import ChartPanel from '../common/ChartPanel';
import { composePeriodInsight } from '../../config/periodInsights';
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

  periods.forEach(p => {
    if (p.homeCF !== null && p.homeCF !== undefined && p.awayCF !== null && p.awayCF !== undefined) {
      const gap = Math.abs(p.homeCF - p.awayCF);
      if (gap > maxGap) { maxGap = gap; maxGapPeriod = p.period; }
    }
  });

  if (maxGap < 0.1) {
    return `${homeTeamAbbrev} and ${awayTeamAbbrev} maintained consistent possession across all periods`;
  }

  // F6: score-aware headline via config/periodInsights. Score ENTERING the max-gap period, from the
  // per-period goals-for/against (home perspective). The CF% shown is the period's own CF%, not the gap.
  const n = (v?: number | null) => v ?? 0;
  const gf = (s: typeof homeStats, p: number) => n(s[`gf_p${p}` as keyof typeof s] as number | null);
  const ga = (s: typeof homeStats, p: number) => n(s[`ga_p${p}` as keyof typeof s] as number | null);
  let homeGoalsBefore = 0, awayGoalsBefore = 0;
  for (let p = 1; p < maxGapPeriod; p++) { homeGoalsBefore += gf(homeStats, p); awayGoalsBefore += ga(homeStats, p); }
  const cf = (s: typeof homeStats) => n(s[`cf_pct_p${maxGapPeriod}` as keyof typeof s] as number | null);
  return composePeriodInsight({
    period: maxGapPeriod as 1 | 2 | 3,
    homeAbbrev: homeTeamAbbrev,
    awayAbbrev: awayTeamAbbrev,
    homeCfPct: cf(homeStats),
    awayCfPct: cf(awayStats),
    homeGoalsBefore,
    awayGoalsBefore,
  });
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

  const fmtCF = (stats: typeof homeStats, period: number) => {
    const v = getStatForPeriod(stats, 'cf_pct', period);
    return v !== null && v !== undefined ? (v as number * 100).toFixed(1) + '%' : '—';
  };
  const fmtXGF = (stats: typeof homeStats, period: number) => {
    const v = calculateXgfPct(
      getStatForPeriod(stats, 'xgf', period) as number,
      getStatForPeriod(stats, 'xga', period) as number
    );
    return v !== null ? v + '%' : '—';
  };
  const fmtTotalCF = (cf: number | null | undefined) =>
    cf !== null && cf !== undefined ? (cf * 100).toFixed(1) + '%' : '—';
  const fmtTotalXGF = (xgf: number, xga: number) => {
    const v = calculateXgfPct(xgf, xga);
    return v !== null ? v + '%' : '—';
  };

  const awaySwatch = `color-mix(in srgb, ${awayTeamColor} 50%, var(--color-bg-base))`;
  const homeSwatch = `color-mix(in srgb, ${homeTeamColor} 50%, var(--color-bg-base))`;

  return (
    <ChartPanel
      title={title}
      subtitle="Period-by-period statistical breakdown"
      expandable={false}
      autoHeight
    >
      <div className="period-breakdown">
        <table className="period-table period-table--combined">
          {/* Item 3: tint alternate stat groups so each pair (away+home) reads as one column group. */}
          <colgroup>
            <col />
            <col span={2} className="period-col--grp" />
            <col span={2} />
            <col span={2} className="period-col--grp" />
          </colgroup>
          <thead>
            <tr>
              <th rowSpan={2} className="period-table__period">Period</th>
              <th colSpan={2}>CF%</th>
              <th colSpan={2}>xGF%</th>
              <th colSpan={2}>Goals</th>
            </tr>
            <tr>
              <th><span className="period-table__swatch" style={{ background: awaySwatch }} />{awayTeamAbbrev}</th>
              <th><span className="period-table__swatch" style={{ background: homeSwatch }} />{homeTeamAbbrev}</th>
              <th><span className="period-table__swatch" style={{ background: awaySwatch }} />{awayTeamAbbrev}</th>
              <th><span className="period-table__swatch" style={{ background: homeSwatch }} />{homeTeamAbbrev}</th>
              <th><span className="period-table__swatch" style={{ background: awaySwatch }} />{awayTeamAbbrev}</th>
              <th><span className="period-table__swatch" style={{ background: homeSwatch }} />{homeTeamAbbrev}</th>
            </tr>
          </thead>
          <tbody>
            {periods.map(p => (
              <tr key={p.period}>
                <td className="period-table__period">{p.label}</td>
                <td className="mono">{fmtCF(awayStats, p.period)}</td>
                <td className="mono">{fmtCF(homeStats, p.period)}</td>
                <td className="mono">{fmtXGF(awayStats, p.period)}</td>
                <td className="mono">{fmtXGF(homeStats, p.period)}</td>
                <td className="mono">{getStatForPeriod(awayStats, 'gf', p.period) ?? '—'}</td>
                <td className="mono">{getStatForPeriod(homeStats, 'gf', p.period) ?? '—'}</td>
              </tr>
            ))}
            <tr className="period-table__total">
              <td className="period-table__period">Final</td>
              <td className="mono">{fmtTotalCF(awayStats.cf_pct)}</td>
              <td className="mono">{fmtTotalCF(homeStats.cf_pct)}</td>
              <td className="mono">{fmtTotalXGF(totalAwayXgf, totalAwayXga)}</td>
              <td className="mono">{fmtTotalXGF(totalHomeXgf, totalHomeXga)}</td>
              <td className="mono">{(awayStats.gf_p1 || 0) + (awayStats.gf_p2 || 0) + (awayStats.gf_p3 || 0)}</td>
              <td className="mono">{(homeStats.gf_p1 || 0) + (homeStats.gf_p2 || 0) + (homeStats.gf_p3 || 0)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </ChartPanel>
  );
}
