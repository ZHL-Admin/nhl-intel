/**
 * The Sheet Design System — chart grammar constants (DS0 scaffold; consumed in DS1).
 * Numeric grammar (strokes, radii, opacities, motion, per-recipe constants) is theme-independent
 * and lives as literals. Colours are read from the CSS custom properties at runtime — theme-aware,
 * cached per active theme — so charts never hardcode a hex and dark/light "just work".
 */

/* --- Theme-independent grammar (§5.2, §4) --- */
export const CHART = {
  series: { stroke: 2, cap: 'round' as const, join: 'round' as const },
  spark: { stroke: 1.5, dot: 2.5, box: [96, 28] as [number, number] },
  point: { r: 3.5, rHover: 5, halo: 2 },
  interval: { dotR: 4, bandOpacity: 0.24, trackStroke: 2 },
  area: { fillOpacity: 0.10 },
  heat: { maxOpacity: 0.85 },
  grid: { minLines: 3, maxLines: 5, stroke: 1 },
  baseline: { stroke: 1 },                       // zero / league-average line
  ticks: { maxX: 6, clearance: 8, size: 11 },
  bar: { topRadius: 2, gapRatio: 0.35, maxWidth: 48 },
  label: { size: 12, weight: 500, haloWidth: 2 },
  legendThreshold: 5,                            // legends only at 5+ series
  annotation: { max: 2 },
  tooltip: { delayChart: 80, delayUi: 300, maxWidth: 260 },
  motion: { fast: 120, base: 180, slow: 240, easing: 'cubic-bezier(0.2, 0, 0, 1)' },
}

/* --- Per-recipe constants (§6). Components read these; they never hardcode. --- */
export const RECIPE = {
  R1_intervalDot: { track: 2, bandHeight: 6, bandRadius: 3, point: 4, rowHeight: 44 },
  R2_ladderHistogram: { columns: 6, gap: 6, wellHeight: 40, wellRadius: 4, labelMinMass: 0.05 },
  R3_timelineWorm: { line: 2, fillOpacity: 0.12, goalR: 4, halo: 2 },
  R4_shotMap: { rinkStroke: 1, densityMaxOpacity: 0.85, shotR: 3, goalR: 4.5, legendBox: [96, 8] as [number, number] },
  R5_radar: { rings: [50, 90], ringStroke: 1, polyStroke: 2, polyFill: 0.12 },
  R6_stackBar: { segGap: 2, totalTick: 2, whisker: 1 },
  R7_divergingSpokes: { centerStroke: 1, valueSize: 11 },
  R8_sparkline: { stroke: 1.5, dot: 2.5, box: [96, 28] as [number, number] },
  R9_standingsLadder: { cutStroke: 1 },
}

/* --- Colours: read from CSS vars, cached per active theme --- */
function cssVar(name: string): string {
  if (typeof window === 'undefined' || typeof document === 'undefined') return ''
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export interface ChartColors {
  categorical: string[]
  diverging: string[]
  seqCool: string[]
  seqHeat: string[]
  ice: string[]
  dataInk: string
  gridline: string
  baseline: string
  surface: string
  textMuted: string
  success: string
  danger: string
}

let cache: { theme: string; colors: ChartColors } | null = null

function readColors(): ChartColors {
  const range = (n: number, f: (i: number) => string) => Array.from({ length: n }, (_, i) => f(i))
  return {
    categorical: range(6, (i) => cssVar(`--oi-cat-${i + 1}`)),
    diverging: range(7, (i) => cssVar(`--oi-div-${i + 1}`)),
    seqCool: range(5, (i) => cssVar(`--oi-seq-cool-${i + 1}`)),
    seqHeat: range(5, (i) => cssVar(`--oi-seq-heat-${i + 1}`)),
    ice: [100, 200, 300, 400, 500, 600, 700].map((s) => cssVar(`--oi-ice-${s}`)),
    dataInk: cssVar('--oi-ice-600'),
    gridline: cssVar('--color-border-subtle'),
    baseline: cssVar('--color-border-strong'),
    surface: cssVar('--color-bg-surface'),
    textMuted: cssVar('--color-text-muted'),
    success: cssVar('--color-success'),
    danger: cssVar('--color-danger'),
  }
}

/** Theme-aware chart palette. Re-reads only when the active theme changes. */
export function getChartColors(): ChartColors {
  const theme = typeof document !== 'undefined'
    ? document.documentElement.getAttribute('data-theme') ?? 'light'
    : 'light'
  if (!cache || cache.theme !== theme) cache = { theme, colors: readColors() }
  return cache.colors
}
