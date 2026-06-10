import { useState } from 'react';
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import ChartPanel, { useChartPanelHeight } from '../components/common/ChartPanel';
import StatCard from '../components/common/StatCard';
import Badge from '../components/common/Badge';
import Tabs from '../components/common/Tabs';
import PageLayout from '../components/common/PageLayout';

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

  // Sample sparkline data
  const sparklineData = [48, 52, 49, 55, 53, 58, 54, 51, 56, 60];
  const sparklineDataNegative = [60, 58, 55, 53, 50, 48, 46, 44, 42, 40];

  return (
    <PageLayout>
      <div style={{ padding: 'var(--space-8)', maxWidth: '1280px', margin: '0 auto' }}>
        <h1 style={{ marginBottom: 'var(--space-8)' }}>Component Showcase (Dev Only)</h1>

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
      </div>
    </PageLayout>
  );
}
