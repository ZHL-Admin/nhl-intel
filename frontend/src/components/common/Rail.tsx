/**
 * The annotation rail (§6.3): the margin is for theory. On the Dossier template a
 * --rail-width right column carries <Note> sidenotes tied to superscript <Ref> markers in
 * the main column. Below 1200px the rail collapses and each <Ref> becomes a tap-to-open
 * popover carrying the same note (registered through RailProvider).
 *
 * Usage:
 *   <RailProvider>
 *     <div className="dossier__main"> … prose <Ref n={1}/> … </div>
 *     <Rail>
 *       <Note n={1}>WAR is wins above replacement…</Note>
 *       <DataAsOf iso="2026-07-01T12:00:00Z" />
 *     </Rail>
 *   </RailProvider>
 */
import {
  createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState,
  type ReactNode,
} from 'react'
import './Rail.css'

type NoteMap = Map<number, ReactNode>
interface RailCtx {
  register: (n: number, content: ReactNode) => void
  unregister: (n: number) => void
  get: (n: number) => ReactNode | undefined
}
const RailContext = createContext<RailCtx | null>(null)

export function RailProvider({ children }: { children: ReactNode }) {
  const store = useRef<NoteMap>(new Map())
  const [, force] = useState(0)
  const register = useCallback((n: number, content: ReactNode) => {
    store.current.set(n, content)
    force((v) => v + 1)
  }, [])
  const unregister = useCallback((n: number) => {
    store.current.delete(n)
    force((v) => v + 1)
  }, [])
  const get = useCallback((n: number) => store.current.get(n), [])
  const value = useMemo(() => ({ register, unregister, get }), [register, unregister, get])
  return <RailContext.Provider value={value}>{children}</RailContext.Provider>
}

export function Rail({ children }: { children: ReactNode }) {
  return <aside className="rail" role="complementary">{children}</aside>
}

export function Note({ n, italic = false, children }: { n: number; italic?: boolean; children: ReactNode }) {
  const ctx = useContext(RailContext)
  useEffect(() => {
    ctx?.register(n, children)
    return () => ctx?.unregister(n)
  }, [ctx, n, children])
  return (
    <p className={`rail__note ${italic ? 'rail__note--italic' : ''}`} id={`note-${n}`}>
      <sup className="rail__marker">{n}</sup>
      <span className="rail__note-body">{children}</span>
    </p>
  )
}

export function Ref({ n }: { n: number }) {
  const ctx = useContext(RailContext)
  const [open, setOpen] = useState(false)
  const id = useId()
  const wrapRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <span className="ref" ref={wrapRef}>
      <button
        type="button"
        className="ref__marker"
        aria-describedby={`note-${n}`}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        {n}
      </button>
      {open && (
        <span className="ref__popover" id={id} role="note">
          {ctx?.get(n) ?? `Note ${n}`}
        </span>
      )}
    </span>
  )
}

/** Standard "Data as of {timestamp}" note — Spline Sans Mono 11px (§6.3). */
export function DataAsOf({ iso, label = 'Data as of' }: { iso: string; label?: string }) {
  const when = new Date(iso)
  const text = isNaN(when.getTime())
    ? iso
    : when.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
  return <p className="rail__asof">{label} {text}</p>
}
