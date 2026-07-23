import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'

// RINK THEORY type roles (rebuild §6), mapped onto the fonts already self-hosted
// in this repo. Owner override: Newsreader is the display/heading (and body) face.
// Newsreader (editorial serif): opsz axis → display cut at large sizes, + italic.
import '@fontsource-variable/newsreader/opsz.css'
import '@fontsource-variable/newsreader/opsz-italic.css'
// Archivo (nav / UI chrome): wdth axis, + italic.
import '@fontsource-variable/archivo/wdth.css'
import '@fontsource-variable/archivo/wdth-italic.css'
// Spline Sans Mono (labels, dates, captions, all numbers): 400/500.
import '@fontsource/spline-sans-mono/400.css'
import '@fontsource/spline-sans-mono/500.css'

// Legacy design-system layers first (for the salvaged tool pages), then the rink
// tokens + shell (single fixed paper theme; no dark-mode toggle in v1). Rink is
// imported last so it wins any shared declaration.
import './rink/legacy-tools.css'
import './rink/tokens.css'
import './rink/shell/shell.css'
import './rink/pages/pages.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
