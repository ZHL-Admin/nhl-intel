/**
 * Shared player explorer (Phase 5.2): a two-level browser used by the Lineup Lab and Trade Fit.
 *
 *  - Landing: a grid of 32 team cards.
 *  - Click a team -> its roster (forwards / defense) with a tab-styled season selector.
 *  - A league-wide search box overrides both with a flat results grid.
 *
 * Players are returned through `onPick`. When `dragged` is supplied, roster/search cards are
 * draggable (the Lineup Lab drops them onto slots). `takenIds` dims players already in use.
 */
import { useEffect, useRef, useState } from 'react'
import { Search, X, ChevronDown, ArrowLeft } from 'lucide-react'
import PlayerCard, { PlayerCardData } from './PlayerCard'
import SkeletonLoader from './SkeletonLoader'
import { searchPlayers } from '../../api/tools'
import { getStyleMap, getTeamRoster } from '../../api/teams'
import { getTeamName, getTeamLogoUrl, getPlayerHeadshotUrl, getCurrentSeasonId } from '../../utils/teams'
import { PlayerSearchResult, RosterPlayer } from '../../api/types'
import './PlayerExplorer.css'

type Kind = 'F' | 'D'
const kindOf = (pos?: string | null): Kind => (pos === 'D' ? 'D' : 'F')

const SEASONS: string[] = (() => {
  const startNow = parseInt(getCurrentSeasonId().slice(0, 4), 10)
  const out: string[] = []
  for (let y = startNow; y >= 2010; y--) out.push(`${y}-${String((y + 1) % 100).padStart(2, '0')}`)
  return out
})()
const season8 = (label: string): string => {
  const y = parseInt(label.slice(0, 4), 10)
  return `${y}${y + 1}`
}

interface TeamOpt { team_id: number; abbrev: string; name: string }

function rosterToCard(rp: RosterPlayer, team: TeamOpt, s8: string): PlayerSearchResult {
  return {
    player_id: rp.player_id, name: rp.player_name, team_id: team.team_id, team_abbrev: team.abbrev,
    position: rp.position, headshot_url: getPlayerHeadshotUrl(rp.player_id, team.abbrev, s8), archetype: null,
  }
}

