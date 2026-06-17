/**
 * Lineup Lab (Phase 5.2, blueprint 6.1) — visual line builder.
 *
 * Build a forward trio, a defense pair, or a full 5-skater unit by browsing team rosters or
 * searching the league, then project its 5v5 results from the Phase 5.1 line-fit engine.
 *
 * Two surfaces:
 *  - The Rink: slots laid out in true on-ice orientation (LW · C · RW above LD · RD). Click a
 *    slot to arm it then pick a player, or drag a player card onto a slot.
 *  - The Explorer: a 32-team logo strip + league-wide search feeding a grid of player cards.
 *
 * The projection itself is rendered by the shared <LineProjection> (drives entirely off the API).
 */
import { useEffect, useRef, useState, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Plus, Search, X, Zap, RotateCcw, ChevronDown, ArrowLeft, Share2, Check, Sparkles } from 'lucide-react'
import { PageLayout, Tabs, PlayerCard, LineProjection, SkeletonLoader } from '../components/common'
import { PlayerCardData } from '../components/common/PlayerCard'
import { lineFit, lineFitSuggestions, searchPlayers } from '../api/tools'
import { getStyleMap, getTeamRoster } from '../api/teams'
import { getTeamName, getTeamLogoUrl, getPlayerHeadshotUrl, getCurrentSeasonId } from '../utils/teams'
import { LineFitProjection, PlayerSearchResult, RosterPlayer, LineMemberOut, LineSuggestions, BetterFitSwap } from '../api/types'
import './LineupLab.css'

type LineType = 'F3' | 'D2' | 'UNIT5'
type SlotPos = 'LW' | 'C' | 'RW' | 'LD' | 'RD'
type Kind = 'F' | 'D'

interface Slot {
  pos: SlotPos
  kind: Kind
  player: PlayerSearchResult | null
}

const LAYOUTS: Record<LineType, SlotPos[]> = {
  F3: ['LW', 'C', 'RW'],
  D2: ['LD', 'RD'],
  UNIT5: ['LW', 'C', 'RW', 'LD', 'RD'],
}
const KIND: Record<SlotPos, Kind> = { LW: 'F', C: 'F', RW: 'F', LD: 'D', RD: 'D' }
const SHORT: Record<SlotPos, string> = { LW: 'LW', C: 'C', RW: 'RW', LD: 'LD', RD: 'RD' }
const FULL: Record<SlotPos, string> = {
  LW: 'Left Wing', C: 'Center', RW: 'Right Wing', LD: 'Left Defense', RD: 'Right Defense',
}

const kindOf = (pos?: string | null): Kind => (pos === 'D' ? 'D' : 'F')
const makeSlots = (lt: LineType): Slot[] =>
  LAYOUTS[lt].map((pos) => ({ pos, kind: KIND[pos], player: null }))

interface TeamOpt { team_id: number; abbrev: string; name: string }

/* ---- shareable line encoding (id.ABBREV pairs in slot order + line type) ---- */
const lineParam = (players: PlayerSearchResult[], type: LineType): Record<string, string> => ({
  line: players.map((p) => `${p.player_id}.${p.team_abbrev ?? ''}`).join('-'),
  type,
})
interface SharePair { id: number; abbrev: string }
const decodeLine = (s: string): SharePair[] =>
  s.split('-')
    .map((tok) => { const [id, abbrev] = tok.split('.'); return { id: parseInt(id, 10), abbrev: abbrev || '' } })
    .filter((p) => Number.isFinite(p.id))
const collectMembers = (proj: LineFitProjection): Record<number, LineMemberOut> => {
  const all = [...(proj.members ?? []), ...(proj.forward_trio?.members ?? []), ...(proj.defense_pair?.members ?? [])]
  const map: Record<number, LineMemberOut> = {}
  for (const m of all) map[m.player_id] = m
  return map
}

