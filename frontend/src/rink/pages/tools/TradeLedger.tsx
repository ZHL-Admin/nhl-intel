import { useParams } from 'react-router-dom'
import Shell from '../../shell/Shell'
import Placeholder from '../Placeholder'

/**
 * Trade Ledger (§2) — renamed from Trade Outcomes. Keeps its deep-link param
 * routes (/tools/trade-ledger/trade/:tradeId and /:kind/:id). The real port of
 * TradeOutcomes + components/trades/* lands in Step 5.
 */
export default function TradeLedger() {
  const { tradeId, kind, id } = useParams()
  const deep = tradeId ? `trade/${tradeId}` : kind ? `${kind}/${id}` : '(index)'
  return (
    <Shell>
      <Placeholder
        title="Trade Ledger"
        kicker="Tool"
        step="Step 5 (Tools)"
        note={`Ports TradeOutcomes + components/trades/*. Deep link: ${deep}.`}
      />
    </Shell>
  )
}
