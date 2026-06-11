import { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell } from 'recharts';
import ChartPanel from '../common/ChartPanel';
import Tabs from '../common/Tabs';
import PossessionBar from '../common/PossessionBar';
import Badge from '../common/Badge';
import Tooltip from '../common/Tooltip';
import { getTeamSituational } from '../../api/teams';
import { TeamSituational } from '../../api/types';
import './TeamComparisonPanel.css';

interface TeamComparisonPanelProps {
  gameId: number;
  homeTeamId: number;
  awayTeamId: number;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeTeamColor: string;
  awayTeamColor: string;
  situation: string;
  onSituationChange: (situation: string) => void;
  // Default data from game detail for 'all' situation
  homeTeamStats: {
    cf_pct: number | null;
    xgf: number | null;
    xga: number | null;
    hdcf_per60: number | null;
    hdca_per60: number | null;
    zone_entry_success_rate: number | null;
    shot_attempts: number | null;
    gf_p1?: number | null;
    gf_p2?: number | null;
    gf_p3?: number | null;
    ga_p1?: number | null;
    ga_p2?: number | null;
    ga_p3?: number | null;
  };
  awayTeamStats: {
    cf_pct: number | null;
    xgf: number | null;
    xga: number | null;
    hdcf_per60: number | null;
    hdca_per60: number | null;
    zone_entry_success_rate: number | null;
    shot_attempts: number | null;
    gf_p1?: number | null;
    gf_p2?: number | null;
    gf_p3?: number | null;
    ga_p1?: number | null;
    ga_p2?: number | null;
    ga_p3?: number | null;
  };
}

