import { Suspense, lazy } from 'react'
import Shell from '../../shell/Shell'
import { ShellContext } from '../../../components/common/PageLayout'

// Salvaged tool (§4.3), ported unchanged into the new shell (chrome only).
const ContractGrader = lazy(() => import('../../../pages/ContractGrader'))

export default function ContractGraderTool() {
  return (
    <Shell>
      <ShellContext.Provider value={true}>
        <Suspense fallback={<p className="rt-intro">Loading…</p>}>
          <ContractGrader />
        </Suspense>
      </ShellContext.Provider>
    </Shell>
  )
}
