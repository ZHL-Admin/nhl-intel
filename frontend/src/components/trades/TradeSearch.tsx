/**
 * TradeSearch (Handoff 6, surface 5E) — first-class entity search for the trade-outcomes page.
 * Resolves teams and GMs to their dossier. (Player + specific-trade resolution is layered on next.)
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { DIVISIONS, getTeamName } from '../../utils/teams'
import { getValueMap, ValueMapPoint } from '../../api/trades'
import { searchPlayers } from '../../api/tools'
import './tradeSearch.css'

type Result = { kind: 'team' | 'gm' | 'player'; id: string; label: string; sub: string }

const TEAM_RESULTS: Result[] = DIVISIONS.flatMap((d) => d.teams).map((t) => ({
  kind: 'team', id: t.abbrev, label: getTeamName(t.abbrev), sub: t.abbrev,
}))

export default function TradeSearch({ onPickEntity }: {
  onPickEntity: (kind: 'team' | 'gm', id: string) => void
  onPickTrade?: (tradeId: string) => void
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [gms, setGms] = useState<Result[]>([])
  const [players, setPlayers] = useState<Result[]>([])
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

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

  // debounced player search (current-roster players) once the query is specific enough
  useEffect(() => {
    const needle = q.trim()
    if (needle.length < 3) { setPlayers([]); return }
    const t = setTimeout(() => {
      searchPlayers(needle, 4)
        .then((ps) => setPlayers(ps.map((p: any) => ({
          kind: 'player', id: String(p.player_id ?? p.id), label: p.name ?? p.full_name ?? '', sub: 'player',
        }))))
        .catch(() => setPlayers([]))
    }, 200)
    return () => clearTimeout(t)
  }, [q])

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return []
    const entities = [...TEAM_RESULTS, ...gms]
      .filter((r) => r.label.toLowerCase().includes(needle) || r.id.toLowerCase().includes(needle))
      .slice(0, 6)
    return [...entities, ...players].slice(0, 8)
  }, [q, gms, players])

  const pick = (r: Result) => {
    if (r.kind === 'player') navigate(`/players/${r.id}`)
    else onPickEntity(r.kind, r.id)
    setOpen(false); setQ('')
  }

  return (
    <div className="tsearch" ref={ref}>
      <div className="tsearch__box">
        <Search size={14} className="tsearch__icon" />
        <input
          className="tsearch__input" placeholder="Search a team, GM, or player…" value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)} aria-label="Search teams, GMs, and players" />
      </div>
      {open && results.length > 0 && (
        <div className="tsearch__menu" role="listbox">
          {results.map((r) => (
            <button key={`${r.kind}:${r.id}`} className="tsearch__item" role="option" onClick={() => pick(r)}>
              <span>{r.label}</span><span className="tsearch__sub">{r.sub}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
