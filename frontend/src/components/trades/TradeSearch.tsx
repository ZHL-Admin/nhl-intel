/**
 * TradeSearch (Handoff 6, surface 5E) — first-class entity search for the trade-outcomes page.
 * Resolves teams and GMs to their dossier. (Player + specific-trade resolution is layered on next.)
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { DIVISIONS, getTeamName } from '../../utils/teams'
import { getValueMap, ValueMapPoint } from '../../api/trades'
import './tradeSearch.css'

type Result = { kind: 'team' | 'gm'; id: string; label: string; sub: string }

const TEAM_RESULTS: Result[] = DIVISIONS.flatMap((d) => d.teams).map((t) => ({
  kind: 'team', id: t.abbrev, label: getTeamName(t.abbrev), sub: t.abbrev,
}))

export default function TradeSearch({ onPickEntity }: { onPickEntity: (kind: 'team' | 'gm', id: string) => void }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [gms, setGms] = useState<Result[]>([])
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // GM list (id + name) once, from the value map
    getValueMap('gm').then((rows: ValueMapPoint[]) =>
      setGms(rows.map((r) => ({ kind: 'gm', id: r.id, label: r.label, sub: 'GM' })))).catch(() => {})
  }, [])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return []
    return [...TEAM_RESULTS, ...gms]
      .filter((r) => r.label.toLowerCase().includes(needle) || r.id.toLowerCase().includes(needle))
      .slice(0, 8)
  }, [q, gms])

  return (
    <div className="tsearch" ref={ref}>
      <div className="tsearch__box">
        <Search size={14} className="tsearch__icon" />
        <input
          className="tsearch__input" placeholder="Search a team or GM…" value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)} aria-label="Search teams and GMs" />
      </div>
      {open && results.length > 0 && (
        <div className="tsearch__menu" role="listbox">
          {results.map((r) => (
            <button key={`${r.kind}:${r.id}`} className="tsearch__item" role="option"
              onClick={() => { onPickEntity(r.kind, r.id); setOpen(false); setQ('') }}>
              <span>{r.label}</span><span className="tsearch__sub">{r.sub}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
