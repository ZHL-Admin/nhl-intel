import Shell from '../../shell/Shell'
import { ShellContext } from '../../../components/common/PageLayout'
import '../../legacy-tools.css'  // legacy design tokens — bundled in this lazy chunk, never on Home/Notes/Ratings
import ContractGrader from '../../../pages/ContractGrader'

// Salvaged tool (§4.3), ported chrome-only; lazy-loaded by App.tsx.
export default function ContractGraderTool() {
  return (
    <Shell>
      <ShellContext.Provider value={true}>
        <ContractGrader />
      </ShellContext.Provider>
    </Shell>
  )
}
