/**
 * A compact "Draft value" line for the player Overview (Handoff 5, 6.5). Self-contained: fetches its
 * own draft block and renders nothing for undrafted players. Never shows the realized number without
 * its context (the slot expectation + how far above/below it landed). Links to the Draft Value tool.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPlayerDraft, DraftPlayerBlock } from '../../api/draft'
import './PlayerDraftLine.css'

const war1 = (v: number) => v.toFixed(1)

function verdict(b: DraftPlayerBlock): { text: string; tone: 'steal' | 'bust' | 'neutral' } {
  if (b.is_censored) return { text: 'still developing', tone: 'neutral' }
  const d = b.value_above_slot
  if (d >= 3) return { text: 'a steal for the slot', tone: 'steal' }
  if (d <= -3) return { text: 'below the slot', tone: 'bust' }
  return { text: 'about slot value', tone: 'neutral' }
}

export default function PlayerDraftLine({ playerId }: { playerId: number }) {
  const [block, setBlock] = useState<DraftPlayerBlock | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    let live = true
    getPlayerDraft(playerId)
      .then((b) => { if (live) { setBlock(b); setDone(true) } })
      .catch(() => { if (live) setDone(true) })
    return () => { live = false }
  }, [playerId])

  if (!done || !block) return null   // undrafted / no data -> render nothing
  const v = verdict(block)
  const pct = Math.round(block.pct_within_range * 100)

  return (
    <div className="pdl">
      <span className="pdl__eyebrow">Draft value</span>
      <span className="pdl__line">
        Drafted <b className="mono">#{block.overall_pick}</b> overall ({block.draft_year}
        {block.draft_team_abbrev ? `, ${block.draft_team_abbrev}` : ''}) —{' '}
        {block.is_censored ? (
          <>still inside the 7-year evaluation window, <span className={`pdl__tag pdl__tag--neutral`}>{v.text}</span></>
        ) : (
          <>
            <b className="mono">{war1(block.realized_value)}</b> WAR over 7 years vs{' '}
            <b className="mono">~{war1(block.expected_mean)}</b> expected for the slot,{' '}
            <span className={`pdl__tag pdl__tag--${v.tone}`}>{v.text}</span>{' '}
            <span className="pdl__pct">({pct}th pct of comparable picks)</span>
          </>
        )}
      </span>
      <span className="pdl__note">
        Realized value is an estimate for older seasons. <Link to="/studio/draft">Draft Value →</Link>
      </span>
    </div>
  )
}
