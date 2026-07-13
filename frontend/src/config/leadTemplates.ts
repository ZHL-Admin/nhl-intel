/**
 * Today's Lead selection + headline templates (Blueprint 2.1 / P7). Deterministic: rules are evaluated
 * in order, first match wins. Each headline is filled from the SAME payload the visual renders
 * (consistency rule).
 *
 * Phase-aware (doc 19 §3): in-season the game/mover/luck rules apply; in the offseason the Lead is
 * (a) yesterday's largest graded move, else (b) the team with the largest "from moves" swing in the
 * forecast. The offseason Lead links to the Offseason Forecast with ?team={abbr} so the dossier
 * auto-expands (doc 10). TODO(data): source the Lead from a served daily-lead feed when one exists;
 * the feed should inherit this same phase-aware rule so the visual and the copy stay consistent.
 */
import type { PowerRatingRow, DeservedStandingRow, RosterForecastRow, Game, MoveRow } from '../api/types'
import { TRAJECTORY_MEANINGFUL_MOVE } from './metrics'
import { getTeamName } from '../utils/teams'

export type LeadKind = 'live' | 'upset' | 'mover' | 'luck' | 'offseason'

export interface Lead {
  kind: LeadKind
  kicker: string
  headline: string
  dek: string
  link: { to: string; label: string }
}

interface Inputs {
  phase: 'season' | 'offseason'
  slate: Game[]
  lastNight: Game[]
  power: PowerRatingRow[]
  deserved: DeservedStandingRow[]
  offseason: RosterForecastRow[]
  moves?: MoveRow[]
}

const abbr = (t?: string | null, id?: number) => t ?? `#${id ?? ''}`

