/**
 * Offseason share card — a 1200x630 (2x) social/OG asset for one team's forecast, drawn client-side on
 * a canvas. Unlike the generic text-only drawShareCard (shared by the other tools' verdict banners),
 * this leads with a deterministic HOOK (rank move / points swing / biggest add / else points+rank) and
 * carries the team's logo, color, projected points+range, rank, and a compact IN/OUT moves strip.
 *
 * NHL images (logo, headshot) are loaded with crossOrigin='anonymous' so the canvas never taints and
 * toBlob() cannot fail silently; each degrades to a team-color block (abbrev) or initials if it 404s or
 * is blocked, so export always succeeds. Colors/fonts are hardcoded here (canvas can't read CSS vars).
 */
import { getTeamColor, getTeamLogoUrl, getPlayerHeadshotUrl, getTeamName, getTeamAbbrev } from './teams'
import { BRAND_NAME } from '../config/brand'
import type { RosterForecastRow, RosterMove } from '../api/types'

const W = 1200
const H = 630
const SCALE = 2

// Dark, high-contrast palette (echoes the app's ink/paper but tuned for a social thumbnail).
const INK = '#f6f4ee'
const MUTED = '#a8a297'
const DIM = '#7a746a'
const BG = '#14130f'
const UP = '#5fbf7a'
const DOWN = '#e0685f'
const CHIP = 'rgba(255,255,255,0.06)'
const LINE = 'rgba(255,255,255,0.12)'

const MONO = "'JetBrains Mono Variable', ui-monospace, monospace"
const SANS = "'Inter Variable', system-ui, sans-serif"

function ordinal(n: number | null | undefined): string {
  if (n == null) return '—'
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}
const signed = (v: number, d = 1) => `${v > 0 ? '+' : v < 0 ? '' : ''}${v.toFixed(d)}`

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'

/** NHL's CDN sends no CORS header, so a crossOrigin canvas load of a logo/headshot taints the canvas
 * and export fails silently. Route NHL images through the backend proxy (/assets/img), which re-serves
 * them under the app's permissive CORS so the canvas stays clean. */
const proxied = (nhlUrl: string) => `${API_BASE}/assets/img?url=${encodeURIComponent(nhlUrl)}`

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => resolve(null)
    img.src = proxied(src)
  })
}

