/**
 * VerdictCard (Blueprint P1) — the product's signature grammar: every tool output and entity summary
 * renders through this ONE shape. Overline kicker (mono) · the verdict in words (display serif, one
 * deterministic sentence) · confidence dot+word+uncertainty phrase · a mandatory decomposition visual
 * (law 4) · a quiet "how we measure" link, with optional Copy-link + share-card actions.
 *
 * The serif sentence MUST be composed by the caller from stored fields only (consistency rule); this
 * component never invents copy. The share card (⤓ Card) renders a 1200x630 PNG client-side (brand mark
 * bottom-right) — the social-distribution mechanism required on trade/contract/fit/lineup verdicts.
 */
import { useRef, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Copy, Download } from 'lucide-react'
import { drawShareCard } from '../../utils/shareCard'
import './VerdictCard.css'

export interface VerdictConfidence {
  tone: 'high' | 'medium' | 'low'
  word: string
  /** e.g. "±0.8 WAR" or "single-season window" */
  phrase?: string
}

interface VerdictCardProps {
  /** Mono overline, e.g. "TRADE VERDICT · JUL 3". */
  kicker: string
  /** The verdict, one deterministic sentence (serif). */
  verdict: string
  confidence?: VerdictConfidence
  /** The decomposition visual — stack bar / histogram / diverging bar (mandatory by law 4). */
  viz?: ReactNode
  /** Methodology doc slug → /learn/methods/:slug. */
  methodSlug?: string
  /** Show Copy-link + ⤓ Card actions (required on trade/contract/fit/lineup verdicts). */
  shareable?: boolean
  /** Download filename stem for the share card. */
  shareName?: string
}

export default function VerdictCard({
  kicker, verdict, confidence, viz, methodSlug, shareable, shareName = 'open-ice-verdict',
}: VerdictCardProps) {
  const dotClass = confidence ? `verdict-card__dot verdict-card__dot--${confidence.tone}` : ''

  const copyLink = () => { navigator.clipboard?.writeText(window.location.href).catch(() => {}) }

  const downloadRef = useRef(false)
  const shareCard = async () => {
    if (downloadRef.current) return
    downloadRef.current = true
    try {
      const blob = await drawShareCard({ kicker, verdict, confidence })
      if (blob) {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${shareName}.png`
        a.click()
        URL.revokeObjectURL(url)
      }
    } finally {
      downloadRef.current = false
    }
  }

  return (
    <section className="verdict-card">
      <span className="verdict-card__kicker">{kicker}</span>
      <p className="verdict-card__verdict">{verdict}</p>
      {confidence && (
        <p className="verdict-card__confidence">
          <span className={dotClass} />
          {confidence.word} confidence
          {confidence.phrase && <span className="verdict-card__phrase"> · {confidence.phrase}</span>}
        </p>
      )}
      {viz && <div className="verdict-card__viz">{viz}</div>}
      <div className="verdict-card__foot">
        {methodSlug
          ? <Link className="verdict-card__method" to={`/learn/methods/${methodSlug}`}>How we measure this ↗</Link>
          : <span />}
        {shareable && (
          <div className="verdict-card__actions">
            <button type="button" className="verdict-card__action" onClick={copyLink}>
              <Copy size={14} /> Copy link
            </button>
            <button type="button" className="verdict-card__action" onClick={shareCard}>
              <Download size={14} /> Card
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
