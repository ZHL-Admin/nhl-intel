/**
 * ShareActions (Blueprint P1) — the ONE "Copy link + ⤓ Card" affordance, extracted so the generic
 * VerdictCard AND the tools' bespoke verdict banners (contract grade, trade grade, fit) render the
 * same social-distribution controls. The share card is a 1200×630 PNG drawn client-side from the
 * verdict's stored fields (brand mark bottom-right) — required on trade/contract/fit/lineup verdicts.
 */
import { useRef } from 'react'
import { Copy, Download } from 'lucide-react'
import { drawShareCard } from '../../utils/shareCard'
import type { VerdictConfidence } from './VerdictCard'
import './ShareActions.css'

interface ShareActionsProps {
  /** Mono overline echoed onto the share card, e.g. "CONTRACT GRADE · JUL 6". */
  kicker: string
  /** The verdict sentence drawn large on the card. */
  verdict: string
  confidence?: VerdictConfidence
  /** Download filename stem. */
  shareName?: string
  className?: string
  /** Optional bespoke card renderer (e.g. the offseason forecast card). When provided it replaces the
   * generic text verdict card for THIS instance only; every other tool keeps drawShareCard untouched. */
  renderCard?: () => Promise<Blob | null>
}

export default function ShareActions({ kicker, verdict, confidence, shareName = 'open-ice-verdict', className, renderCard }: ShareActionsProps) {
  const copyLink = () => { navigator.clipboard?.writeText(window.location.href).catch(() => {}) }

  const busy = useRef(false)
  const shareCard = async () => {
    if (busy.current) return
    busy.current = true
    try {
      const blob = renderCard ? await renderCard() : await drawShareCard({ kicker, verdict, confidence })
      if (blob) {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${shareName}.png`
        a.click()
        URL.revokeObjectURL(url)
      }
    } finally {
      busy.current = false
    }
  }

  return (
    <div className={`share-actions${className ? ` ${className}` : ''}`}>
      <button type="button" className="share-actions__btn" onClick={copyLink}>
        <Copy size={14} /> Copy link
      </button>
      <button type="button" className="share-actions__btn" onClick={shareCard}>
        <Download size={14} /> Share card
      </button>
    </div>
  )
}
