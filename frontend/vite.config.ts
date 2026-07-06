import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// P4: `@docs` points at the repo's docs/ so the Learn methods library can render
// docs/methodology/*.md on-site; server.fs.allow lets the dev server read it (it lives outside the
// frontend root). This is the one sanctioned vite config change in the site-cohesion work.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@docs': path.resolve(__dirname, '../docs'),
    },
  },
  server: {
    fs: {
      allow: [path.resolve(__dirname), path.resolve(__dirname, '../docs')],
    },
  },
})
