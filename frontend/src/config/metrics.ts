/**
 * Single source of truth for metric naming on the frontend.
 *
 * Each metric declares its display label, value format, and (from Phase 6) its
 * glossary key exactly once. Components reference these helpers instead of
 * hardcoding stat strings, so renames and proxy labelling happen in one place.
 */

export type MetricFormat =
  | 'percent' // 0..1 or 0..100 rendered as %
  | 'rate' // per-60 style decimals
  | 'count' // integers
  | 'decimal2' // two-decimal floats (e.g. xG)
  | 'plus_minus' // signed (e.g. GSAx)

export interface MetricMeta {
  key: string
  label: string
  format: MetricFormat
  /** Concept-card key, wired to the glossary in Phase 6. */
  glossaryKey?: string
  /** When true, the UI appends "(proxy)" to the label (derived, not observed). */
  proxy?: boolean
}

export const METRICS: Record<string, MetricMeta> = {
  cf_pct: { key: 'cf_pct', label: 'Corsi For %', format: 'percent', glossaryKey: 'corsi' },
  xgf_pct: { key: 'xgf_pct', label: 'Expected Goals %', format: 'percent', glossaryKey: 'xg' },
  hdcf_per60: { key: 'hdcf_per60', label: 'High-danger Chances /60', format: 'rate', glossaryKey: 'high_danger' },
  hdca_per60: { key: 'hdca_per60', label: 'High-danger Chances Against /60', format: 'rate', glossaryKey: 'high_danger' },
  ixg: { key: 'ixg', label: 'Individual xG', format: 'decimal2', glossaryKey: 'xg' },
  gsax: { key: 'gsax', label: 'GSAx', format: 'plus_minus', glossaryKey: 'gsax' },
  zone_entry_proxy_success_rate: {
    key: 'zone_entry_proxy_success_rate',
    label: 'Zone Entry Success',
    format: 'percent',
    proxy: true,
    glossaryKey: 'zone_entry_proxy',
  },
}

/** Display label for a metric, appending "(proxy)" for derived metrics. */
export function metricLabel(key: string): string {
  const m = METRICS[key]
  if (!m) return key
  return m.proxy ? `${m.label} (proxy)` : m.label
}
