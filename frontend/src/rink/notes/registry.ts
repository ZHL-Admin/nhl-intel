import type { ComponentType } from 'react'

export interface NoteFrontmatter {
  title: string
  slug: string
  date: string           // ISO YYYY-MM-DD
  dek?: string
  tags?: string[]
  status: 'draft' | 'published'
  tool?: string          // route of a related tool, for the "EXPLORE THE DATA" strip
  updated?: string
  readingTime?: string   // editorial estimate, e.g. "6 MIN"
}

export interface NoteMeta extends NoteFrontmatter {
  path: string
}

// One eager glob for the whole set (frontmatter + body component). The note
// corpus is small and curated; a single static glob keeps the registry simple
// and avoids the static/dynamic double-import that would defeat chunking.
// (If the recharts weight in the main chunk ever matters, split with
// build.rollupOptions manualChunks — a ship-gate optimization, not needed now.)
const mods = import.meta.glob('/content/notes/*.mdx', { eager: true }) as Record<
  string,
  { frontmatter: NoteFrontmatter; default: ComponentType }
>

// Drafts render in dev only. The production build never lists or serves them,
// so `status: draft` truly never ships as published content (§5.1). Nothing
// publishes without an explicit frontmatter flip to `status: published`.
const SHOW_DRAFTS = import.meta.env.DEV

/** Published notes (plus drafts in dev), newest first. */
export function listNotes(): NoteMeta[] {
  return Object.entries(mods)
    .map(([path, m]) => ({ ...m.frontmatter, path }))
    .filter((n) => SHOW_DRAFTS || n.status === 'published')
    .sort((a, b) => (a.date < b.date ? 1 : -1))
}

export function findNote(slug: string): NoteMeta | undefined {
  return listNotes().find((n) => n.slug === slug)
}

/** The MDX body component for a note, or undefined if not visible. */
export function noteBody(path: string): ComponentType | undefined {
  return mods[path]?.default
}

/** Previous (older) and next (newer) notes for footer nav. */
export function neighbors(slug: string): { prev?: NoteMeta; next?: NoteMeta } {
  const all = listNotes()
  const i = all.findIndex((n) => n.slug === slug)
  if (i === -1) return {}
  return { next: all[i - 1], prev: all[i + 1] }
}
