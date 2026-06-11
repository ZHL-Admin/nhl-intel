import { useState } from 'react';
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { Moon, Sun } from 'lucide-react';
import ChartPanel, { useChartPanelHeight } from '../components/common/ChartPanel';
import StatCard from '../components/common/StatCard';
import Badge from '../components/common/Badge';
import Tabs from '../components/common/Tabs';
import PageLayout from '../components/common/PageLayout';
import TabNav from '../components/common/TabNav';
import ComparisonRow from '../components/common/ComparisonRow';
import IdentityHeader from '../components/common/IdentityHeader';
import TimelineList, { TimelineGroup } from '../components/common/TimelineList';
import PodiumCards, { PodiumPlayer } from '../components/common/PodiumCards';
import DateStrip, { GameDate } from '../components/common/DateStrip';
import MiniWorm from '../components/common/MiniWorm';

// Sample data for charts
const sampleChartData = [
  { name: 'Game 1', value: 52 },
  { name: 'Game 2', value: 48 },
  { name: 'Game 3', value: 55 },
  { name: 'Game 4', value: 51 },
  { name: 'Game 5', value: 58 },
  { name: 'Game 6', value: 53 },
  { name: 'Game 7', value: 56 },
  { name: 'Game 8', value: 49 },
  { name: 'Game 9', value: 54 },
  { name: 'Game 10', value: 60 },
];

