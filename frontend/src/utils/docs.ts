/**
 * Doc loaders (P4). Methodology docs live at docs/methodology/*.md (via the @docs vite alias);
 * writing lives at frontend/content/writing/*.md. Both are inlined at build time as raw strings, so
 * the Learn library renders them on-site with no runtime fetch. Slug = filename without extension.
 */
const methodologyRaw = import.meta.glob('@docs/methodology/*.md', {
  query: '?raw', import: 'default', eager: true,
}) as Record<string, string>

const writingRaw = import.meta.glob('../../content/writing/*.md', {
  query: '?raw', import: 'default', eager: true,
}) as Record<string, string>

function toSlugMap(raw: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [p, content] of Object.entries(raw)) {
    const m = p.match(/([^/]+)\.md$/)
    if (m) out[m[1]] = content
  }
  return out
}

export const METHOD_DOCS = toSlugMap(methodologyRaw)
export const WRITING_DOCS = toSlugMap(writingRaw)

/** All methodology slugs present on disk (README excluded — it's not a method page). */
export const ALL_METHOD_SLUGS = Object.keys(METHOD_DOCS).filter((s) => s.toLowerCase() !== 'readme')

export const getMethodDoc = (slug: string): string | null => METHOD_DOCS[slug] ?? null
export const getWritingDoc = (slug: string): string | null => WRITING_DOCS[slug] ?? null
