import Shell from '../../shell/Shell'
import { ShellContext } from '../../../components/common/PageLayout'
import '../../legacy-tools.css'  // legacy design tokens — bundled in this lazy chunk, never on Home/Notes/Ratings
import DraftValue from '../../../pages/DraftValue'

// Salvaged tool (§4.3), ported chrome-only; lazy-loaded by App.tsx.
export default function DraftValueTool() {
  return (
    <Shell>
      <ShellContext.Provider value={true}>
        <DraftValue />
      </ShellContext.Provider>
    </Shell>
  )
}
