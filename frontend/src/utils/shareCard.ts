/**
 * Client-side share-card renderer (Blueprint P1 / D28). Draws a 1200x630 PNG of a verdict — kicker,
 * the serif sentence, confidence, and the faceoff brand mark bottom-right — entirely on a canvas, no
 * server. The decomposition visual is not rasterized in v1 (arbitrary SVG → canvas needs a DOM-to-image
 * pass); the text card is the shareable artifact. Colours are read from the live theme.
 */
import { BRAND_NAME } from '../config/brand'
import type { VerdictConfidence } from '../components/common/VerdictCard'

const W = 1200
const H = 630

const cssVar = (name: string, fallback: string) => {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

/** Greedy word-wrap to a max width, capped at maxLines (last line ellipsised). */
function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number): string[] {
  const words = text.split(/\s+/)
  const lines: string[] = []
  let line = ''
  for (const w of words) {
    const test = line ? `${line} ${w}` : w
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line)
      line = w
      if (lines.length === maxLines - 1) break
    } else {
      line = test
    }
  }
  if (line && lines.length < maxLines) lines.push(line)
  return lines
}

export async function drawShareCard(
  data: { kicker: string; verdict: string; confidence?: VerdictConfidence },
): Promise<Blob | null> {
  if (typeof document === 'undefined') return null
  // Ensure the variable fonts are ready so canvas doesn't fall back to system faces.
  try { await (document as Document & { fonts?: FontFaceSet }).fonts?.ready } catch { /* noop */ }

  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  if (!ctx) return null

  const bg = cssVar('--color-bg-surface', '#ffffff')
  const ink = cssVar('--color-text-primary', '#1a1917')
  const muted = cssVar('--color-text-muted', '#79756c')
  const secondary = cssVar('--color-text-secondary', '#5c5850')
  const accent = cssVar('--color-accent', '#1a1917')
  const border = cssVar('--color-border', '#e4e1d9')
  const toneColor = data.confidence
    ? cssVar(data.confidence.tone === 'high' ? '--color-success' : data.confidence.tone === 'medium' ? '--color-warning' : '--color-text-muted', muted)
    : muted

  const PAD = 80
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, W, H)
  // hairline frame
  ctx.strokeStyle = border
  ctx.lineWidth = 2
  ctx.strokeRect(1, 1, W - 2, H - 2)

  // kicker (mono, uppercase)
  ctx.fillStyle = muted
  ctx.font = "500 26px 'JetBrains Mono Variable', monospace"
  ctx.textBaseline = 'alphabetic'
  ctx.fillText(data.kicker.toUpperCase(), PAD, PAD + 26)

  // verdict (serif, wrapped)
  ctx.fillStyle = ink
  ctx.font = "600 62px 'Source Serif 4 Variable', Georgia, serif"
  const lines = wrap(ctx, data.verdict, W - PAD * 2, 5)
  let y = PAD + 120
  for (const ln of lines) {
    ctx.fillText(ln, PAD, y)
    y += 78
  }

  // confidence
  if (data.confidence) {
    const cy = H - PAD - 8
    ctx.beginPath()
    ctx.fillStyle = toneColor
    ctx.arc(PAD + 8, cy - 8, 9, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = secondary
    ctx.font = "400 28px 'Inter Variable', system-ui, sans-serif"
    const conf = `${data.confidence.word} confidence${data.confidence.phrase ? ` · ${data.confidence.phrase}` : ''}`
    ctx.fillText(conf, PAD + 28, cy)
  }

  // brand mark (faceoff dot) + name, bottom-right
  const bx = W - PAD - 150
  const by = H - PAD - 16
  ctx.strokeStyle = accent
  ctx.lineWidth = 2.5
  ctx.beginPath()
  ctx.arc(bx, by, 14, 0, Math.PI * 2)
  ctx.stroke()
  ctx.fillStyle = accent
  ctx.beginPath()
  ctx.arc(bx, by, 5, 0, Math.PI * 2)
  ctx.fill()
  ctx.font = "600 30px 'Inter Variable', system-ui, sans-serif"
  ctx.textBaseline = 'middle'
  ctx.fillText(BRAND_NAME, bx + 26, by + 1)

  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), 'image/png'))
}
