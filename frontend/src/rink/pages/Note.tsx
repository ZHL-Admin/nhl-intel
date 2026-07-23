import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import Shell from '../shell/Shell'
import { findNote, noteBody, neighbors } from '../notes/registry'
import { tagColor, fmtDate } from '../notes/tags'
import '../notes/notes.css'

/** A single note (§3.2): kicker, title, meta line, MDX body, prev/next. */
export default function Note() {
  const { slug = '' } = useParams()
  const note = findNote(slug)

  useEffect(() => {
    document.title = note ? `${note.title} · Rink Theory` : 'Note · Rink Theory'
  }, [note])

  const Body = note ? noteBody(note.path) : undefined

  if (!note || !Body) {
    // Drafts are not visible in production; an unknown/hidden slug lands here.
    return (
      <Shell>
        <div className="rt-reading">
          <div className="rt-kicker">Not found</div>
          <h1 className="rt-pagetitle">No such note</h1>
          <p className="rt-intro">This note isn’t published. <Link to="/notes">All notes →</Link></p>
        </div>
      </Shell>
    )
  }

  const { prev, next } = neighbors(slug)

  return (
    <Shell>
      <article className="rt-reading">
        <div className="rt-note__kicker">Research Note</div>
        <h1 className="rt-note__title">{note.title}</h1>
        <div className="rt-note__metaline">
          {fmtDate(note.date)}
          {note.tags?.length ? (
            <> · {note.tags.map((t, i) => (
              <span key={t}>
                {i > 0 && ', '}
                <span className="rt-noterow__tag" style={{ color: tagColor(t) }}>{t}</span>
              </span>
            ))}</>
          ) : null}
          {note.readingTime && <> · {note.readingTime}</>}
          {note.status === 'draft' && <> · <span className="rt-noterow__draft">Draft</span></>}
        </div>

        <div className="rt-prose">
          <Body />
        </div>

        {note.tool && (
          <div className="rt-note__explore">
            <span>Explore the data</span>
            <Link to={note.tool}>Open →</Link>
          </div>
        )}

        <div className="rt-note__nav">
          <span>{prev ? <Link to={`/notes/${prev.slug}`}>← {prev.title}</Link> : <span />}</span>
          <Link to="/notes">All notes →</Link>
          <span>{next ? <Link to={`/notes/${next.slug}`}>{next.title} →</Link> : <span />}</span>
        </div>
      </article>
    </Shell>
  )
}
