import { useState, useEffect, useRef } from 'react';
import * as d3 from 'd3';
import ChartPanel from '../common/ChartPanel';
import Tabs from '../common/Tabs';
import { getGameShots } from '../../api/games';
import { ShotAttempt } from '../../api/types';
import './ShotMapKDE.css';

interface ShotMapKDEProps {
  gameId: number;
  homeTeamAbbrev: string;
  awayTeamAbbrev: string;
  homeTeamColor: string;
  awayTeamColor: string;
}

// Rink dimensions (NHL standard, scaled for SVG)
const RINK_LENGTH = 200;
const RINK_WIDTH = 85;
const HALF_RINK = RINK_LENGTH / 2;

// High danger zone definition (slot area)
const HIGH_DANGER_ZONE = {
  xMin: -22,
  xMax: 22,
  yMin: 69,
  yMax: 89
};

function isHighDanger(x: number, y: number): boolean {
  return (
    Math.abs(x) >= HIGH_DANGER_ZONE.xMin &&
    Math.abs(x) <= HIGH_DANGER_ZONE.xMax &&
    Math.abs(y) >= HIGH_DANGER_ZONE.yMin &&
    Math.abs(y) <= HIGH_DANGER_ZONE.yMax
  );
}

function analyzeShotConcentration(shots: ShotAttempt[]): number {
  const hdShots = shots.filter(s => isHighDanger(s.x, s.y)).length;
  const totalShots = shots.length || 1;
  return hdShots / totalShots;
}

function generateTitle(
  homeShots: ShotAttempt[],
  awayShots: ShotAttempt[],
  homeTeamAbbrev: string,
  awayTeamAbbrev: string
): string {
  const homeHDPct = analyzeShotConcentration(homeShots);
  const awayHDPct = analyzeShotConcentration(awayShots);

  if (Math.abs(homeHDPct - awayHDPct) < 0.1) {
    return 'Both teams generated chances from similar areas';
  }

  if (homeHDPct > awayHDPct + 0.1) {
    return `${homeTeamAbbrev}'s attack concentrated in the slot while ${awayTeamAbbrev} relied on perimeter shots`;
  }

  return `${awayTeamAbbrev}'s attack concentrated in the slot while ${homeTeamAbbrev} relied on perimeter shots`;
}

function getShotTypeShape(shotType?: string): string {
  if (!shotType) return 'circle';
  const type = shotType.toLowerCase();
  if (type.includes('slap')) return 'square';
  if (type.includes('tip') || type.includes('deflect')) return 'triangle';
  if (type.includes('back')) return 'diamond';
  if (type.includes('wrap')) return 'star';
  return 'circle';
}

