/**
 * Gauge (§6.7): a 3px hairline track with a positioned 8px dot marker and a small tabular
 * value. Replaces every fat rounded percentage bar (PercentileBar) in the codebase.
 *
 * Default: a 0→1 (or 0→100) magnitude read; the marker sits at `value/max`, ink dot.
 * Diverging: track centered on zero; the fill runs from center — blue to the right
 * (above expected), red to the left (below expected). Pass value in [-1, 1] with
 * diverging, or supply `min`/`max` around a zero center.
 */
import './Gauge.css'

export default function Gauge({
  value,
  min = 0,
  max = 1,
  label,
  valueLabel,
  diverging = false,
  className = '',
}: {
  value: number
  min?: number
  max?: number
  label?: string
  /** Formatted readout; defaults to the raw value. */
  valueLabel?: string
  diverging?: boolean
  className?: string
}) {
  const clamped = Math.max(min, Math.min(max, value))
  const pct = ((clamped - min) / (max - min)) * 100      // 0..100 along the track

  // Diverging: fill from center (50%) to the marker; blue right, red left.
  const center = 50
  const fillLeft = diverging ? Math.min(center, pct) : 0
  const fillWidth = diverging ? Math.abs(pct - center) : pct
  const fillColor = diverging
    ? (pct >= center ? 'var(--color-data-positive)' : 'var(--color-data-negative)')
    : 'var(--color-accent)'

  return (
    <div className={`gauge ${className}`}>
      {label && <span className="gauge__label">{label}</span>}
      <div className="gauge__track" role="meter" aria-valuenow={value} aria-valuemin={min} aria-valuemax={max}>
        {diverging && <span className="gauge__center" />}
        <span
          className="gauge__fill"
          style={{ left: `${fillLeft}%`, width: `${fillWidth}%`, background: fillColor }}
        />
        <span className="gauge__marker" style={{ left: `${pct}%`, background: fillColor }} />
      </div>
      {valueLabel !== undefined && <span className="gauge__value">{valueLabel}</span>}
    </div>
  )
}
