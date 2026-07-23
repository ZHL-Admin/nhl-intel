import { Suspense, lazy } from 'react'
import Shell from '../../shell/Shell'
import { ShellContext } from '../../../components/common/PageLayout'

// Salvaged tool (§4.3), ported unchanged into the new shell (chrome only).
const LineupLab = lazy(() => import('../../../pages/LineupLab'))

export default function LineupLabTool() {
  return (
    <Shell>
      <ShellContext.Provider value={true}>
        <Suspense fallback={<p className="rt-intro">Loading…</p>}>
          <LineupLab />
        </Suspense>
      </ShellContext.Provider>
    </Shell>
  )
}
