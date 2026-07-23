import Shell from '../../shell/Shell'
import { ShellContext } from '../../../components/common/PageLayout'
import '../../legacy-tools.css'  // legacy design tokens — bundled in this lazy chunk, never on Home/Notes/Ratings
import LineupLab from '../../../pages/LineupLab'

// Salvaged tool (§4.3), ported chrome-only; lazy-loaded by App.tsx.
export default function LineupLabTool() {
  return (
    <Shell>
      <ShellContext.Provider value={true}>
        <LineupLab />
      </ShellContext.Provider>
    </Shell>
  )
}
