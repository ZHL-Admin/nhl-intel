// MDX modules expose a default component (the compiled note body) and, via
// remark-mdx-frontmatter, a named `frontmatter` export (the YAML block).
declare module '*.mdx' {
  import type { ComponentType } from 'react'
  export const frontmatter: {
    title: string
    slug: string
    date: string
    dek?: string
    tags?: string[]
    status: 'draft' | 'published'
    tool?: string
    updated?: string
    readingTime?: string
  }
  const MDXComponent: ComponentType<Record<string, unknown>>
  export default MDXComponent
}