/** A usable canvas color for the team — getTeamColor returns hex for known teams, a CSS var otherwise. */
function teamHex(abbrev: string): string {
  const c = getTeamColor(abbrev)
  return c.startsWith('#') || c.startsWith('rgb') ? c : '#3b6fd4'
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

interface Hook {
  kind: 'rank' | 'points' | 'player'
  big: string
  sub: string
  player?: RosterMove
}

function pickHook(row: RosterForecastRow, moves: RosterMove[]): Hook {
  const rankMoved = row.base_rank != null && row.projected_rank != null && row.base_rank !== row.projected_rank
  const ptsDelta = row.points_delta ?? 0
  if (Math.abs(ptsDelta) >= 3) {
    return { kind: 'points', big: `${ptsDelta > 0 ? '+' : ''}${Math.round(ptsDelta)} pts`, sub: 'from the offseason' }
  }
  if (rankMoved) {
    return { kind: 'rank', big: `${ordinal(row.base_rank)} → ${ordinal(row.projected_rank)}`, sub: 'projected finish' }
  }
  const adds = moves
    .filter((m) => m.move_type === 'arrival' && m.player_id != null)
    .sort((a, b) => Math.abs(b.projected_war) - Math.abs(a.projected_war))
  const top = adds[0]
  if (top && Math.abs(top.projected_war) >= 1.0) {
    return { kind: 'player', big: top.name ?? `#${top.player_id}`, sub: `${signed(top.projected_war, 1)} projected WAR · biggest add of the summer`, player: top }
  }
  return { kind: 'points', big: `${row.projected_points ?? '—'} pts`, sub: `projected ${ordinal(row.projected_rank)} of 32` }
}

export async function drawOffseasonCard(data: {
  row: RosterForecastRow
  moves: RosterMove[]
  nextSeason: string
  dateStamp: string
}): Promise<Blob | null> {
  if (typeof document === 'undefined') return null
  try { await (document as Document & { fonts?: FontFaceSet }).fonts?.ready } catch { /* noop */ }

  const { row, moves, nextSeason, dateStamp } = data
  const abbrev = row.team_abbrev ?? getTeamAbbrev(row.team_id)
  const color = teamHex(abbrev)
  const hook = pickHook(row, moves)
  const baseSeasonId = (() => {
    const y = parseInt(String(row.transition).slice(0, 4), 10)
    return isFinite(y) ? `${y}${y + 1}` : undefined
  })()

  const [logo, mug] = await Promise.all([
    loadImage(getTeamLogoUrl(abbrev)),
    hook.kind === 'player' && hook.player?.player_id != null
      ? loadImage(getPlayerHeadshotUrl(hook.player.player_id, abbrev, baseSeasonId))
      : Promise.resolve(null),
  ])

  const canvas = document.createElement('canvas')
  canvas.width = W * SCALE
  canvas.height = H * SCALE
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  ctx.scale(SCALE, SCALE)
  ctx.textBaseline = 'alphabetic'

  const PAD = 64

  // --- background: dark base + a team-color wash from the top-left ---
  ctx.fillStyle = BG
  ctx.fillRect(0, 0, W, H)
  const grad = ctx.createLinearGradient(0, 0, W * 0.9, H)
  grad.addColorStop(0, `${color}55`)
  grad.addColorStop(0.45, `${color}14`)
  grad.addColorStop(1, '#00000000')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, W, H)
  // team-color spine on the left edge
  ctx.fillStyle = color
  ctx.fillRect(0, 0, 10, H)

  // --- header: logo + team name + eyebrow ---
  const logoBox = 96
  if (logo) {
    ctx.drawImage(logo, PAD, PAD, logoBox, logoBox)
  } else {
    ctx.fillStyle = color
    roundRect(ctx, PAD, PAD, logoBox, logoBox, 16)
    ctx.fill()
    ctx.fillStyle = '#fff'
    ctx.font = `700 34px ${SANS}`
    ctx.textAlign = 'center'
    ctx.fillText(abbrev, PAD + logoBox / 2, PAD + logoBox / 2 + 12)
    ctx.textAlign = 'left'
  }
  const tx = PAD + logoBox + 28
  ctx.fillStyle = MUTED
  ctx.font = `600 20px ${MONO}`
  ctx.fillText(`OFFSEASON FORECAST · ${dateStamp}`.toUpperCase(), tx, PAD + 26)
  ctx.fillStyle = INK
  ctx.font = `600 44px ${SANS}`
  ctx.fillText(getTeamName(abbrev), tx, PAD + 72)
  ctx.fillStyle = DIM
  ctx.font = `400 22px ${SANS}`
  ctx.fillText(`Projected for ${nextSeason}`, tx, PAD + 100)

  // --- hook block ---
  const hookY = 250
  if (hook.kind === 'player') {
    const mugSize = 132
    const mx = W - PAD - mugSize
    const my = hookY - 44
    // clipped circle headshot with a team-color ring, or an initials disc
    ctx.save()
    ctx.beginPath()
    ctx.arc(mx + mugSize / 2, my + mugSize / 2, mugSize / 2, 0, Math.PI * 2)
    ctx.closePath()
    ctx.clip()
    if (mug) {
      ctx.drawImage(mug, mx, my, mugSize, mugSize)
    } else {
      ctx.fillStyle = color
      ctx.fillRect(mx, my, mugSize, mugSize)
      ctx.fillStyle = '#fff'
      ctx.font = `700 48px ${SANS}`
      ctx.textAlign = 'center'
      const nm = (hook.player?.name ?? '').split(/\s+/)
      const ini = ((nm[0]?.[0] ?? '') + (nm[nm.length - 1]?.[0] ?? '')).toUpperCase()
      ctx.fillText(ini || '··', mx + mugSize / 2, my + mugSize / 2 + 16)
      ctx.textAlign = 'left'
    }
    ctx.restore()
    ctx.strokeStyle = color
    ctx.lineWidth = 4
    ctx.beginPath()
    ctx.arc(mx + mugSize / 2, my + mugSize / 2, mugSize / 2, 0, Math.PI * 2)
    ctx.stroke()
  }
  ctx.fillStyle = MUTED
  ctx.font = `600 22px ${MONO}`
  ctx.fillText(hook.kind === 'player' ? 'BIGGEST MOVE' : hook.kind === 'rank' ? 'PROJECTED FINISH' : 'THE OFFSEASON', PAD, hookY - 20)
  ctx.fillStyle = INK
  ctx.font = `700 96px ${SANS}`
  ctx.fillText(hook.big, PAD, hookY + 66)
  ctx.fillStyle = MUTED
  ctx.font = `400 26px ${SANS}`
  ctx.fillText(hook.sub, PAD, hookY + 108)

  // --- support row (mono stat cells) ---
  const sy = 430
  const cells: { label: string; value: string; tone?: string }[] = [
    {
      label: 'PROJ POINTS',
      value: `${row.projected_points ?? '—'}${row.points_low != null && row.points_high != null ? `  ${row.points_low}–${row.points_high}` : ''}`,
    },
    { label: 'LEAGUE RANK', value: `${ordinal(row.projected_rank)} of 32` },
    { label: 'MOVES', value: String(row.n_moves) },
    {
      label: 'NET WAR',
      value: signed(row.net_delta_war, 1),
      tone: row.net_delta_war > 0.05 ? UP : row.net_delta_war < -0.05 ? DOWN : MUTED,
    },
  ]
  const cellW = (W - PAD * 2) / cells.length
  cells.forEach((c, i) => {
    const cx = PAD + i * cellW
    if (i > 0) {
      ctx.strokeStyle = LINE
      ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(cx, sy - 4); ctx.lineTo(cx, sy + 40); ctx.stroke()
    }
    const px = cx + (i > 0 ? 24 : 0)
    ctx.fillStyle = DIM
    ctx.font = `600 15px ${MONO}`
    ctx.fillText(c.label, px, sy + 8)
    ctx.fillStyle = c.tone ?? INK
    ctx.font = `600 30px ${MONO}`
    ctx.fillText(c.value, px, sy + 42)
  })

  // --- top-moves strip (up to 3 IN/OUT chips) ---
  const strip = [...moves]
    .filter((m) => m.player_id != null && (m.move_type === 'arrival' || m.move_type === 'departure'))
    .sort((a, b) => Math.abs(b.delta_contribution) - Math.abs(a.delta_contribution))
    .slice(0, 3)
  if (strip.length) {
    const chy = 512
    let chx = PAD
    ctx.font = `500 22px ${SANS}`
    for (const m of strip) {
      const isIn = m.move_type === 'arrival'
      const tag = isIn ? 'IN' : 'OUT'
      const val = signed(m.delta_contribution, 1)
      const label = `${m.name ?? '#' + m.player_id}  ${val}`
      const tagW = 44
      const textW = ctx.measureText(label).width
      const chipW = tagW + textW + 36
      if (chx + chipW > W - PAD) break
      roundRect(ctx, chx, chy, chipW, 44, 10)
      ctx.fillStyle = CHIP
      ctx.fill()
      ctx.fillStyle = isIn ? UP : DOWN
      ctx.font = `700 15px ${MONO}`
      ctx.fillText(tag, chx + 16, chy + 28)
      ctx.fillStyle = INK
      ctx.font = `500 22px ${SANS}`
      ctx.fillText(label, chx + tagW + 8, chy + 29)
      chx += chipW + 12
    }
  }

  // --- footer: wordmark + host + updated ---
  const fy = H - 40
  ctx.fillStyle = color
  ctx.beginPath(); ctx.arc(PAD + 8, fy - 6, 9, 0, Math.PI * 2); ctx.fill()
  ctx.fillStyle = INK
  ctx.font = `700 24px ${SANS}`
  ctx.fillText(BRAND_NAME, PAD + 26, fy)
  ctx.fillStyle = DIM
  ctx.font = `400 18px ${SANS}`
  const host = typeof window !== 'undefined' ? window.location.host : ''
  const foot = `${host ? host + ' · ' : ''}updated ${dateStamp.toLowerCase()}`
  ctx.textAlign = 'right'
  ctx.fillText(foot, W - PAD, fy)
  ctx.textAlign = 'left'

  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), 'image/png'))
}