/** Share the current projection — Web Share API on mobile, clipboard link otherwise. */
function ShareButton({ url, grade, xgf }: { url: string; grade: string; xgf: number }) {
  const [copied, setCopied] = useState(false)
  const onShare = async () => {
    const text = `My projected line grades ${grade} — ${xgf}% expected-goals share. Build yours in NHL Intel’s Lineup Lab:`
    if (typeof navigator !== 'undefined' && (navigator as any).share) {
      try { await (navigator as any).share({ title: 'NHL Intel · Lineup Lab', text, url }) } catch { /* dismissed */ }
      return
    }
    try {
      await navigator.clipboard.writeText(`${text} ${url}`)
      setCopied(true); setTimeout(() => setCopied(false), 2200)
    } catch { /* clipboard blocked */ }
  }
  return (
    <button className={`lab__share${copied ? ' lab__share--copied' : ''}`} onClick={onShare}>
      {copied ? <><Check size={15} /> Link copied</> : <><Share2 size={15} /> Share</>}
    </button>
  )
}

const POS_FULL: Record<string, string> = { C: 'Center', L: 'Left Wing', R: 'Right Wing', D: 'Defense' }

/** One same-caliber candidate: face, xGF gain, resulting grade, and the top fit reason. */
function CandidateCard({ c, onClick }: { c: BetterFitSwap; onClick: () => void }) {
  const src = c.headshot_url || (c.team_abbrev ? getPlayerHeadshotUrl(c.player_id, c.team_abbrev) : '')
  const gain = `+${(c.xgf_gain * 100).toFixed(1)}`
  return (
    <button className="lab-fit-cand" onClick={onClick} title={`Swap in ${c.name ?? ''}`}>
      <span className="lab-fit-cand__gain">{gain}<small>pp</small></span>
      <span className="lab-fit-cand__media">
        {src
          ? <img src={src} alt="" onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
          : <span className="lab-fit-cand__blank" />}
        {c.team_abbrev && <img className="lab-fit-cand__logo" src={getTeamLogoUrl(c.team_abbrev)} alt="" onError={(e) => ((e.currentTarget.style.display = 'none'))} />}
      </span>
      <span className="lab-fit-cand__name">{c.name}</span>
      <span className="lab-fit-cand__grade">projects {c.swap_grade}</span>
      {c.reasons?.[0] && <span className="lab-fit-cand__why">{c.reasons[0]}</span>}
    </button>
  )
}

