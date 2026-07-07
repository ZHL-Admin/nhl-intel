/**
 * Roster Builder (/tools/roster-builder) — an interactive depth-chart sandbox.
 *
 * Start from a team's current roster laid out as a depth chart, freely swap in any player, and read a
 * points-led projection live. DELTA vs the real roster is the headline (reliable — shared players
 * cancel); projected points + band is the secondary absolute read (a forward projection, not a
 * measured rating — see docs/methodology/roster-builder.md). Reuses the offseason forecast engine and
 * the Lineup Lab per-line grades via POST /tools/roster-evaluate. No cap/salary anywhere.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Wand2, RotateCcw, X, Plus, Loader2, ChevronLeft, ChevronRight } from 'lucide-react'
import { PageLayout, PageCard, SkeletonLoader, ShareActions } from '../components/common'
import PlayerPicker from '../components/common/PlayerPicker'
import TeamQuickJump from '../components/common/TeamQuickJump'
import { rosterEvaluate, rosterSuggest } from '../api/tools'
import { getTeamRoster } from '../api/teams'
import {
  RosterEvaluateResponse, RosterPlayerOut, RosterSlotInput, RosterSuggestion, TeamRoster, RosterPlayer,
} from '../api/types'
import {
  getTeamColor, getTeamAbbrev, getTeamLogoUrl, setTeamPrimaryColor, clearTeamPrimaryColor, DIVISIONS,
} from '../utils/teams'
import { fmtWar, fmtPoints, fmtPointsBand, MINUS } from '../utils/forecastFormat'
import './RosterBuilder.css'

const ALL_TEAMS = DIVISIONS.flatMap((d) => d.teams) // { id, abbrev }
const ABBR_TO_ID = new Map(ALL_TEAMS.map((t) => [t.abbrev, t.id]))

interface PickedPlayer { player_id: number; name: string | null; pos: string | null }

interface Dnd {
  dragSlot: string | null; overSlot: string | null
  onStart: (slot: string) => void; onEnter: (slot: string) => void
  onEnd: () => void; onDrop: (slot: string) => void
}
/** Two slots can swap only within the same position group (F/D/G). */
const dndCompatible = (a: string | null, b: string) => !!a && a !== b && a[0] === b[0]

const FWD_LINES = [
  ['F1L', 'F1C', 'F1R'], ['F2L', 'F2C', 'F2R'], ['F3L', 'F3C', 'F3R'], ['F4L', 'F4C', 'F4R'],
]
const DEF_PAIRS = [['D1L', 'D1R'], ['D2L', 'D2R'], ['D3L', 'D3R']]
const SLOT_LABEL: Record<string, string> = {
  L: 'LW', C: 'C', R: 'RW',
}
function slotRole(slot: string): string {
  if (slot.startsWith('G')) return slot === 'G1' ? 'Starter' : 'Backup'
  if (slot.startsWith('D')) return slot.endsWith('L') ? 'LD' : 'RD'
  return SLOT_LABEL[slot[slot.length - 1]] ?? ''
}
function slotFilter(slot: string): 'F' | 'D' | undefined {
  if (slot.startsWith('D')) return 'D'
  if (slot.startsWith('F')) return 'F'
  return undefined // goalie slots: no F/D filter
}

interface Placed { player_id: number; name: string | null; pos: string | null }
type Placement = Record<string, Placed | undefined>

/** Seed the placement map from a server response (the slots it iced) — the canvas authoritative state. */
function placementFromResponse(d: RosterEvaluateResponse): Placement {
  const p: Placement = {}
  const take = (s: RosterPlayerOut) => {
    if (s.slot && s.player_id) p[s.slot] = { player_id: s.player_id, name: s.name, pos: s.pos }
  }
  d.forward_lines.forEach((ln) => ln.slots.forEach(take))
  d.defense_pairs.forEach((pr) => pr.slots.forEach(take))
  if (d.goalies.starter) take(d.goalies.starter)
  if (d.goalies.backup) take(d.goalies.backup)
  return p
}

function placementToRoster(p: Placement): RosterSlotInput[] {
  return Object.entries(p)
    .filter(([, v]) => v && v.player_id)
    .map(([slot, v]) => ({ player_id: (v as Placed).player_id, slot }))
}

