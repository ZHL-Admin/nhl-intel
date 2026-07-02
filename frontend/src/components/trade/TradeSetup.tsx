/**
 * TradeSetup — the Trade Builder's empty state (shown before any team is chosen). Mirrors the Trade
 * Outcomes landing: Side A / Side B slots with a swap glyph, the shared TeamQuickJump chip grid, and a
 * player search. Picking a team (or a player) drops straight into the builder, where that team's asset
 * picker and sends list take over.
 */
import { useEffect, useRef, useState } from 'react'
import { ArrowLeftRight, Search } from 'lucide-react'
import { TeamQuickJump } from '../common'
import { DIVISIONS, getTeamColor, getTeamName } from '../../utils/teams'
import { searchAssets } from '../../api/assets'
import { TradeableAsset } from '../../api/types'

const ALL_TEAMS = DIVISIONS.flatMap((d) => d.teams)
const idForAbbrev = (abbrev: string) => ALL_TEAMS.find((t) => t.abbrev === abbrev)?.id
const abbrevForId = (id: number) => ALL_TEAMS.find((t) => t.id === id)?.abbrev

function SideSlot({ label, teamId, isNext }: { label: string; teamId: number | undefined; isNext: boolean }) {
  if (teamId == null) {
    return (
      <div className={`ts-side ts-side--empty${isNext ? ' ts-side--next' : ''}`}>
        <span className="ts-side__label">{label}{isNext ? ' · choose a team' : ''}</span>
      </div>
    )
  }
  const abbrev = abbrevForId(teamId) ?? ''
  return (
    <div className="ts-side ts-side--filled" style={{ ['--ts-team' as any]: getTeamColor(abbrev) }}>
      <span className="ts-side__dot" />
      <span className="ts-side__name">{getTeamName(abbrev)}</span>
    </div>
  )
}

export default function TradeSetup({ teams, onPickTeam, onStartFromPlayer, onLoadExample }: {
  teams: number[]
  onPickTeam: (id: number) => void
  onStartFromPlayer: (asset: TradeableAsset) => void
  onLoadExample: () => void
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState<TradeableAsset[]>([])
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  useEffect(() => {
    const needle = q.trim()
    if (needle.length < 2) { setResults([]); return }
    const t = setTimeout(() => {
      searchAssets({ q: needle, type: 'player', limit: 6 })
        .then(setResults).catch(() => setResults([]))
    }, 200)
    return () => clearTimeout(t)
  }, [q])

  const pickedAbbrevs = teams.map((id) => abbrevForId(id)).filter(Boolean) as string[]
  const nextIndex = teams.length    // the side the next pick fills (0 = A, 1 = B)

  return (
    <div className="ts-setup">
      {/* Side A / Side B slots with a swap glyph between them */}
      <div className="ts-sides">
        <SideSlot label="Side A" teamId={teams[0]} isNext={nextIndex === 0} />
        <ArrowLeftRight size={18} className="ts-sides__swap" aria-hidden />
        <SideSlot label="Side B" teamId={teams[1]} isNext={nextIndex === 1} />
      </div>

      {/* Quick-pick grid — the shared 32-team chips (Trade Outcomes styling) */}
      <div className="ts-pick">
        <div className="ts-pick__label">Pick a team</div>
        <TeamQuickJump exclude={pickedAbbrevs} onPick={(ab) => { const id = idForAbbrev(ab); if (id != null) onPickTeam(id) }} />
      </div>

      <div className="ts-or"><span>or</span></div>

      {/* Player search + load-an-example */}
      <div className="ts-search-row">
        <div className="ts-search" ref={ref}>
          <Search size={16} className="ts-search__icon" />
          <input
            className="ts-search__input"
            placeholder="Start from a player — search to build around someone"
            value={q}
            onChange={(e) => { setQ(e.target.value); setOpen(true) }}
            onFocus={() => setOpen(true)}
            aria-label="Search a player to build a trade around"
          />
          {open && results.length > 0 && (
            <div className="ts-search__menu" role="listbox">
              {results.map((r) => (
                <button key={r.asset_id} className="ts-search__item" role="option"
                  onClick={() => { onStartFromPlayer(r); setQ(''); setOpen(false) }}>
                  <span>{r.label}</span>
                  <span className="ts-search__sub">{[r.org_team, r.pos_or_slot].filter(Boolean).join(' · ')}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button className="ts-example" onClick={onLoadExample}>load an example →</button>
      </div>
    </div>
  )
}