const isoYesterday = () => {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const ORDINAL = ['zeroth', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth']
const ordinal = (n?: number | null) => (n != null && n < ORDINAL.length ? ORDINAL[n] : n != null ? `${n}th` : '')
const GRADE_MAG: Record<string, number> = { 'A+': 5, A: 4.5, 'A-': 4, 'B+': 3.5, B: 3, 'B-': 2.5, C: 1, D: 3.5, F: 4.5 }
const moveWeight = (m: MoveRow) => (m.type === 'trade' ? Math.abs(m.verdict?.margin ?? 0) : (GRADE_MAG[m.verdict?.grade ?? ''] ?? 0))
const swingVal = (r: RosterForecastRow) => (r.points_delta ?? r.net_delta_war ?? 0)

/** First matching rule wins. Returns null only if nothing qualifies (caller falls back). */
export function selectLead(inputs: Inputs): Lead | null {
  return inputs.phase === 'offseason' ? offseasonLead(inputs) : seasonLead(inputs)
}

// ── Offseason branch ─────────────────────────────────────────────────────────
function offseasonLead({ offseason, moves }: Inputs): Lead | null {
  // (a) yesterday's largest graded move — the headline names the move and its verdict.
  const graded = (moves ?? [])
    .filter((m) => m.date === isoYesterday() && (m.verdict?.grade || m.verdict?.edge))
    .sort((a, b) => moveWeight(b) - moveWeight(a))
  const pick = graded[0]
  if (pick) return moveLead(pick)

  // (b) the largest absolute "from moves" swing in the forecast — written as an editorial hook,
  //     not a stat readout. Headline carries the tension (how far the moves actually move them);
  //     the dek grounds it in the real numbers and opens a curiosity gap toward the forecast.
  const swing = [...offseason]
    .filter((r) => !r.negligible)
    .sort((a, b) => Math.abs(swingVal(b)) - Math.abs(swingVal(a)))[0]
  if (swing) return forecastSwingLead(swing)
  return null
}

const teamName = (abbrev?: string | null, id?: number) => getTeamName(abbrev ?? '') || abbr(abbrev, id)
const mag = (n: number) => Math.abs(Math.round(n))

// The biggest projected mover of the summer, framed by where the moves actually leave them.
function forecastSwingLead(swing: RosterForecastRow): Lead {
  const name = teamName(swing.team_abbrev, swing.team_id)
  const pts = swingVal(swing)
  const P = mag(pts)
  const rank = swing.projected_rank ?? null
  const to = `/studio/offseason?team=${swing.team_abbrev ?? ''}`
  const base = { kind: 'offseason' as const, kicker: 'THE OFFSEASON', link: { to, label: 'See what changed →' } }

  if (pts >= 0) {
    // Most improved. The story is how much that improvement is actually worth in the standings.
    if (rank != null && rank <= 8) {
      return { ...base, headline: `${name} built the summer's biggest upgrade — and now they're built to contend`,
        dek: `A league-best ${P}-point projected jump has them ${ordinal(rank)} before a puck drops. See the moves behind it.` }
    }
    if (rank != null && rank <= 20) {
      return { ...base, headline: `The NHL's most improved team is still chasing the pack`,
        dek: `${name} added more than anyone this summer — a projected ${P} points — and the model still slots them ${ordinal(rank)}.` }
    }
    return { ...base, headline: `The NHL's most improved team still has a long climb ahead`,
      dek: `${name} spent the summer better than any other roster, and the projection barely lifted them off the floor. The case for patience.` }
  }

  // Most eroded. The story is a team that got worse while it slept.
  if (rank != null && rank <= 12) {
    return { ...base, headline: `${name} took the summer's biggest step back`,
      dek: `A league-worst ${P}-point projected erosion this offseason. What they let walk — and whether it sinks them.` }
  }
  return { ...base, headline: `No roster lost more this summer than ${name}`,
    dek: `A projected ${P} points gone, the most in the league, and the model sees the fall. The moves that did the damage.` }
}

// Verdict word for a graded contract — mirrors the Contract Grader's word-first framing.
const GRADE_VERDICT: Record<string, string> = {
  'A+': 'a steal', A: 'a steal', 'A-': 'a bargain', 'B+': 'a bargain',
  B: 'a fair deal', 'B-': 'a fair deal', C: 'a slight overpay', D: 'an overpay', F: 'an albatross',
}
const gradeHook = (grade?: string | null) =>
  !grade ? 'See how it grades.' : ['A', 'B'].includes(grade[0]) ? 'Why the number works.' : 'Why it could bite.'

function moveLead(m: MoveRow): Lead {
  const p = m.players[0]
  if (m.type === 'trade') {
    const edge = m.verdict?.edge ?? m.teams[0]
    return {
      kind: 'offseason', kicker: 'THE LEDGER',
      headline: `${teamName(edge)} came out ahead in the ${p ? `${p.name} ` : ''}trade`,
      dek: m.verdict?.margin != null
        ? `The scoreboard tilts ${m.verdict.margin.toFixed(1)} their way. See how the assets stack up.`
        : 'A fresh deal hits the board. See how it grades.',
      link: { to: `/studio/offseason?team=${edge ?? ''}`, label: 'See the deal →' },
    }
  }
  const grade = m.verdict?.grade
  const verdict = GRADE_VERDICT[grade ?? ''] ?? 'a notable deal'
  const verb = m.type === 'extension' ? 're-signed' : 'signed'
  const terms = m.terms ? `${m.terms.years} years at $${(m.terms.aav / 1e6).toFixed(1)}M` : ''
  return {
    kind: 'offseason', kicker: 'THE LEDGER',
    headline: `${teamName(m.teams[0])} ${verb} ${p?.name ?? 'a new face'} — the model calls it ${verdict}`,
    dek: terms ? `${terms}, graded ${grade}. ${gradeHook(grade)}` : `Graded ${grade}. ${gradeHook(grade)}`,
    link: { to: `/studio/offseason?team=${m.teams[0] ?? ''}`, label: 'See the grade →' },
  }
}

// ── In-season branch ─────────────────────────────────────────────────────────
function seasonLead({ slate, lastNight, power, deserved }: Inputs): Lead | null {
  // Rule 1: a live game (the site can't know the swing without the worm; a live game leads regardless).
  const live = slate.find((g) => g.is_live)
  if (live) {
    return {
      kind: 'live', kicker: 'IT’S HAPPENING',
      headline: `${live.away_team_abbrev} at ${live.home_team_abbrev}, live right now`,
      dek: 'Win probability is swinging — watch it move.',
      link: { to: `/games/${live.game_id}`, label: 'Watch the game →' },
    }
  }

  // Rule 2: yesterday's biggest upset by result — the bigger season-possession dog that still won.
  const finals = lastNight.filter((g) => !g.is_preview && !g.is_live)
  const upset = finals
    .map((g) => {
      const homeWon = (g.home_score ?? 0) > (g.away_score ?? 0)
      const winRank = homeWon ? g.home_cf_rank : g.away_cf_rank
      const loseRank = homeWon ? g.away_cf_rank : g.home_cf_rank
      const edge = winRank != null && loseRank != null ? winRank - loseRank : 0 // winner much worse rank = bigger upset
      return { g, homeWon, edge }
    })
    .filter((x) => x.edge >= 8)
    .sort((a, b) => b.edge - a.edge)[0]
  if (upset) {
    const w = upset.homeWon ? upset.g.home_team_abbrev : upset.g.away_team_abbrev
    const l = upset.homeWon ? upset.g.away_team_abbrev : upset.g.home_team_abbrev
    return {
      kind: 'upset', kicker: 'LAST NIGHT’S SHOCKER',
      headline: `${w} stunned ${l}`,
      dek: 'The underdog by the season’s possession numbers took it anyway.',
      link: { to: `/games/${upset.g.game_id}`, label: 'See how →' },
    }
  }

  // Rule 3: the largest 15-day power mover past the meaningful threshold.
  const mover = [...power]
    .filter((r) => r.trajectory_15d != null && Math.abs(r.trajectory_15d) > TRAJECTORY_MEANINGFUL_MOVE)
    .sort((a, b) => Math.abs(b.trajectory_15d ?? 0) - Math.abs(a.trajectory_15d ?? 0))[0]
  if (mover) {
    const up = (mover.trajectory_15d ?? 0) > 0
    return {
      kind: 'mover', kicker: 'ON THE MOVE',
      headline: `${abbr(mover.team_abbrev, mover.team_id)} is ${up ? 'surging' : 'sliding'}`,
      dek: `Their power rating has moved ${up ? '+' : '−'}${Math.abs(mover.trajectory_15d ?? 0).toFixed(2)} over 15 days.`,
      link: { to: '/teams?view=power', label: 'Power ratings →' },
    }
  }

  // Rule 4: the largest luck gap (actual vs deserved points) — in-season only.
  const luck = [...deserved].sort((a, b) => Math.abs(b.luck_delta) - Math.abs(a.luck_delta))[0]
  if (luck && Math.abs(luck.luck_delta) >= 3) {
    const lucky = luck.luck_delta > 0
    return {
      kind: 'luck', kicker: 'LUCK WATCH',
      headline: `${abbr(luck.team_abbrev, luck.team_id)} has been ${lucky ? 'riding its luck' : 'snakebitten'}`,
      dek: `${Math.round(luck.actual_points)} actual points vs ${Math.round(luck.deserved_points)} deserved.`,
      link: { to: '/teams?view=deserved', label: 'Deserved standings →' },
    }
  }

  return null
}