export default function TeamComparisonPanel({
  gameId,
  homeTeamId,
  awayTeamId,
  homeTeamAbbrev: _homeTeamAbbrev,
  awayTeamAbbrev: _awayTeamAbbrev,
  homeTeamColor,
  awayTeamColor,
  homeTeamStats,
  awayTeamStats,
  situation,
  onSituationChange
}: TeamComparisonPanelProps) {
  const [homeSituational, setHomeSituational] = useState<TeamSituational[]>([]);
  const [awaySituational, setAwaySituational] = useState<TeamSituational[]>([]);

  useEffect(() => {
    if (situation === 'all') {
      // Use the default data passed as props
      return;
    }

    const fetchSituational = async () => {
      try {
        const [homeData, awayData] = await Promise.all([
          getTeamSituational(homeTeamId, gameId),
          getTeamSituational(awayTeamId, gameId)
        ]);
        setHomeSituational(homeData);
        setAwaySituational(awayData);
      } catch (err) {
        console.error('Error fetching situational data:', err);
      }
    };

    fetchSituational();
  }, [situation, homeTeamId, awayTeamId, gameId]);

  // Get current situation's stats
  const getCurrentStats = () => {
    if (situation === 'all') {
      return { home: homeTeamStats, away: awayTeamStats };
    }

    const homeSit = homeSituational.find(s => s.situation === situation);
    const awaySit = awaySituational.find(s => s.situation === situation);

    return {
      home: homeSit || homeTeamStats,
      away: awaySit || awayTeamStats
    };
  };

  const { home: currentHome, away: currentAway } = getCurrentStats();

  // Calculate xGF%
  const homeXgfPct = currentHome.xgf && currentHome.xga
    ? (currentHome.xgf / (currentHome.xgf + currentHome.xga)) * 100
    : null;
  const awayXgfPct = currentAway.xgf && currentAway.xga
    ? (currentAway.xgf / (currentAway.xgf + currentAway.xga)) * 100
    : null;

  // Period goals data for bar chart - only available when situation === 'all'
  const periodData = situation === 'all' ? [
    {
      period: 'P1',
      away: ('gf_p1' in currentAway ? currentAway.gf_p1 : null) || 0,
      home: ('gf_p1' in currentHome ? currentHome.gf_p1 : null) || 0
    },
    {
      period: 'P2',
      away: ('gf_p2' in currentAway ? currentAway.gf_p2 : null) || 0,
      home: ('gf_p2' in currentHome ? currentHome.gf_p2 : null) || 0
    },
    {
      period: 'P3',
      away: ('gf_p3' in currentAway ? currentAway.gf_p3 : null) || 0,
      home: ('gf_p3' in currentHome ? currentHome.gf_p3 : null) || 0
    }
  ] : [];

  // Calculate PDO (simplified - would need actual shooting % and save %)
  const homePDO = 1.000; // Placeholder
  const awayPDO = 1.000; // Placeholder

  return (
    <ChartPanel
      title="Team Comparison"
      subtitle="How each team performed across all metrics"
      expandable={false}
      footer={
        <Tabs
          options={[
            { value: 'all', label: 'All' },
            { value: '5v5', label: '5v5' },
            { value: 'ev', label: 'EV' },
            { value: 'pp', label: 'PP' },
            { value: 'pk', label: 'PK' },
          ]}
          value={situation}
          onChange={onSituationChange}
        />
      }
    >
      <div className="team-comparison">
        {/* Group 1: Who controlled the puck? */}
        <div className="team-comparison__group">
          <h4 className="team-comparison__group-title">Who controlled the puck?</h4>

          {/* CF% */}
          {currentHome.cf_pct !== null && currentAway.cf_pct !== null && (
            <div className="team-comparison__metric">
              <div className="team-comparison__metric-label">
                <Tooltip content="Corsi For Percentage - shot attempts for divided by total shot attempts">
                  CF%
                </Tooltip>
              </div>
              <PossessionBar
                homeValue={(currentHome.cf_pct ?? 0) * 100}
                awayValue={(currentAway.cf_pct ?? 0) * 100}
                homeColor={homeTeamColor}
                awayColor={awayTeamColor}
              />
            </div>
          )}

          {/* xGF% */}
          {homeXgfPct !== null && awayXgfPct !== null && (
            <div className="team-comparison__metric">
              <div className="team-comparison__metric-label">
                <Tooltip content="Expected Goals For Percentage - expected goals for divided by total expected goals">
                  xGF%
                </Tooltip>
              </div>
              <PossessionBar
                homeValue={homeXgfPct}
                awayValue={awayXgfPct}
                homeColor={homeTeamColor}
                awayColor={awayTeamColor}
              />
            </div>
          )}
        </div>

        {/* Group 2: Where did the danger come from? */}
        <div className="team-comparison__group">
          <h4 className="team-comparison__group-title">Where did the danger come from?</h4>

          <div className="team-comparison__side-by-side-metrics">
            {/* HDCF/60 */}
            {currentHome.hdcf_per60 !== null && currentAway.hdcf_per60 !== null && (
              <div className="team-comparison__stat-row">
                <div className="team-comparison__stat-label">
                  <Tooltip content="High Danger Chances For per 60 minutes">
                    HDCF/60
                  </Tooltip>
                </div>
                <div className="team-comparison__stat-values">
                  <span className="mono">{(currentAway.hdcf_per60 ?? 0).toFixed(1)}</span>
                  <span className="mono">{(currentHome.hdcf_per60 ?? 0).toFixed(1)}</span>
                </div>
              </div>
            )}

            {/* HDCA/60 */}
            {currentHome.hdca_per60 !== null && currentAway.hdca_per60 !== null && (
              <div className="team-comparison__stat-row">
                <div className="team-comparison__stat-label">
                  <Tooltip content="High Danger Chances Against per 60 minutes">
                    HDCA/60
                  </Tooltip>
                </div>
                <div className="team-comparison__stat-values">
                  <span className="mono">{(currentAway.hdca_per60 ?? 0).toFixed(1)}</span>
                  <span className="mono">{(currentHome.hdca_per60 ?? 0).toFixed(1)}</span>
                </div>
              </div>
            )}

            {/* Zone Entry Success Rate */}
            {currentHome.zone_entry_success_rate !== null && currentAway.zone_entry_success_rate !== null && (
              <div className="team-comparison__stat-row">
                <div className="team-comparison__stat-label">
                  <Tooltip content="Percentage of zone entries that were controlled (with possession)">
                    Zone Entry %
                  </Tooltip>
                </div>
                <div className="team-comparison__stat-values">
                  <span className="mono">{((currentAway.zone_entry_success_rate ?? 0) * 100).toFixed(1)}%</span>
                  <span className="mono">{((currentHome.zone_entry_success_rate ?? 0) * 100).toFixed(1)}%</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Group 3: What actually happened? */}
        <div className="team-comparison__group">
          <h4 className="team-comparison__group-title">What actually happened?</h4>

          {/* Goals by period bar chart - only shown when situation is 'all' */}
          {situation === 'all' && periodData.length > 0 && (
            <div className="team-comparison__period-chart">
              <div className="team-comparison__stat-label">Goals by Period</div>
              <ResponsiveContainer width="100%" height={100}>
                <BarChart data={periodData} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                  <XAxis dataKey="period" stroke="var(--color-text-secondary)" tick={{ fontSize: 11 }} />
                  <YAxis hide tickFormatter={(value) => Math.round(value).toString()} />
                  <Bar dataKey="away" fill={awayTeamColor} radius={[4, 4, 0, 0]}>
                    {periodData.map((_, index) => (
                      <Cell key={`away-${index}`} fill={awayTeamColor} opacity={0.8} />
                    ))}
                  </Bar>
                  <Bar dataKey="home" fill={homeTeamColor} radius={[4, 4, 0, 0]}>
                    {periodData.map((_, index) => (
                      <Cell key={`home-${index}`} fill={homeTeamColor} opacity={0.8} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* PDO */}
          <div className="team-comparison__stat-row">
            <div className="team-comparison__stat-label">
              <Tooltip content="PDO measures shooting percentage plus save percentage. Values above 1.000 often reflect good luck and tend to regress toward average over time.">
                PDO <Badge variant="luck" />
              </Tooltip>
            </div>
            <div className="team-comparison__stat-values">
              <span className="mono">{awayPDO.toFixed(3)}</span>
              <span className="mono">{homePDO.toFixed(3)}</span>
            </div>
          </div>
        </div>
      </div>
    </ChartPanel>
  );
}