function SampleChart() {
  const height = useChartPanelHeight();

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={sampleChartData}>
        <XAxis dataKey="name" />
        <YAxis />
        <Line type="monotone" dataKey="value" stroke="var(--color-data-1)" strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default function DevComponents() {
  const [situation, setSituation] = useState('all');
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedDate, setSelectedDate] = useState('2024-03-15');
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  });

  // Sample sparkline data
  const sparklineData = [48, 52, 49, 55, 53, 58, 54, 51, 56, 60];
  const sparklineDataNegative = [60, 58, 55, 53, 50, 48, 46, 44, 42, 40];

  // Sample data for Phase 1 components
  const sampleDates: GameDate[] = [
    { date: '2024-03-13', gameCount: 8 },
    { date: '2024-03-14', gameCount: 12 },
    { date: '2024-03-15', gameCount: 10 },
    { date: '2024-03-16', gameCount: 6 },
    { date: '2024-03-17', gameCount: 11 },
  ];

  const sampleXgData = [
    { time: 0, diff: 0 },
    { time: 300, diff: 0.2 },
    { time: 600, diff: 0.5 },
    { time: 900, diff: 0.3 },
    { time: 1200, diff: -0.1 },
    { time: 1500, diff: -0.3 },
    { time: 1800, diff: 0.1 },
    { time: 2100, diff: 0.4 },
    { time: 2400, diff: 0.6 },
    { time: 2700, diff: 0.8 },
    { time: 3000, diff: 1.1 },
    { time: 3300, diff: 0.9 },
    { time: 3600, diff: 1.2 },
  ];

  const sampleGoals = [
    { time: 600, label: 'Home Goal' },
    { time: 1500, label: 'Away Goal' },
    { time: 2400, label: 'Home Goal' },
    { time: 3300, label: 'Home Goal' },
  ];

  const sampleTimelineGroups: TimelineGroup[] = [
    {
      label: '1st Period',
      items: [
        {
          id: '1',
          leftContent: <div><strong>5:32</strong> • McDavid (Matthews, Marner)</div>,
          rightContent: <div style={{ textAlign: 'right' }}>1-0 TOR</div>,
          accentColor: '#003E7E'
        },
        {
          id: '2',
          leftContent: <div><strong>12:48</strong> • Draisaitl (PP) (Bouchard, Hyman)</div>,
          rightContent: <div style={{ textAlign: 'right' }}>1-1</div>,
          accentColor: '#FF4C00'
        }
      ]
    },
    {
      label: '2nd Period',
      items: [
        {
          id: '3',
          leftContent: <div><strong>3:15</strong> • Nylander (Tavares)</div>,
          rightContent: <div style={{ textAlign: 'right' }}>2-1 TOR</div>,
          accentColor: '#003E7E'
        }
      ]
    }
  ];

  const samplePodiumPlayers: PodiumPlayer[] = [
    {
      playerId: 8478402,
      name: 'Connor McDavid',
      teamAbbrev: 'EDM',
      teamLogo: 'https://assets.nhle.com/logos/nhl/svg/EDM_light.svg',
      position: 'C',
      statLine: '2G, 1A, 3P',
      highlight: 'Game Winner',
      accentColor: '#FF4C00'
    },
    {
      playerId: 8477934,
      name: 'Auston Matthews',
      teamAbbrev: 'TOR',
      teamLogo: 'https://assets.nhle.com/logos/nhl/svg/TOR_light.svg',
      position: 'C',
      statLine: '1G, 2A, 3P',
      accentColor: '#003E7E'
    },
    {
      playerId: 8477492,
      name: 'Leon Draisaitl',
      teamAbbrev: 'EDM',
      teamLogo: 'https://assets.nhle.com/logos/nhl/svg/EDM_light.svg',
      position: 'C',
      statLine: '1G, 1A, 2P',
      accentColor: '#FF4C00'
    }
  ];

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', newTheme);
    setTheme(newTheme);
  };

  return (
    <PageLayout>
      <div style={{ padding: 'var(--space-8)', maxWidth: '1280px', margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-8)' }}>
          <h1>Component Showcase (Dev Only)</h1>
          <button
            onClick={toggleTheme}
            style={{
              background: 'var(--color-bg-elevated)',
              border: 'none',
              borderRadius: 'var(--radius-full)',
              width: '40px',
              height: '40px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: 'var(--color-text-primary)'
            }}
          >
            {theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}
          </button>
        </div>

        {/* Chart Panel Test */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>Chart Panel</h2>
          <ChartPanel
            sectionNumber="01"
            title="Team CF% has improved consistently over the last 10 games"
            subtitle="5-on-5 possession trending upward"
            footer={
              <div>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                  Last updated: Today
                </span>
              </div>
            }
          >
            <SampleChart />
          </ChartPanel>
        </section>

        {/* StatCard Tests */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>Stat Cards</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 'var(--space-4)' }}>
            <StatCard
              label="Corsi For %"
              value="56.2%"
              rank={3}
              tooltip="Percentage of shot attempts taken while this team is on ice"
              sparklineData={sparklineData}
              trendDelta={2.3}
              trendLabel="vs last 5"
            />
            <StatCard
              label="Expected Goals"
              value="2.84"
              rank={15}
              sparklineData={sparklineDataNegative}
              trendDelta={-0.8}
              trendLabel="vs last 5"
            />
            <StatCard
              label="High Danger Chances"
              value="8.5"
              rank={28}
            />
            <StatCard
              label="Save Percentage"
              value=".915"
              rank={12}
              tooltip="Goals saved per shots faced"
            />
          </div>
        </section>

        {/* Badge Tests */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>Badges</h2>
          <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
            <Badge variant="hot" />
            <Badge variant="cold" />
            <Badge variant="preview" />
            <Badge variant="live" />
            <Badge variant="small-sample" />
            <Badge variant="luck" />
            <Badge variant="luck" label="PDO" />
          </div>
        </section>

        {/* Tabs Test */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>Tabs (Situation Filters)</h2>
          <Tabs
            options={[
              { value: 'all', label: 'All' },
              { value: '5v5', label: '5v5' },
              { value: 'pp', label: 'PP' },
              { value: 'pk', label: 'PK' },
            ]}
            value={situation}
            onChange={setSituation}
          />
          <p style={{ marginTop: 'var(--space-4)', color: 'var(--color-text-secondary)' }}>
            Selected: {situation}
          </p>
        </section>

        <hr style={{ border: 'none', borderTop: '2px solid var(--color-border)', margin: 'var(--space-20) 0' }} />
        <h1 style={{ marginBottom: 'var(--space-8)', textAlign: 'center' }}>Phase 1 Foundation Components</h1>

        {/* TabNav Test */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>TabNav (Page-level Navigation)</h2>
          <div style={{ position: 'relative', background: 'var(--color-bg-surface)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4)' }}>
            <TabNav
              tabs={[
                { value: 'overview', label: 'Overview' },
                { value: 'boxscore', label: 'Boxscore' },
                { value: 'shifts', label: 'Shifts' },
                { value: 'plays', label: 'Plays' },
              ]}
              activeTab={activeTab}
              onChange={setActiveTab}
            />
            <p style={{ marginTop: 'var(--space-8)', padding: 'var(--space-4)', color: 'var(--color-text-secondary)' }}>
              Active tab: <strong>{activeTab}</strong>
            </p>
          </div>
        </section>

        {/* ComparisonRow Test */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>ComparisonRow (Two-team Stat Display)</h2>
          <div style={{ background: 'var(--color-bg-surface)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-6)' }}>
            <ComparisonRow
              label="Shots on Goal"
              awayValue={32}
              homeValue={28}
              awayRaw={32}
              homeRaw={28}
              awayColor="#FF4C00"
              homeColor="#003E7E"
            />
            <ComparisonRow
              label="Expected Goals"
              awayValue="2.84"
              homeValue="3.12"
              awayRaw={2.84}
              homeRaw={3.12}
              awayColor="#FF4C00"
              homeColor="#003E7E"
              tooltip="Total xG generated by each team"
            />
            <ComparisonRow
              label="Face-off Win %"
              awayValue="52%"
              homeValue="48%"
              awayColor="#FF4C00"
              homeColor="#003E7E"
              showBar={false}
            />
          </div>
        </section>

        {/* IdentityHeader Test */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>IdentityHeader (Page Headers)</h2>
          <IdentityHeader
            backLink={{ label: 'Back to Games', to: '/' }}
            leftContent={
              <div>
                <img src="https://assets.nhle.com/logos/nhl/svg/EDM_light.svg" alt="EDM" style={{ width: 48, height: 48 }} />
                <div style={{ marginTop: 'var(--space-2)' }}>
                  <div style={{ fontSize: 'var(--text-lg)', fontWeight: 600 }}>Edmonton Oilers</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>Pacific Division</div>
                </div>
              </div>
            }
            centerContent={
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 'var(--text-4xl)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>4 - 3</div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>Final/OT</div>
              </div>
            }
            rightContent={
              <div style={{ textAlign: 'right' }}>
                <img src="https://assets.nhle.com/logos/nhl/svg/TOR_light.svg" alt="TOR" style={{ width: 48, height: 48, marginLeft: 'auto' }} />
                <div style={{ marginTop: 'var(--space-2)' }}>
                  <div style={{ fontSize: 'var(--text-lg)', fontWeight: 600 }}>Toronto Maple Leafs</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>Atlantic Division</div>
                </div>
              </div>
            }
            teamColors={{ away: '#FF4C00', home: '#003E7E' }}
          />
        </section>

        {/* TimelineList Test */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>TimelineList (Scoring, Penalties)</h2>
          <TimelineList groups={sampleTimelineGroups} />
        </section>

        {/* PodiumCards Test */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>PodiumCards (Top Performers)</h2>
          <PodiumCards players={samplePodiumPlayers} title="Three Stars" />
        </section>

        {/* DateStrip Test */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>DateStrip (Date Navigation)</h2>
          <div style={{ background: 'var(--color-bg-surface)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4)' }}>
            <DateStrip
              dates={sampleDates}
              selectedDate={selectedDate}
              onDateChange={setSelectedDate}
              todayDate="2024-03-15"
            />
            <p style={{ marginTop: 'var(--space-4)', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
              Selected: {selectedDate}
            </p>
          </div>
        </section>

        {/* MiniWorm Test */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>MiniWorm (xG Sparkline)</h2>
          <div style={{ background: 'var(--color-bg-surface)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-6)', display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
            <div>
              <h3 style={{ fontSize: 'var(--text-sm)', marginBottom: 'var(--space-3)' }}>Default Size (300x60)</h3>
              <MiniWorm
                data={sampleXgData}
                goals={sampleGoals}
                homeColor="#003E7E"
                awayColor="#FF4C00"
              />
            </div>
            <div>
              <h3 style={{ fontSize: 'var(--text-sm)', marginBottom: 'var(--space-3)' }}>Custom Size (400x80)</h3>
              <MiniWorm
                data={sampleXgData}
                goals={sampleGoals}
                homeColor="#003E7E"
                awayColor="#FF4C00"
                width={400}
                height={80}
              />
            </div>
            <div>
              <h3 style={{ fontSize: 'var(--text-sm)', marginBottom: 'var(--space-3)' }}>Empty State</h3>
              <MiniWorm
                data={[]}
                homeColor="#003E7E"
                awayColor="#FF4C00"
              />
            </div>
          </div>
        </section>

        {/* Page Grid Test */}
        <section style={{ marginBottom: 'var(--space-16)' }}>
          <h2 style={{ marginBottom: 'var(--space-4)' }}>Page Grid & De-carding Utilities</h2>
          <div className="page-grid">
            <div className="col-full">
              <h3 className="section-title">Full Width Section</h3>
              <p className="section-subtitle">This demonstrates the section title pattern on page background</p>
              <div style={{ background: 'var(--color-bg-surface)', padding: 'var(--space-6)', borderRadius: 'var(--radius-lg)' }}>
                Content in a card
              </div>
            </div>
            <div className="col-8 section-gap">
              <h3 className="section-title">8-Column Section</h3>
              <div style={{ background: 'var(--color-bg-surface)', padding: 'var(--space-6)', borderRadius: 'var(--radius-lg)' }}>
                Main content area
              </div>
            </div>
            <div className="col-4 section-gap">
              <h3 className="section-title">4-Column Sidebar</h3>
              <div style={{ background: 'var(--color-bg-surface)', padding: 'var(--space-6)', borderRadius: 'var(--radius-lg)' }}>
                Sidebar content
              </div>
            </div>
            <div className="col-6 section-gap">
              <h3 className="section-title">6-Column Left</h3>
              <div style={{ background: 'var(--color-bg-surface)', padding: 'var(--space-6)', borderRadius: 'var(--radius-lg)' }}>
                Half width
              </div>
            </div>
            <div className="col-6 section-gap">
              <h3 className="section-title">6-Column Right</h3>
              <div style={{ background: 'var(--color-bg-surface)', padding: 'var(--space-6)', borderRadius: 'var(--radius-lg)' }}>
                Half width
              </div>
            </div>
          </div>
        </section>
      </div>
    </PageLayout>
  );
}
