// Shared figure-treatment constants (§6). Concrete hex so recharts SVG fills are
// unambiguous; these mirror the CSS tokens in tokens.css.
export const FIG = {
  orange: '#F25D2B',
  blue: '#0890D1',
  context: '#CACACA',
  ink: '#17181A',
  muted: '#6B6F76',
  grid: '#FFFFFF',
} as const

export const MONO = "'Spline Sans Mono', ui-monospace, monospace"

// Standard axis tick style: mono, small, muted.
export const tick = { fontFamily: MONO, fontSize: 11, fill: FIG.muted } as const

// Standard axis line: ink.
export const axisLine = { stroke: FIG.ink } as const