function ShotMapKDEChart({
  gameId,
  homeTeamColor,
  awayTeamColor,
  situation
}: {
  gameId: number;
  homeTeamColor: string;
  awayTeamColor: string;
  situation: string;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [homeShots, setHomeShots] = useState<ShotAttempt[]>([]);
  const [awayShots, setAwayShots] = useState<ShotAttempt[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchShots = async () => {
      setLoading(true);
      try {
        const data = await getGameShots(gameId, situation);
        setHomeShots(data.home_shots || []);
        setAwayShots(data.away_shots || []);
      } catch (err) {
        console.error('Error fetching shot data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchShots();
  }, [gameId, situation]);

  useEffect(() => {
    if (!svgRef.current || loading || (homeShots.length === 0 && awayShots.length === 0)) {
      return;
    }

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = 800;
    const height = 400;

    // Create main group
    const g = svg
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('width', '100%')
      .attr('height', '100%')
      .append('g');

    // Draw rink outline and markings
    drawRink(g, width, height);

    // Scale functions
    const xScale = d3.scaleLinear()
      .domain([-RINK_WIDTH / 2, RINK_WIDTH / 2])
      .range([50, width / 2 - 50]);

    const yScale = d3.scaleLinear()
      .domain([0, HALF_RINK])
      .range([height - 50, 50]);

    // Draw KDE contours for away team (left half)
    if (awayShots.length > 0) {
      drawKDEContours(g, awayShots, xScale, yScale, awayTeamColor);
    }

    // Draw KDE contours for home team (right half, mirrored)
    if (homeShots.length > 0) {
      const xScaleHome = d3.scaleLinear()
        .domain([-RINK_WIDTH / 2, RINK_WIDTH / 2])
        .range([width / 2 + 50, width - 50]);
      drawKDEContours(g, homeShots, xScaleHome, yScale, homeTeamColor);
    }

    // Draw goal markers on top
    drawGoalMarkers(g, awayShots.filter(s => s.outcome === 'goal'), xScale, yScale, awayTeamColor);
    const xScaleHome = d3.scaleLinear()
      .domain([-RINK_WIDTH / 2, RINK_WIDTH / 2])
      .range([width / 2 + 50, width - 50]);
    drawGoalMarkers(g, homeShots.filter(s => s.outcome === 'goal'), xScaleHome, yScale, homeTeamColor);

  }, [homeShots, awayShots, loading, homeTeamColor, awayTeamColor]);

  if (loading) {
    return <div className="shot-map-loading">Loading shot data...</div>;
  }

  const awayOnGoal = awayShots.filter(s => s.outcome === 'shot_on_goal' || s.outcome === 'goal').length;
  const homeOnGoal = homeShots.filter(s => s.outcome === 'shot_on_goal' || s.outcome === 'goal').length;

  return (
    <div className="shot-map-kde">
      <svg ref={svgRef} />
      <div className="shot-map-kde__summary">
        <div className="shot-map-kde__summary-item">
          <span className="shot-map-kde__summary-team">Away:</span>
          <span className="shot-map-kde__summary-stats">
            {awayShots.length} attempts, {awayOnGoal} on goal
          </span>
        </div>
        <div className="shot-map-kde__summary-item">
          <span className="shot-map-kde__summary-team">Home:</span>
          <span className="shot-map-kde__summary-stats">
            {homeShots.length} attempts, {homeOnGoal} on goal
          </span>
        </div>
      </div>
    </div>
  );
}

function drawRink(g: d3.Selection<SVGGElement, unknown, null, undefined>, width: number, height: number) {
  const rinkGroup = g.append('g').attr('class', 'rink');

  // Ice surface background
  rinkGroup
    .append('rect')
    .attr('x', 0)
    .attr('y', 0)
    .attr('width', width)
    .attr('height', height)
    .attr('fill', 'var(--color-bg-base)');

  // Center line
  rinkGroup
    .append('line')
    .attr('x1', width / 2)
    .attr('y1', 50)
    .attr('x2', width / 2)
    .attr('y2', height - 50)
    .attr('stroke', 'var(--color-border)')
    .attr('stroke-width', 2);

  // Rink outline
  rinkGroup
    .append('rect')
    .attr('x', 50)
    .attr('y', 50)
    .attr('width', width - 100)
    .attr('height', height - 100)
    .attr('fill', 'none')
    .attr('stroke', 'var(--color-border-strong)')
    .attr('stroke-width', 2)
    .attr('rx', 28);
}

function drawKDEContours(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  shots: ShotAttempt[],
  xScale: d3.ScaleLinear<number, number>,
  yScale: d3.ScaleLinear<number, number>,
  teamColor: string
) {
  // Prepare data points
  const points: [number, number][] = shots.map(s => [xScale(s.x), yScale(Math.abs(s.y))]);

  if (points.length === 0) return;

  // Create contour density
  const density = d3.contourDensity()
    .x(d => d[0])
    .y(d => d[1])
    .size([800, 400])
    .bandwidth(20)
    .thresholds(15);

  const contours = density(points);

  // Get computed background color from CSS variable
  const bgColor = getComputedStyle(document.documentElement).getPropertyValue('--color-bg-base').trim();

  // Draw contours using color-mix blending instead of opacity
  const maxValue = d3.max(contours, c => c.value) || 1;

  g.append('g')
    .attr('class', 'kde-contours')
    .selectAll('path')
    .data(contours)
    .join('path')
    .attr('d', d3.geoPath())
    .attr('fill', d => {
      const normalized = d.value / maxValue;
      // At peak density (normalized=1), use full team color
      // At zero density, use background color
      // Use color-mix to blend between them
      const teamColorPercent = Math.round(normalized * 100);
      return `color-mix(in srgb, ${teamColor} ${teamColorPercent}%, ${bgColor})`;
    })
    .attr('stroke', 'none');
}

function drawGoalMarkers(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  goals: ShotAttempt[],
  xScale: d3.ScaleLinear<number, number>,
  yScale: d3.ScaleLinear<number, number>,
  teamColor: string
) {
  const goalsGroup = g.append('g').attr('class', 'goals');

  goals.forEach(goal => {
    const cx = xScale(goal.x);
    const cy = yScale(Math.abs(goal.y));
    const shape = getShotTypeShape(goal.shot_type);

    if (shape === 'circle') {
      goalsGroup
        .append('circle')
        .attr('cx', cx)
        .attr('cy', cy)
        .attr('r', 6)
        .attr('fill', 'var(--color-bg-surface)')
        .attr('stroke', teamColor)
        .attr('stroke-width', 2)
        .append('title')
        .text(`${goal.scorer_name || 'Goal'} - ${goal.shot_type || 'shot'} - P${goal.period} ${goal.time_in_period || ''}`);
    } else if (shape === 'square') {
      goalsGroup
        .append('rect')
        .attr('x', cx - 5)
        .attr('y', cy - 5)
        .attr('width', 10)
        .attr('height', 10)
        .attr('fill', 'var(--color-bg-surface)')
        .attr('stroke', teamColor)
        .attr('stroke-width', 2)
        .append('title')
        .text(`${goal.scorer_name || 'Goal'} - ${goal.shot_type || 'shot'} - P${goal.period} ${goal.time_in_period || ''}`);
    }
    // Additional shapes can be added here
  });
}

export default function ShotMapKDE(props: ShotMapKDEProps) {
  const [situation, setSituation] = useState('all');
  const [homeShots, setHomeShots] = useState<ShotAttempt[]>([]);
  const [awayShots, setAwayShots] = useState<ShotAttempt[]>([]);

  useEffect(() => {
    const fetchTitleData = async () => {
      try {
        const data = await getGameShots(props.gameId, situation);
        setHomeShots(data.home_shots || []);
        setAwayShots(data.away_shots || []);
      } catch (err) {
        console.error('Error fetching shot data for title:', err);
      }
    };

    fetchTitleData();
  }, [props.gameId, situation]);

  const title = generateTitle(homeShots, awayShots, props.homeTeamAbbrev, props.awayTeamAbbrev);

  return (
    <ChartPanel
      title={title}
      subtitle="Shot density and goal locations for each team"
      footer={
        <Tabs
          options={[
            { value: 'all', label: 'All Situations' },
            { value: '5v5', label: '5v5 Only' },
          ]}
          value={situation}
          onChange={setSituation}
        />
      }
    >
      <ShotMapKDEChart
        gameId={props.gameId}
        homeTeamColor={props.homeTeamColor}
        awayTeamColor={props.awayTeamColor}
        situation={situation}
      />
    </ChartPanel>
  );
}