/** Per-slot "better fit" suggestions for the projected line — click a candidate to swap + re-project. */
function BetterFits({ playerIds, onSwap }: {
  playerIds: number[]
  onSwap: (currentPlayerId: number, cand: BetterFitSwap) => void
}) {
  const [data, setData] = useState<LineSuggestions | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const key = playerIds.join('-')

  useEffect(() => {
    let on = true
    setLoading(true); setError(null); setData(null)
    lineFitSuggestions(playerIds)
      .then((d) => on && setData(d))
      .catch(() => on && setError('Could not load suggestions right now.'))
      .finally(() => on && setLoading(false))
    return () => { on = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return (
    <div className="lab-fits">
      <div className="lab-fits__head">
        <span className="lab-fits__icon"><Sparkles size={16} /></span>
        <div>
          <h3 className="lab-fits__title">Better fits</h3>
          <p className="lab-fits__sub">
            Same-caliber alternatives — players in each member’s usage tier, ranked by the projected
            xGF% they’d add. Click one to swap it in and re-project.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="lab-fits__loading"><SkeletonLoader /><span>Finding better fits…</span></div>
      ) : error ? (
        <p className="lab-fits__msg">{error}</p>
      ) : data && data.slots.length > 0 ? (
        <div className="lab-fits__slots">
          {data.slots.map((slot) => (
            <div className="lab-fit-slot" key={slot.slot_index}>
              <div className="lab-fit-slot__head">
                <span className="lab-fit-slot__pos">{POS_FULL[slot.position ?? ''] ?? slot.position}</span>
                <span className="lab-fit-slot__cur">over {slot.current_player_name}</span>
              </div>
              {slot.candidates.length > 0 ? (
                <div className="lab-fit-slot__cands">
                  {slot.candidates.map((c) => (
                    <CandidateCard key={c.player_id} c={c} onClick={() => onSwap(slot.current_player_id, c)} />
                  ))}
                </div>
              ) : (
                <p className="lab-fit-slot__none">{slot.current_player_name} is already the best same-tier fit here.</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="lab-fits__msg">No better same-tier fits found for this line.</p>
      )}
    </div>
  )
}

export default function LineupLab() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [lineType, setLineType] = useState<LineType>('F3')
  const [slots, setSlots] = useState<Slot[]>(() => makeSlots('F3'))
  const [armed, setArmed] = useState<number | null>(null)
  const [result, setResult] = useState<LineFitProjection | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dragged = useRef<{ player: PlayerSearchResult; kind: Kind } | null>(null)

  const takenIds = useMemo(
    () => new Set(slots.map((s) => s.player?.player_id).filter(Boolean) as number[]),
    [slots],
  )
  const filled = slots.every((s) => s.player)

  const changeType = (t: string) => {
    const lt = t as LineType
    setLineType(lt)
    setSlots(makeSlots(lt))
    setArmed(null); setResult(null); setError(null)
  }

  /** Place a player into a specific slot (used by drag-drop and explicit targeting). */
  const placeAt = (index: number, player: PlayerSearchResult) => {
    setSlots((prev) => {
      if (kindOf(player.position) !== prev[index].kind) return prev
      return prev.map((s, i) =>
        i === index ? { ...s, player }
          : s.player?.player_id === player.player_id ? { ...s, player: null } : s)
    })
    setArmed(null); setResult(null)
  }

  /** Auto-place: armed slot if compatible, else next empty slot of the player's kind. */
  const placeAuto = (player: PlayerSearchResult) => {
    const kind = kindOf(player.position)
    let idx = armed != null && slots[armed]?.kind === kind ? armed : -1
    if (idx === -1) idx = slots.findIndex((s) => s.kind === kind && !s.player)
    if (idx === -1) idx = slots.findIndex((s) => s.kind === kind)
    if (idx === -1) return
    placeAt(idx, player)
  }

  const removeAt = (index: number) => {
    setSlots((prev) => prev.map((s, i) => (i === index ? { ...s, player: null } : s)))
    setResult(null)
  }

  const armSlot = (index: number) => setArmed((a) => (a === index ? null : index))

  const clearAll = () => {
    setSlots(makeSlots(lineType))
    setArmed(null); setResult(null); setError(null)
  }

  const onDropSlot = (index: number) => {
    const d = dragged.current
    dragged.current = null
    if (d) placeAt(index, d.player)
  }

  const linePlayers = slots.map((s) => s.player).filter(Boolean) as PlayerSearchResult[]
  const showResult = !!result && !loading
  const shareUrl = `${window.location.origin}/tools/lineup-lab?${new URLSearchParams(lineParam(linePlayers, lineType)).toString()}`

  const projectPlayers = async (players: PlayerSearchResult[]) => {
    setLoading(true); setError(null); setResult(null)
    try {
      const proj = await lineFit(players.map((p) => p.player_id))
      setResult(proj)
      setSearchParams(lineParam(players, lineType), { replace: true })
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Could not project this line.')
    } finally {
      setLoading(false)
    }
  }

  const project = () => { if (filled) projectPlayers(linePlayers) }

  /** Apply a "better fit" swap from the result view, then re-project. */
  const applySwap = (currentPlayerId: number, cand: BetterFitSwap) => {
    const repl: PlayerSearchResult = {
      player_id: cand.player_id, name: cand.name, team_id: cand.team_id,
      team_abbrev: cand.team_abbrev, position: cand.position, archetype: cand.archetype,
      headshot_url: cand.headshot_url ?? (cand.team_abbrev ? getPlayerHeadshotUrl(cand.player_id, cand.team_abbrev) : null),
    }
    const next = slots.map((s) => (s.player?.player_id === currentPlayerId ? { ...s, player: repl } : s))
    setSlots(next)
    projectPlayers(next.map((s) => s.player).filter(Boolean) as PlayerSearchResult[])
  }

  /** Return to the builder (keeps the line so it can be tweaked). */
  const projectAnother = () => { setResult(null); setError(null) }

  // Reconstruct + project a shared line from the URL on first load.
  useEffect(() => {
    const line = searchParams.get('line')
    const type = searchParams.get('type') as LineType | null
    if (!line || !type || !LAYOUTS[type]) return
    const pairs = decodeLine(line)
    if (pairs.length !== LAYOUTS[type].length) return
    let on = true
    setLoading(true); setLineType(type)
    lineFit(pairs.map((p) => p.id))
      .then((proj) => {
        if (!on) return
        const mem = collectMembers(proj)
        const built: PlayerSearchResult[] = pairs.map((p) => {
          const m = mem[p.id]
          return {
            player_id: p.id, name: m?.name ?? `#${p.id}`, team_id: null, team_abbrev: p.abbrev,
            position: m?.position ?? null, archetype: m?.archetype ?? null,
            headshot_url: p.abbrev ? getPlayerHeadshotUrl(p.id, p.abbrev) : null,
          }
        })
        const next = makeSlots(type)
        built.forEach((pl) => {
          const idx = next.findIndex((s) => s.kind === kindOf(pl.position) && !s.player)
          if (idx >= 0) next[idx].player = pl
        })
        setSlots(next)
        setResult(proj)
      })
      .catch(() => on && setError('Could not load that shared line.'))
      .finally(() => on && setLoading(false))
    return () => { on = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const fwdSlots = slots.map((s, i) => ({ s, i })).filter((x) => x.s.kind === 'F')
  const defSlots = slots.map((s, i) => ({ s, i })).filter((x) => x.s.kind === 'D')

  const renderSlot = ({ s, i }: { s: Slot; i: number }) => (
    <div key={i} className={`lab-slot-wrap${s.pos === 'C' ? ' lab-slot-wrap--center' : ''}`}>
      <span className="lab-slot__pos" title={FULL[s.pos]}>{SHORT[s.pos]}</span>
      <div
        className={[
          'lab-slot',
          s.player ? 'lab-slot--filled' : 'lab-slot--empty',
          armed === i ? 'lab-slot--armed' : '',
        ].join(' ').trim()}
        onClick={() => !s.player && armSlot(i)}
        onDragOver={(e) => { e.preventDefault() }}
        onDrop={(e) => { e.preventDefault(); onDropSlot(i) }}
      >
        {s.player ? (
          <PlayerCard player={s.player as PlayerCardData} size="lg" onRemove={() => removeAt(i)} />
        ) : (
          <button className="lab-slot__placeholder" onClick={(e) => { e.stopPropagation(); armSlot(i) }}>
            <span className="lab-slot__plus"><Plus size={20} /></span>
            <span className="lab-slot__hint">{armed === i ? 'Pick a player →' : `Add ${FULL[s.pos].toLowerCase()}`}</span>
          </button>
        )}
      </div>
    </div>
  )

  return (
    <PageLayout>
      <div className="lab">
        <div className="lab__header">
          <Link to="/tools" className="lab__back">← Tools</Link>
          <h1 className="lab__title">Lineup Lab</h1>
          <p className="lab__sub">
            Build a line and project its 5v5 results from each member’s measured profile —
            no two players need to have ever shared the ice.
          </p>
        </div>

        {showResult ? (
          /* ---- the champion: projection result ---- */
          <div className="lab__result">
            <div className="lab__result-bar">
              <button className="lab__again" onClick={projectAnother}>
                <RotateCcw size={15} /> Build another line
              </button>
              <ShareButton
                url={shareUrl}
                grade={result!.grade}
                xgf={Math.round(result!.projected_xgf_pct * 100)}
              />
            </div>
            <LineProjection proj={result!} variant="hero" players={linePlayers} />
            <BetterFits playerIds={result!.player_ids} onSwap={applySwap} />
          </div>
        ) : loading ? (
          <div className="lab__result"><SkeletonLoader /></div>
        ) : (
          /* ---- the builder ---- */
          <>
            <div className="lab__build-bar">
              <Tabs
                options={[
                  { value: 'F3', label: 'Forward trio' },
                  { value: 'D2', label: 'Defense pair' },
                  { value: 'UNIT5', label: 'Full unit' },
                ]}
                value={lineType}
                onChange={changeType}
              />
              {slots.some((s) => s.player) && (
                <button className="lab__clear" onClick={clearAll}>
                  <RotateCcw size={13} /> Clear
                </button>
              )}
            </div>

            <div className="lab__grid">
              {/* ---- build surface ---- */}
              <section className="lab__build">
                <div className="lab-rink">
                  <div className="lab-rink__lines" aria-hidden="true" />
                  {fwdSlots.length > 0 && (
                    <div className="lab-rink__zone lab-rink__zone--off">
                      <span className="lab-rink__zone-tag">Offensive zone</span>
                      <div className="lab-rink__row">{fwdSlots.map(renderSlot)}</div>
                    </div>
                  )}
                  {defSlots.length > 0 && (
                    <div className="lab-rink__zone lab-rink__zone--def">
                      <div className="lab-rink__row">{defSlots.map(renderSlot)}</div>
                      <span className="lab-rink__zone-tag lab-rink__zone-tag--def">Defensive pair</span>
                    </div>
                  )}
                </div>

                {error && <div className="lab__error">{error}</div>}

                <button className="lab__project" disabled={!filled || loading} onClick={project}>
                  <Zap size={16} />
                  {loading ? 'Projecting…' : filled ? 'Project line' : `Add ${slots.filter((s) => !s.player).length} more`}
                </button>
              </section>

              {/* ---- explorer ---- */}
              <Explorer onPick={placeAuto} takenIds={takenIds} dragged={dragged} />
            </div>
          </>
        )}
      </div>
    </PageLayout>
  )
}

/* ============================================================================
   Roster + search explorer
   ============================================================================ */
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

function rosterToCard(rp: RosterPlayer, team: TeamOpt, s8: string): PlayerSearchResult {
  return {
    player_id: rp.player_id,
    name: rp.player_name,
    team_id: team.team_id,
    team_abbrev: team.abbrev,
    position: rp.position,
    headshot_url: getPlayerHeadshotUrl(rp.player_id, team.abbrev, s8),
    archetype: null,
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
    <div className="lab-season" ref={ref}>
      <button className="lab-season__btn" onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open}>
        {value}
        <ChevronDown size={13} className={open ? 'lab-season__chev lab-season__chev--open' : 'lab-season__chev'} />
      </button>
      {open && (
        <ul className="lab-season__menu" role="listbox">
          {SEASONS.map((s) => (
            <li key={s}>
              <button
                role="option"
                aria-selected={s === value}
                className={`lab-season__opt${s === value ? ' lab-season__opt--active' : ''}`}
                onClick={() => { onChange(s); setOpen(false) }}
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Explorer({ onPick, takenIds, dragged }: {
  onPick: (p: PlayerSearchResult) => void
  takenIds: Set<number>
  dragged: React.MutableRefObject<{ player: PlayerSearchResult; kind: Kind } | null>
}) {
  const [teams, setTeams] = useState<TeamOpt[]>([])
  const [active, setActive] = useState<TeamOpt | null>(null)
  const [season, setSeason] = useState<string>(SEASONS[0])
  const [roster, setRoster] = useState<{ forwards: RosterPlayer[]; defensemen: RosterPlayer[] } | null>(null)
  const [rosterLoading, setRosterLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PlayerSearchResult[]>([])
  const [searching, setSearching] = useState(false)

  // team list (from the league style map — gives all 32 with abbreviations)
  useEffect(() => {
    let on = true
    getStyleMap()
      .then((sm) => {
        if (!on) return
        const opts = sm.teams
          .filter((t) => t.team_abbrev)
          .map((t) => ({ team_id: t.team_id, abbrev: t.team_abbrev as string, name: getTeamName(t.team_abbrev as string) }))
          .sort((a, b) => a.name.localeCompare(b.name))
        setTeams(opts)
      })
      .catch(() => on && setTeams([]))
    return () => { on = false }
  }, [])

  // roster for the active team + season
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

  // league-wide search (debounced)
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

  const startDrag = (player: PlayerSearchResult) => {
    dragged.current = { player, kind: kindOf(player.position) }
  }

  const searchMode = query.trim().length >= 2
  const s8 = season8(season)

  const card = (p: PlayerSearchResult) => (
    <PlayerCard
      key={p.player_id}
      player={p as PlayerCardData}
      size="md"
      onClick={() => onPick(p)}
      draggable
      onDragStart={() => startDrag(p)}
      onDragEnd={() => { dragged.current = null }}
      disabled={takenIds.has(p.player_id)}
    />
  )

  return (
    <section className="lab__explorer">
      <div className="lab-explorer__search">
        <Search size={15} className="lab-explorer__search-icon" />
        <input
          className="lab-explorer__input"
          placeholder="Search any player in the league…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {query && (
          <button className="lab-explorer__search-clear" onClick={() => setQuery('')} aria-label="Clear search">
            <X size={15} />
          </button>
        )}
      </div>

      <div className="lab-explorer__body">
        {searchMode ? (
          /* ---- league-wide search results ---- */
          searching && results.length === 0 ? (
            <SkeletonLoader />
          ) : results.length === 0 ? (
            <p className="lab-explorer__empty">No players match “{query.trim()}”.</p>
          ) : (
            <div className="lab-explorer__grid">{results.map(card)}</div>
          )
        ) : active ? (
          /* ---- a single team's roster ---- */
          <div className="lab-roster">
            <div className="lab-roster__head">
              <button className="lab-roster__back" onClick={() => setActive(null)}>
                <ArrowLeft size={14} /> Teams
              </button>
              <div className="lab-roster__team">
                <img src={getTeamLogoUrl(active.abbrev)} alt="" className="lab-roster__logo"
                     onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
                <span>{active.name}</span>
              </div>
              <SeasonSelect value={season} onChange={setSeason} />
            </div>

            {rosterLoading ? (
              <SkeletonLoader />
            ) : roster && (roster.forwards.length || roster.defensemen.length) ? (
              <>
                <h3 className="lab-explorer__group"><span>Forwards</span></h3>
                <div className="lab-explorer__grid">
                  {roster.forwards.map((rp) => card(rosterToCard(rp, active, s8)))}
                </div>
                <h3 className="lab-explorer__group"><span>Defense</span></h3>
                <div className="lab-explorer__grid">
                  {roster.defensemen.map((rp) => card(rosterToCard(rp, active, s8)))}
                </div>
              </>
            ) : (
              <p className="lab-explorer__empty">No roster data for {active.name} in {season}.</p>
            )}
          </div>
        ) : (
          /* ---- the team grid (default landing) ---- */
          <>
            <h3 className="lab-explorer__group"><span>Browse by team</span></h3>
            {teams.length === 0 ? (
              <SkeletonLoader />
            ) : (
              <div className="lab-explorer__team-grid">
                {teams.map((t) => (
                  <button key={t.team_id} className="lab-team-card" onClick={() => setActive(t)} title={t.name}>
                    <img src={getTeamLogoUrl(t.abbrev)} alt="" draggable={false}
                         onError={(e) => ((e.currentTarget.style.visibility = 'hidden'))} />
                    <span className="lab-team-card__name">{t.name}</span>
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
