// Build-time RSS generator (§2 /rss.xml). Scans content/notes/*.mdx, keeps only
// `status: published`, and writes public/rss.xml (Vite copies public/ to the dist
// root). Drafts never appear in the feed. A feed with zero published notes is
// still emitted as valid, empty RSS.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import matter from 'gray-matter'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..')
const NOTES_DIR = path.join(ROOT, 'content', 'notes')
const OUT = path.join(ROOT, 'public', 'rss.xml')

const SITE = process.env.SITE_URL || 'https://rinktheory.example'
const TITLE = 'Rink Theory'
const DESCRIPTION = 'An analytic study of the NHL — research notes.'

const esc = (s = '') =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

function toRfc822(iso) {
  const [y, m, d] = String(iso).split('-').map(Number)
  return new Date(Date.UTC(y, (m || 1) - 1, d || 1)).toUTCString()
}

let notes = []
if (fs.existsSync(NOTES_DIR)) {
  notes = fs.readdirSync(NOTES_DIR)
    .filter((f) => f.endsWith('.mdx'))
    .map((f) => matter(fs.readFileSync(path.join(NOTES_DIR, f), 'utf8')).data)
    .filter((fm) => fm.status === 'published')
    .sort((a, b) => (a.date < b.date ? 1 : -1))
}

const items = notes.map((n) => `    <item>
      <title>${esc(n.title)}</title>
      <link>${SITE}/notes/${esc(n.slug)}</link>
      <guid isPermaLink="true">${SITE}/notes/${esc(n.slug)}</guid>
      <pubDate>${toRfc822(n.date)}</pubDate>
      ${n.dek ? `<description>${esc(n.dek)}</description>` : ''}
      ${(n.tags || []).map((t) => `<category>${esc(t)}</category>`).join('')}
    </item>`).join('\n')

const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${esc(TITLE)}</title>
    <link>${SITE}</link>
    <description>${esc(DESCRIPTION)}</description>
    <language>en-us</language>
    <atom:link href="${SITE}/rss.xml" rel="self" type="application/rss+xml" />
${items ? items + '\n' : ''}  </channel>
</rss>
`

fs.mkdirSync(path.dirname(OUT), { recursive: true })
fs.writeFileSync(OUT, xml)
console.log(`[gen-rss] wrote ${OUT} — ${notes.length} published note(s).`)