/** A per-slot lookup of the latest server projection, so the canvas overlays WAR/band onto each card. */
function projBySlot(d: RosterEvaluateResponse | null): Record<string, RosterPlayerOut> {
  const m: Record<string, RosterPlayerOut> = {}
  if (!d) return m
  const take = (s: RosterPlayerOut) => { if (s.slot) m[s.slot] = s }
  d.forward_lines.forEach((ln) => ln.slots.forEach(take))
  d.defense_pairs.forEach((pr) => pr.slots.forEach(take))
  if (d.goalies.starter) take(d.goalies.starter)
  if (d.goalies.backup) take(d.goalies.backup)
  return m
}

/** Verdict-kicker date stamp, e.g. "JUL 6" (browser-local; the share card echoes it). */
const shareStamp = () => new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()

function gradeClass(grade: string | null | undefined): string {
  if (!grade) return ''
  if (grade === 'A') return 'rb-grade--a'
  if (grade === 'B') return 'rb-grade--b'
  if (grade === 'C') return 'rb-grade--c'
  return 'rb-grade--d'
}

export default function RosterBuilder() {
  const [params, setParams] = useSearchParams()
  const initialTeam = Number(params.get('team')) || ALL_TEAMS[0].id
  const [teamId, setTeamId] = useState<number>(initialTeam)
  const [placement, setPlacement] = useState<Placement>({})
  const [data, setData] = useState<RosterEvaluateResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [evaluating, setEvaluating] = useState(false)
  const [error, setError] = useState(false)
  const [pickerSlot, setPickerSlot] = useState<string | null>(null)
  const dirtyRef = useRef(false)        // user has edited since the last server seed
  const reqRef = useRef(0)              // guards against out-of-order responses

  const abbrev = getTeamAbbrev(teamId)

  useEffect(() => {
    setTeamPrimaryColor(getTeamColor(abbrev))
    return () => clearTeamPrimaryColor()
  }, [abbrev])

  // Load the baseline (current roster) whenever the team changes — never a cold empty canvas.
  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(false); dirtyRef.current = false
    const id = ++reqRef.current
    rosterEvaluate(teamId)
      .then((d) => {
        if (cancelled || id !== reqRef.current) return
        setData(d); setPlacement(placementFromResponse(d)); setLoading(false)
      })
      .catch(() => { if (!cancelled) { setError(true); setLoading(false) } })
    return () => { cancelled = true }
  }, [teamId])

  // Live re-evaluation on every edit (debounced ~280ms, like the Trade Builder).
  useEffect(() => {
    if (!dirtyRef.current) return
    const roster = placementToRoster(placement)
    setEvaluating(true)
    const id = ++reqRef.current
    const t = setTimeout(() => {
      rosterEvaluate(teamId, roster)
        .then((d) => { if (id === reqRef.current) { setData(d); setEvaluating(false) } })
        .catch(() => { if (id === reqRef.current) setEvaluating(false) })
    }, 280)
    return () => clearTimeout(t)
  }, [placement, teamId])

  const edit = useCallback((next: Placement) => { dirtyRef.current = true; setPlacement(next) }, [])

  const onSelectTeam = (id: number) => {
    if (id === teamId) return
    setParams({ team: String(id) }, { replace: true })
    setTeamId(id)
  }

  const onPick = (slot: string, p: PickedPlayer) => {
    edit({ ...placement, [slot]: { player_id: p.player_id, name: p.name, pos: p.pos } })
    setPickerSlot(null)
  }
  const onRemove = (slot: string) => {
    const next = { ...placement }; delete next[slot]; edit(next)
  }

  // Drag-and-drop: dragging one slot onto another swaps their players (or moves into an empty slot).
  // Only within a position group (forwards/defense/goalies) — a winger can't fill a D slot.
  const [dragSlot, setDragSlot] = useState<string | null>(null)
  const [overSlot, setOverSlot] = useState<string | null>(null)
  const swapSlots = (a: string, b: string) => {
    if (a === b) return
    const next = { ...placement }
    const pa = next[a]; const pb = next[b]
    if (pb) next[a] = pb; else delete next[a]
    if (pa) next[b] = pa; else delete next[b]
    edit(next)
  }
  const dnd = {
    dragSlot, overSlot,
    onStart: (slot: string) => setDragSlot(slot),
    onEnter: (slot: string) => setOverSlot(slot),
    onEnd: () => { setDragSlot(null); setOverSlot(null) },
    onDrop: (slot: string) => { if (dragSlot) swapSlots(dragSlot, slot); setDragSlot(null); setOverSlot(null) },
  }

  const autoOptimize = () => {
    const roster = placementToRoster(placement)
    setEvaluating(true)
    const id = ++reqRef.current
    rosterEvaluate(teamId, roster, true)
      .then((d) => {
        if (id !== reqRef.current) return
        setData(d); setPlacement(placementFromResponse(d)); dirtyRef.current = false; setEvaluating(false)
      })
      .catch(() => { if (id === reqRef.current) setEvaluating(false) })
  }
  const resetToCurrent = () => {
    setEvaluating(true)
    const id = ++reqRef.current
    rosterEvaluate(teamId)
      .then((d) => {
        if (id !== reqRef.current) return
        setData(d); setPlacement(placementFromResponse(d)); dirtyRef.current = false; setEvaluating(false)
      })
      .catch(() => { if (id === reqRef.current) setEvaluating(false) })
  }

  const proj = useMemo(() => projBySlot(data), [data])

  return (
    <PageLayout>
      <div className="rb">
        <PageCard
          eyebrow="Studio"
          title="Roster Builder"
          subtitle="Assemble the lineup card and let the model evaluate it or suggest additions."
        >
          <TeamBar teamId={teamId} onSelect={onSelectTeam} evaluating={evaluating}
                   onOptimize={autoOptimize} onReset={resetToCurrent} />

          {error ? (
            <p className="rb-msg">Could not load this roster. <button className="rb-link" onClick={resetToCurrent}>Retry</button></p>
          ) : loading ? (
            <div className="rb-grid">
              <SkeletonLoader height={420} /><SkeletonLoader height={420} />
            </div>
          ) : (
            <div className="rb-grid">
              <div className="rb-canvas">
                <p className="rb-canvas__hint">Click a player to swap him out · drag one player onto another to trade spots</p>
                {FWD_LINES.map((line, i) => (
                  <LineRow key={`F${i}`} label={`Line ${i + 1}`} slots={line}
                           fit={data?.forward_lines[i]?.fit ?? null}
                           placement={placement} proj={proj} dnd={dnd}
                           onAdd={setPickerSlot} onRemove={onRemove} />
                ))}
                {DEF_PAIRS.map((pair, i) => (
                  <LineRow key={`D${i}`} label={`Pair ${i + 1}`} slots={pair}
                           fit={data?.defense_pairs[i]?.fit ?? null}
                           placement={placement} proj={proj} dnd={dnd}
                           onAdd={setPickerSlot} onRemove={onRemove} />
                ))}
                <LineRow label="Goalies" slots={['G1', 'G2']} fit={null}
                         placement={placement} proj={proj} dnd={dnd}
                         onAdd={setPickerSlot} onRemove={onRemove} />
                {data && data.scratches.length > 0 && (
                  <div className="rb-scratch">
                    <span className="rb-scratch__label">Scratches</span>
                    <div className="rb-scratch__list">
                      {data.scratches.map((s) => (
                        <span key={s.player_id} className="rb-scratch__chip">{s.name}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <ProjectionPanel data={data} abbrev={abbrev} evaluating={evaluating} />
            </div>
          )}
        </PageCard>
      </div>

      {pickerSlot && (
        <SlotPicker slot={pickerSlot} teamId={teamId} roster={placementToRoster(placement)}
                    onClose={() => setPickerSlot(null)} onPick={(p) => onPick(pickerSlot, p)} />
      )}
    </PageLayout>
  )
}

function TeamBar({ teamId, onSelect, evaluating, onOptimize, onReset }: {
  teamId: number; onSelect: (id: number) => void; evaluating: boolean
  onOptimize: () => void; onReset: () => void
}) {
  return (
    <div className="rb-topbar">
      <TeamQuickJump active={getTeamAbbrev(teamId)}
                     onPick={(ab) => { const id = ABBR_TO_ID.get(ab); if (id) onSelect(id) }} />
      <div className="rb-actions">
        <span className={`rb-eval ${evaluating ? 'is-on' : ''}`}>
          {evaluating && <Loader2 size={13} className="rb-spin" />} {evaluating ? 'evaluating…' : 'live'}
        </span>
        <button className="rb-btn" onClick={onOptimize}><Wand2 size={14} /> Auto-optimize</button>
        <button className="rb-btn" onClick={onReset}><RotateCcw size={14} /> Reset</button>
      </div>
    </div>
  )
}

function LineRow({ label, slots, fit, placement, proj, dnd, onAdd, onRemove }: {
  label: string; slots: string[]; fit: { grade: string | null; xgf_pct: number | null } | null
  placement: Placement; proj: Record<string, RosterPlayerOut>; dnd: Dnd
  onAdd: (slot: string) => void; onRemove: (slot: string) => void
}) {
  return (
    <div className="rb-line">
      <div className="rb-line__head">
        <span className="rb-line__label">{label}</span>
        {fit?.grade && (
          <span className={`rb-grade ${gradeClass(fit.grade)}`} title={fit.xgf_pct != null ? `${(fit.xgf_pct * 100).toFixed(1)}% xGF` : undefined}>
            {fit.grade}
          </span>
        )}
      </div>
      <div className="rb-line__slots">
        {slots.map((slot) => (
          <SlotCard key={slot} slot={slot} placed={placement[slot]} p={proj[slot]} dnd={dnd}
                    onAdd={() => onAdd(slot)} onRemove={() => onRemove(slot)} />
        ))}
      </div>
    </div>
  )
}

function SlotCard({ slot, placed, p, dnd, onAdd, onRemove }: {
  slot: string; placed: Placed | undefined; p: RosterPlayerOut | undefined; dnd: Dnd
  onAdd: () => void; onRemove: () => void
}) {
  const role = slotRole(slot)
  const isGoalie = slot.startsWith('G')
  const canDrop = dndCompatible(dnd.dragSlot, slot)
  // Drop handlers shared by empty + filled cards: accept a compatible drag, show a target highlight.
  const dropProps = {
    onDragOver: (e: React.DragEvent) => { if (canDrop) { e.preventDefault(); dnd.onEnter(slot) } },
    onDrop: (e: React.DragEvent) => { if (canDrop) { e.preventDefault(); dnd.onDrop(slot) } },
  }
  const dropTarget = canDrop && dnd.overSlot === slot ? ' rb-slot--dropok' : ''

  if (!placed) {
    return (
      <button className={`rb-slot rb-slot--empty${dropTarget}`} onClick={onAdd} {...dropProps}>
        <span className="rb-slot__role">{role}</span>
        <span className="rb-slot__hole"><Plus size={14} /> replacement</span>
      </button>
    )
  }
  // WAR/band come from the server response (may lag the optimistic name by one debounce tick).
  const war = p && p.player_id === placed.player_id ? p.projected_war : null
  const sd = p && p.player_id === placed.player_id ? p.war_sd : null
  const shoots = p && p.player_id === placed.player_id ? p.shoots : null
  const isD = slot.startsWith('D')
  const offSide = isD && shoots != null && shoots !== (slot.endsWith('L') ? 'L' : 'R')
  const dragging = dnd.dragSlot === slot ? ' rb-slot--dragging' : ''
  return (
    <div className={`rb-slot ${isGoalie ? 'rb-slot--g' : ''} ${p?.on_new_team ? 'rb-slot--new' : ''}${dropTarget}${dragging}`}
         draggable
         onDragStart={(e) => { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', slot); dnd.onStart(slot) }}
         onDragEnd={dnd.onEnd}
         {...dropProps}>
      <button className="rb-slot__x" onClick={onRemove} aria-label="Remove"><X size={12} /></button>
      <span className="rb-slot__role">
        {role}
        {shoots && !isGoalie && (
          <em className={`rb-slot__hand ${offSide ? 'is-off' : ''}`}
              title={offSide ? `Shoots ${shoots} — playing his off side` : `Shoots ${shoots}`}>{shoots}</em>
        )}
        {p?.on_new_team && <em className="rb-slot__tag">new</em>}
      </span>
      <button className="rb-slot__name" onClick={onAdd} title="Swap">{placed.name}</button>
      <span className="rb-slot__war mono">
        {war == null ? <span className="rb-slot__shim" /> : (
          <>
            {fmtWar(war)} <span className="rb-slot__band">±{sd != null ? sd.toFixed(2) : '—'}</span>
          </>
        )}
        {p?.no_track_record && <em className="rb-slot__nt" title="No track record — replacement level, wide band">no track</em>}
      </span>
    </div>
  )
}

function ProjectionPanel({ data, abbrev, evaluating }: {
  data: RosterEvaluateResponse | null; abbrev: string; evaluating: boolean
}) {
  if (!data) return <div className="rb-panel"><SkeletonLoader height={380} /></div>
  const d = data
  const delta = d.points_delta
  const deltaSign = delta > 0.05 ? 'up' : delta < -0.05 ? 'down' : 'flat'
  const deltaText = deltaSign === 'flat' ? 'even with' :
    `${deltaSign === 'up' ? '+' : MINUS}${Math.abs(Math.round(delta))} points vs`

  const lines = [...d.forward_lines.map((l, i) => ({ name: `Line ${i + 1}`, fit: l.fit })),
                 ...d.defense_pairs.map((p, i) => ({ name: `Pair ${i + 1}`, fit: p.fit }))]
    .filter((l) => l.fit?.grade)
  const graded = lines.filter((l) => l.fit?.xgf_pct != null)
  const best = graded.length ? graded.reduce((a, b) => ((b.fit!.xgf_pct! > a.fit!.xgf_pct!) ? b : a)) : null
  const worst = graded.length ? graded.reduce((a, b) => ((b.fit!.xgf_pct! < a.fit!.xgf_pct!) ? b : a)) : null

  const comp = d.components
  const compRows = [
    { label: '5v5 play', v: comp.play_5v5 }, { label: 'Finishing', v: comp.finishing },
    { label: 'Special teams', v: comp.special_teams }, { label: 'Goaltending', v: comp.goaltending },
  ]
  const compMax = Math.max(2, ...compRows.map((r) => Math.abs(r.v)))
  const pos = d.positional
  const posRows = [
    { label: 'Forwards', v: pos.forward_war }, { label: 'Defense', v: pos.defense_war },
    { label: 'Goaltending', v: pos.goaltending_war },
  ]
  const posMax = Math.max(2, ...posRows.map((r) => r.v))

  const shareVerdict = deltaSign === 'flat'
    ? `This roster projects even with ${abbrev}’s current roster.`
    : `This roster projects ${deltaSign === 'up' ? '+' : MINUS}${Math.abs(Math.round(delta))} points vs ${abbrev}’s current roster.`

  return (
    <div className={`rb-panel ${evaluating ? 'is-evaluating' : ''}`}>
      <div className="rb-kickrow">
        <span className="rb-kicker mono">ROSTER PROJECTION · {shareStamp()}</span>
        <ShareActions kicker={`ROSTER PROJECTION · ${shareStamp()}`} verdict={shareVerdict}
          confidence={{ tone: 'medium', word: 'projection', phrase: `± ${d.delta_band.toFixed(1)} pts` }}
          shareName={`roster-${abbrev?.toLowerCase() ?? 'build'}`} />
      </div>
      <div className={`rb-headline rb-headline--${deltaSign}`}>
        <span className="rb-headline__delta mono">
          {deltaSign === 'flat' ? '±0' : `${deltaSign === 'up' ? '+' : MINUS}${Math.abs(Math.round(delta))}`}
        </span>
        <span className="rb-headline__sub">
          {deltaText === 'even with' ? 'even with' : 'points vs'} {abbrev}’s current roster
          {Math.abs(delta) > 0.05 && <span className="rb-headline__band mono"> ± {d.delta_band.toFixed(1)}</span>}
        </span>
      </div>

      <div className="rb-projbox">
        <div className="rb-projbox__main">
          <span className="rb-projbox__pts mono">{fmtPoints(d.projected_points)}</span>
          <span className="rb-projbox__lbl">projected points</span>
        </div>
        <div className="rb-projbox__band">
          <span className="mono">{fmtPointsBand(d.points_low, d.points_high)}</span>
          <span className="rb-projbox__bandlbl">full-season range (± {Math.round(d.abs_band)})</span>
        </div>
      </div>
      <p className="rb-note">
        The change vs the real roster (± {d.delta_band.toFixed(1)}) is the reliable number — the shared
        players cancel. The full-season total is wide on purpose: an 82-game season is partly luck.
      </p>

      <Section title="Component value" hint="What the roster is made of (realized WAR, shared scale).">
        {compRows.map((r) => <Bar key={r.label} label={r.label} v={r.v} max={compMax} diverging />)}
      </Section>

      <Section title="Positional strength" hint="Projected value above replacement by group.">
        {posRows.map((r) => <Bar key={r.label} label={r.label} v={r.v} max={posMax} />)}
      </Section>

      {(best || worst) && (
        <Section title="Lines" hint="Cold-start fit grades from the Lineup Lab.">
          {best && <div className="rb-linenote"><span className="rb-up">Best</span> {best.name} <span className={`rb-grade ${gradeClass(best.fit!.grade)}`}>{best.fit!.grade}</span></div>}
          {worst && worst.name !== best?.name && <div className="rb-linenote"><span className="rb-down">Weakest</span> {worst.name} <span className={`rb-grade ${gradeClass(worst.fit!.grade)}`}>{worst.fit!.grade}</span></div>}
        </Section>
      )}
    </div>
  )
}

function Section({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="rb-sec">
      <div className="rb-sec__head"><span className="rb-sec__title">{title}</span></div>
      <p className="rb-sec__hint">{hint}</p>
      {children}
    </div>
  )
}

function Bar({ label, v, max, diverging }: { label: string; v: number; max: number; diverging?: boolean }) {
  const pct = Math.min(100, (Math.abs(v) / max) * (diverging ? 50 : 100))
  const up = v >= 0
  return (
    <div className="rb-bar">
      <span className="rb-bar__label">{label}</span>
      <span className={`rb-bar__track ${diverging ? 'is-div' : ''}`}>
        {diverging && <span className="rb-bar__zero" />}
        <span className={`rb-bar__fill ${up ? 'is-up' : 'is-down'}`}
              style={diverging ? (up ? { left: '50%', width: `${pct}%` } : { right: '50%', width: `${pct}%` }) : { left: 0, width: `${pct}%` }} />
      </span>
      <span className={`rb-bar__val mono ${up ? 'is-up' : 'is-down'}`}>{fmtWar(v)}</span>
    </div>
  )
}

function Headshot({ url }: { url: string | null | undefined }) {
  if (!url) return <span className="rb-hs rb-hs--blank" />
  return <img className="rb-hs" src={url} alt=""
              onError={(e) => ((e.target as HTMLImageElement).style.visibility = 'hidden')} />
}

/** Horizontally-scrollable "great fits" carousel — shows ~3 cards, arrows scroll through all 9. */
function FitCarousel({ items, onPick }: {
  items: RosterSuggestion[]; onPick: (p: PickedPlayer) => void
}) {
  const track = useRef<HTMLDivElement>(null)
  const scroll = (dir: number) => track.current?.scrollBy({ left: dir * track.current.clientWidth * 0.8, behavior: 'smooth' })
  return (
    <div className="rb-carousel">
      <button className="rb-carousel__arrow" onClick={() => scroll(-1)} aria-label="Scroll left"><ChevronLeft size={16} /></button>
      <div className="rb-carousel__track" ref={track}>
        {items.map((s) => (
          <button key={s.player_id} className="rb-fitcard"
                  onClick={() => onPick({ player_id: s.player_id, name: s.name, pos: s.pos })}>
            <Headshot url={s.headshot_url} />
            <span className="rb-fitcard__name">{s.name}</span>
            <span className="rb-fitcard__meta">
              {s.team_abbrev && <img className="rb-fitcard__logo" src={getTeamLogoUrl(s.team_abbrev)} alt="" />}
              <span className="mono">{fmtWar(s.projected_war)}</span>
              {s.grade && <span className={`rb-grade ${gradeClass(s.grade)}`}>{s.grade}</span>}
            </span>
          </button>
        ))}
      </div>
      <button className="rb-carousel__arrow" onClick={() => scroll(1)} aria-label="Scroll right"><ChevronRight size={16} /></button>
    </div>
  )
}

/** The visual fill overlay: line-aware "great fits" up top, then explore any team's roster (same
 * chip pills as the rest of the app), with a league search as the fallback. */
function SlotPicker({ slot, teamId, roster, onClose, onPick }: {
  slot: string; teamId: number; roster: RosterSlotInput[]
  onClose: () => void; onPick: (p: PickedPlayer) => void
}) {
  const filter = slotFilter(slot)            // 'F' | 'D' | undefined (goalie)
  // A forward slot wants one exact position (a center slot -> centers, a wing slot -> that side's wings).
  const forwardPos = filter === 'F' ? (slot[slot.length - 1] as 'L' | 'C' | 'R') : undefined
  const pickerFilter = forwardPos ?? filter           // 'C'|'L'|'R' for F, 'D' for D, undefined for G
  const noun = filter === 'D' ? 'defenseman'
    : forwardPos === 'C' ? 'center' : forwardPos === 'L' ? 'left wing'
    : forwardPos === 'R' ? 'right wing' : 'goalie'
  const unit = filter === 'D' ? 'pair' : filter === 'F' ? 'line' : 'crease'
  const [sugg, setSugg] = useState<RosterSuggestion[]>([])
  const [suggLoading, setSuggLoading] = useState(true)
  const [exploreId, setExploreId] = useState(teamId)
  const [exploreRoster, setExploreRoster] = useState<TeamRoster | null>(null)
  const [rosterLoading, setRosterLoading] = useState(true)

  useEffect(() => {
    let c = false; setSuggLoading(true)
    rosterSuggest(teamId, slot, roster)
      .then((d) => { if (!c) { setSugg(d.suggestions); setSuggLoading(false) } })
      .catch(() => { if (!c) setSuggLoading(false) })
    return () => { c = true }
    // roster is captured at open time on purpose — suggestions reflect the line as it stands now.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teamId, slot])

  useEffect(() => {
    let c = false; setRosterLoading(true)
    getTeamRoster(exploreId)
      .then((d) => { if (!c) { setExploreRoster(d); setRosterLoading(false) } })
      .catch(() => { if (!c) setRosterLoading(false) })
    return () => { c = true }
  }, [exploreId])

  const group = (r: TeamRoster | null): RosterPlayer[] =>
    !r ? [] : filter === 'D' ? r.defensemen : filter === 'F' ? r.forwards : r.goalies
  const placedIds = new Set(roster.map((x) => x.player_id))
  const explorePlayers = group(exploreRoster)
    .filter((p) => !placedIds.has(p.player_id))
    .filter((p) => !forwardPos || p.position === forwardPos)   // forwards: exact position (C/L/R)

  return (
    <div className="rb-picker-overlay" onMouseDown={onClose}>
      <div className="rb-picker rb-picker--wide" onMouseDown={(e) => e.stopPropagation()}>
        <div className="rb-picker__head">
          <span>Fill {slotRole(slot)}</span>
          <button className="rb-picker__close" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>

        <div className="rb-picker__sec">
          <span className="rb-picker__label">Great fits for this {unit}</span>
          {suggLoading ? <SkeletonLoader height={66} /> : sugg.length === 0 ? (
            <span className="rb-picker__empty">No fits available for this slot.</span>
          ) : (
            <FitCarousel items={sugg} onPick={onPick} />
          )}
        </div>

        <div className="rb-picker__sec">
          <span className="rb-picker__label">Explore a roster</span>
          <TeamQuickJump active={getTeamAbbrev(exploreId)}
                         onPick={(ab) => { const id = ABBR_TO_ID.get(ab); if (id) setExploreId(id) }} />
          <div className="rb-rosterlist">
            {rosterLoading ? <SkeletonLoader height={130} /> : explorePlayers.length === 0 ? (
              <span className="rb-picker__empty">No available {noun}s on this roster.</span>
            ) : explorePlayers.map((p) => (
              <button key={p.player_id} className="rb-rosteritem"
                      onClick={() => onPick({ player_id: p.player_id, name: p.player_name, pos: p.position })}>
                <Headshot url={p.headshot_url} />
                <span className="rb-rosteritem__name">{p.player_name}</span>
                <span className="rb-rosteritem__pos mono">{p.position}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="rb-picker__sec">
          <span className="rb-picker__label">Or search the league</span>
          <PlayerPicker positionFilter={pickerFilter}
                        onSelect={(p) => onPick({ player_id: p.player_id, name: p.name ?? null, pos: p.position ?? null })}
                        placeholder={`Search any ${noun}…`} />
        </div>
      </div>
    </div>
  )
}
