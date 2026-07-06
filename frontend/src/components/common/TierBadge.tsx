import './TierBadge.css'

interface Props {
  label: string
  /** confidence_label: high | medium | low — drives the tone. */
  confidence?: string | null
  size?: 'sm' | 'md'
  title?: string
}

const TONE: Record<string, string> = { high: 'good', medium: 'mid', low: 'low' }

/** Role-tier chip, tinted by confidence. Display-only — never a sort/rank affordance. */
export default function TierBadge({ label, confidence, size = 'md', title }: Props) {
  const tone = TONE[confidence ?? ''] ?? 'neutral'
  return (
    <span className={`tier-badge tier-badge--${tone} tier-badge--${size}`} title={title}>
      {label}
    </span>
  )
}
