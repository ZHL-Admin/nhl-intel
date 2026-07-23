import { useEffect } from 'react'

/**
 * Step-2 placeholder. The shell wires every Section-2 route now; the body of
 * each page is filled in by the later build steps (Notes → Ratings → Tools →
 * Home). This makes the route real and testable without pretending the content
 * exists. Removed before the ship gate.
 */
export default function Placeholder({
  title,
  kicker,
  step,
  note,
}: {
  title: string
  kicker?: string
  step: string
  note?: string
}) {
  useEffect(() => {
    document.title = `${title} · Rink Theory`
  }, [title])

  return (
    <>
      {kicker && <div className="rt-kicker">{kicker}</div>}
      <h1 className="rt-pagetitle">{title}</h1>
      <div className="rt-placeholder">
        <strong>Placeholder.</strong> This route is wired in the shell; its content
        arrives in <code>{step}</code>.{note ? ` ${note}` : ''}
      </div>
    </>
  )
}
