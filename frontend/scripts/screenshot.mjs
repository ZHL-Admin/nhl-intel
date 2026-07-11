/**
 * Checkpoint screenshotter. Captures a route at desktop (1280) and mobile (390) widths in both themes.
 *   node scripts/screenshot.mjs "/games/2025030215" game-detail
 * Writes to scripts/shots/<name>-<theme>-<width>.png. Assumes the dev server is on :5174.
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'fs'

const route = process.argv[2] || '/'
const name = process.argv[3] || 'shot'
const base = process.env.BASE || 'http://localhost:5174'
const outDir = new URL('./shots/', import.meta.url).pathname
mkdirSync(outDir, { recursive: true })

const widths = [1280, 390]
const themes = ['light', 'dark']

const browser = await chromium.launch()
for (const theme of themes) {
  for (const width of widths) {
    const ctx = await browser.newContext({
      viewport: { width, height: width === 1280 ? 900 : 780 },
      deviceScaleFactor: 1,
    })
    await ctx.addInitScript((t) => localStorage.setItem('nhl-intel-theme', t), theme)
    const page = await ctx.newPage()
    await page.goto(base + route, { waitUntil: 'networkidle', timeout: 45000 }).catch(() => {})
    await page.waitForTimeout(Number(process.env.WAIT || 1500))
    const file = `${outDir}${name}-${theme}-${width}.png`
    await page.screenshot({ path: file, fullPage: true })
    console.log('wrote', file)
    await ctx.close()
  }
}
await browser.close()
