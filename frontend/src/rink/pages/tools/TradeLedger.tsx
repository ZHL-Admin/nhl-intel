import Shell from '../../shell/Shell'
import { ShellContext } from '../../../components/common/PageLayout'
import '../../legacy-tools.css'  // legacy design tokens — bundled in this lazy chunk, never on Home/Notes/Ratings
import TradeOutcomes from '../../../pages/TradeOutcomes'

// Salvaged tool (§4.3), ported chrome-only. This whole module is lazy-loaded by
// App.tsx, so the tool code + its legacy CSS ship only when the route is visited.
// ShellContext=true collapses the tool's own PageLayout to a pass-through, so it
// renders inside the new TopBar/Footer. Renamed Trade Outcomes → Trade Ledger.
export default function TradeLedger() {
  return (
    <Shell>
      <ShellContext.Provider value={true}>
        <TradeOutcomes />
      </ShellContext.Provider>
    </Shell>
  )
}
