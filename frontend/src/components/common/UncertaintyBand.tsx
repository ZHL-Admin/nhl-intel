import './UncertaintyBand.css'

interface UncertaintyBandProps {
  value: number
  lo: number
  hi: number
  domainMin: number
  domainMax: number
  size?: 'sm' | 'md'
  /** CSS var (or color) for the fill + tick. Defaults to the active team color. */
  colorVar?: string
}

const clampPct = (x: number, lo: number, hi: number) =>
  Math.max(0, Math.min(100, ((x - lo) / (hi - lo || 1)) * 100))

/**
 * The recurring uncertainty motif: a track with a filled [lo, hi] range and a tick at `value`.
 * Used in the hero rating cell, every move row, every lineup slot, and the league-table range cell —
 * uncertainty is visible everywhere on this page by design.
 */
export default function UncertaintyBand({
  value, lo, hi, domainMin, domainMax, size = 'sm', colorVar = 'var(--color-team-primary)',
}: UncertaintyBandProps) {
  const left = clampPct(Math.min(lo, hi), domainMin, domainMax)
  const right = clampPct(Math.max(lo, hi), domainMin, domainMax)
  const tick = clampPct(value, domainMin, domainMax)
  return (
    <span
      className={`uband uband--${size}`}
      role="img"
      aria-label={`projected ${value.toFixed(2)}, range ${lo.toFixed(2)} to ${hi.toFixed(2)}`}
    >
      <span
        className="uband__range"
        style={{ left: `${left}%`, width: `${Math.max(1.5, right - left)}%`,
                 background: `color-mix(in srgb, ${colorVar} 38%, transparent)` }}
      />
      <span className="uband__tick" style={{ left: `${tick}%`, background: colorVar }} />
    </span>
  )
}
