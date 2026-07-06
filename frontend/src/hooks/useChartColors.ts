import { useEffect, useState } from 'react'
import { getChartColors, type ChartColors } from '../utils/chartTheme'

/**
 * Theme-reactive chart palette (DS1). Returns the resolved --oi-* / --color-* chart colours for the
 * ACTIVE theme and re-renders when the theme flips (a MutationObserver on the documentElement
 * data-theme attribute), so charts never hold a stale light/dark palette across a theme toggle.
 */
export function useChartColors(): ChartColors {
  const [colors, setColors] = useState<ChartColors>(() => getChartColors())
  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return
    const obs = new MutationObserver(() => setColors(getChartColors()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [])
  return colors
}
