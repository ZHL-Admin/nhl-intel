import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
// The Sheet Design System v2 — self-hosted fonts, one per role (§3). Loaded before index.css.
// Newsreader (editorial voice): opsz axis so large sizes get the display cut automatically, + italic.
import '@fontsource-variable/newsreader/opsz.css'
import '@fontsource-variable/newsreader/opsz-italic.css'
// Archivo (the machine): wdth axis for dense-table 92 / eyebrow 110 widths, + italic.
import '@fontsource-variable/archivo/wdth.css'
import '@fontsource-variable/archivo/wdth-italic.css'
// Spline Sans Mono (micro-labels only): 400/500 weights.
import '@fontsource/spline-sans-mono/400.css'
import '@fontsource/spline-sans-mono/500.css'
import './index.css'
import { initTheme } from './utils/theme'

// Apply stored theme before first render to prevent flash
initTheme()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
