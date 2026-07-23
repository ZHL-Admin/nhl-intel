import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import mdx from '@mdx-js/rollup'
import remarkFrontmatter from 'remark-frontmatter'
import remarkMdxFrontmatter from 'remark-mdx-frontmatter'
import remarkGfm from 'remark-gfm'
import path from 'path'

// RINK THEORY notes are authored in MDX (§5.1) so figures can be React components.
// remark-frontmatter + remark-mdx-frontmatter expose the YAML frontmatter as a
// named `frontmatter` export, which the notes registry reads to build the index
// and RSS. The MDX plugin must run before the React plugin (enforce: 'pre').
export default defineConfig({
  plugins: [
    {
      enforce: 'pre',
      ...mdx({
        remarkPlugins: [
          remarkFrontmatter,
          [remarkMdxFrontmatter, { name: 'frontmatter' }],
          remarkGfm,
        ],
      }),
    },
    react({ include: /\.(jsx|js|mdx|md|tsx|ts)$/ }),
  ],
  resolve: {
    // @docs points at the repo's docs/ (kept from the prior config for any
    // methodology reference a note figure may pull in).
    alias: {
      '@docs': path.resolve(__dirname, '../docs'),
      // Figures kit, imported by MDX notes (§5.3) — location-independent.
      '@figures': path.resolve(__dirname, 'src/rink/figures'),
    },
  },
  server: {
    fs: {
      allow: [path.resolve(__dirname), path.resolve(__dirname, '../docs')],
    },
  },
})
