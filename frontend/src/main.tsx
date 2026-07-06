import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
// The Sheet Design System — self-hosted fonts, one per role (§3). Loaded before index.css.
import '@fontsource-variable/source-serif-4'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './index.css'
import { initTheme } from './utils/theme'

// Apply stored theme before first render to prevent flash
initTheme()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