/** Season picker styled to match the line-type Tabs (pill button + dropdown menu). */
function SeasonSelect({ value, onChange }: { value: string; onChange: (s: string) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])
  return (
    <div className="pexp-season" ref={ref}>
      <button className="pexp-season__btn" onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open}>
        {value}
        <ChevronDown size={13} className={open ? 'pexp-season__chev pexp-season__chev--open' : 'pexp-season__chev'} />
      </button>
      {open && (
        <ul className="pexp-season__menu" role="listbox">
          {SEASONS.map((s) => (
            <li key={s}>
              <button role="option" aria-selected={s === value}
                className={`pexp-season__opt${s === value ? ' pexp-season__opt--active' : ''}`}
                onClick={() => { onChange(s); setOpen(false) }}>{s}</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function PlayerExplorer({ onPick, takenIds, dragged, sticky }: {
  onPick: (p: PlayerSearchResult) => void
  takenIds?: Set<number>
  dragged?: React.MutableRefObject<{ player: PlayerSearchResult; kind: 'F' | 'D' } | null>
  sticky?: boolean
}) {
  const [teams, setTeams] = useState<TeamOpt[]>([])
  const [active, setActive] = useState<TeamOpt | null>(null)
  const [season, setSeason] = useState<string>(SEASONS[0])
  const [roster, setRoster] = useState<{ forwards: RosterPlayer[]; defensemen: RosterPlayer[] } | null>(null)
  const [rosterLoading, setRosterLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PlayerSearchResult[]>([])
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    let on = true
    getStyleMap()
      .then((sm) => {
        if (!on) return
        setTeams(sm.teams
          .filter((t) => t.team_abbrev)
          .map((t) => ({ team_id: t.team_id, abbrev: t.team_abbrev as string, name: getTeamName(t.team_abbrev as string) }))
          .sort((a, b) => a.name.localeCompare(b.name)))
      })
      .catch(() => on && setTeams([]))
    return () => { on = false }
  }, [])

  useEffect(() => {
    if (!active) { setRoster(null); return }
    let on = true
    setRosterLoading(true); setRoster(null)
    getTeamRoster(active.team_id, season)
      .then((r) => { if (on) setRoster({ forwards: r.forwards ?? [], defensemen: r.defensemen ?? [] }) })
      .catch(() => on && setRoster({ forwards: [], defensemen: [] }))
      .finally(() => on && setRosterLoading(false))
    return () => { on = false }
  }, [active, season])

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) { setResults([]); setSearching(false); return }
    let on = true
    setSearching(true)
    const t = setTimeout(async () => {
      try {
        const data = await searchPlayers(q, 24)
        if (on) setResults(data.filter((p) => p.position !== 'G'))
      } catch { if (on) setResults([]) }
      finally { if (on) setSearching(false) }
    }, 220)
    return () => { on = false; clearTimeout(t) }
  }, [query])

  const searchMode = query.trim().length >= 2
  const s8 = season8(season)

  const card = (p: PlayerSearchResult) => (
    <PlayerCard
      key={p.player_id}
      player={p as PlayerCardData}
      size="md"
      onClick={() => onPick(p)}
      draggable={!!dragged}
      onDragStart={dragged ? () => { dragged.current = { player: p, kind: kindOf(p.position) } } : undefined}
      onDragEnd={dragged ? () => { dragged.current = null } : undefined}
      disabled={takenIds?.has(p.player_id)}
    />
  )

  return (
    <section className={`pexp${sticky ? ' pexp--sticky' : ''}`}>
      <div className="pexp__search">
        <Search size={15} className="pexp__search-icon" />
        <input className="pexp__input" placeholder="Search any player in the league…"
          value={query} onChange={(e) => setQuery(e.target.value)} />
        {query && (
          <button className="pexp__search-clear" onClick={() => setQuery('')} aria-label="Clear search">
            <X size={15} />
          </button>
        )}
      </div>

      <div className="pexp__body">
        {searchMode ? (
          searching && results.length === 0 ? <SkeletonLoader />
            : results.length === 0 ? <p className="pexp__empty">No players match “{query.trim()}”.</p>
              : <div className="pexp__grid">{results.map(card)}</div>
        ) : active ? (
          <div className="pexp-roster">
            <div className="pexp-roster__head">
              <button className="pexp-roster__back" onClick={() => setActive(null)}><ArrowLeft size={14} /> Teams</button>
              <div className="pexp-roster__team">
                <img src={getTeamLogoUrl(active.abbrev)} alt="" className="pexp-roster__logo"
                  onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
                <span>{active.name}</span>
              </div>
              <SeasonSelect value={season} onChange={setSeason} />
            </div>
            {rosterLoading ? <SkeletonLoader />
              : roster && (roster.forwards.length || roster.defensemen.length) ? (
                <>
                  <h3 className="pexp__group"><span>Forwards</span></h3>
                  <div className="pexp__grid">{roster.forwards.map((rp) => card(rosterToCard(rp, active, s8)))}</div>
                  <h3 className="pexp__group"><span>Defense</span></h3>
                  <div className="pexp__grid">{roster.defensemen.map((rp) => card(rosterToCard(rp, active, s8)))}</div>
                </>
              ) : <p className="pexp__empty">No roster data for {active.name} in {season}.</p>}
          </div>
        ) : (
          <>
            <h3 className="pexp__group"><span>Browse by team</span></h3>
            {teams.length === 0 ? <SkeletonLoader /> : (
              <div className="pexp__team-grid">
                {teams.map((t) => (
                  <button key={t.team_id} className="pexp-team" onClick={() => setActive(t)} title={t.name}>
                    <img src={getTeamLogoUrl(t.abbrev)} alt="" draggable={false}
                      onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
                    <span className="pexp-team__name">{t.name}</span>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}
