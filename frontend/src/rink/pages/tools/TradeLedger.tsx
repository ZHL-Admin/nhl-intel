import { Suspense, lazy } from 'react'
import Shell from '../../shell/Shell'
import { ShellContext } from '../../../components/common/PageLayout'

// Salvaged tool (§4.3), ported unchanged into the new shell. ShellContext=true
// collapses the tool's own PageLayout to a pass-through, so it renders inside the
// new TopBar/Footer chrome instead of the old NavBar. Renamed Trade Outcomes →
// Trade Ledger (§7 step 5); internal logic is unchanged.
const TradeOutcomes = lazy(() => import('../../../pages/TradeOutcomes'))

export default function TradeLedger() {
  return (
    <Shell>
      <ShellContext.Provider value={true}>
        <Suspense fallback={<p className="rt-intro">Loading…</p>}>
          <TradeOutcomes />
        </Suspense>
      </ShellContext.Provider>
    </Shell>
  )
}
