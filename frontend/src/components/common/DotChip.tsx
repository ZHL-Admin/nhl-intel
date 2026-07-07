/**
 * Dot-chip (§6.6): a 7px circle + an eyebrow-style label, no background. The dot color
 * carries meaning (position group, status, archetype family). The faceoff-dot language
 * encodes three levels of certainty:
 *   filled    = confirmed / observed
 *   leaning   = ring with the left half filled
 *   projected = hollow ring (unsettled)
 * Replaces every filled pill chip.
 */
import './DotChip.css'

export type DotState = 'filled' | 'leaning' | 'projected'

export default function DotChip({
  label,
  color = 'var(--color-text-muted)',
  state = 'filled',
  className = '',
}: {
  label: string
  /** Any CSS color — pass a token like `var(--line-blue)` or a getTeamColor() hex. */
  color?: string
  state?: DotState
  className?: string
}) {
  return (
    <span className={`dot-chip ${className}`}>
      <span
        className={`dot-chip__dot dot-chip__dot--${state}`}
        style={{ '--dot-color': color } as React.CSSProperties}
      />
      <span className="dot-chip__label">{label}</span>
    </span>
  )
}
