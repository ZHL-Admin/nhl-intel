/**
 * Lineup Lab (Phase 5.2, blueprint 6.1): pick a forward trio, a defense pair, or a full
 * 5-skater unit and project its on-ice results from the Phase 5.1 line-fit engine.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PageLayout, Tabs, PlayerPicker, LineProjection, SkeletonLoader } from '../components/common'
import { lineFit } from '../api/tools'
import { LineFitProjection, PlayerSearchResult } from '../api/types'
import './LineupLab.css'

type LineType = 'F3' | 'D2' | 'UNIT5'

// slot composition per line type: which position each slot accepts
const SLOTS: Record<LineType, ('F' | 'D')[]> = {
  F3: ['F', 'F', 'F'],
  D2: ['D', 'D'],
  UNIT5: ['F', 'F', 'F', 'D', 'D'],
}
const SLOT_LABEL = { F: 'Forward', D: 'Defenseman' }

export default function LineupLab() {
  const [lineType, setLineType] = useState<LineType>('F3')
  const [picks, setPicks] = useState<(PlayerSearchResult | null)[]>([null, null, null])
  const [result, setResult] = useState<LineFitProjection | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const changeType = (t: string) => {
    const lt = t as LineType
    setLineType(lt)
    setPicks(SLOTS[lt].map(() => null))
    setResult(null); setError(null)
  }

  const setSlot = (i: number, p: PlayerSearchResult | null) =>
    setPicks(prev => prev.map((x, j) => (j === i ? p : x)))

  const filled = picks.every(Boolean)

  const project = async () => {
    if (!filled) return
    setLoading(true); setError(null); setResult(null)
    try {
      const ids = picks.map(p => p!.player_id)
      setResult(await lineFit(ids))
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Could not project this line.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <PageLayout>
      <div className="lab">
        <div className="lab__header">
          <Link to="/tools" className="lab__back">← Tools</Link>
          <h1 className="lab__title">Lineup Lab</h1>
          <p className="lab__sub">
            Build a line and project its 5v5 results from each member’s measured profile.
            Players don’t need to have ever played together.
          </p>
        </div>

        <div className="lab__builder">
          <Tabs
            options={[
              { value: 'F3', label: 'Forward trio' },
              { value: 'D2', label: 'Defense pair' },
              { value: 'UNIT5', label: 'Full unit (5)' },
            ]}
            value={lineType}
            onChange={changeType}
          />

          <div className="lab__slots">
            {SLOTS[lineType].map((pos, i) => (
              <div key={i} className="lab__slot">
                <label className="lab__slot-label">{SLOT_LABEL[pos]} {pos === 'F'
                  ? i + 1
                  : i - SLOTS[lineType].filter(p => p === 'F').length + 1}</label>
                <PlayerPicker
                  value={picks[i]}
                  positionFilter={pos}
                  onSelect={(p) => setSlot(i, p)}
                  onClear={() => setSlot(i, null)}
                />
              </div>
            ))}
          </div>

          <button className="lab__project" disabled={!filled || loading} onClick={project}>
            {loading ? 'Projecting…' : 'Project line'}
          </button>
        </div>

        <div className="lab__result">
          {loading && <SkeletonLoader />}
          {error && <div className="lab__error">{error}</div>}
          {result && !loading && <LineProjection proj={result} />}
        </div>
      </div>
    </PageLayout>
  )
}
