import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import Shell from '../shell/Shell'
import { listNotes } from '../notes/registry'
import { tagColor, fmtDate } from '../notes/tags'
import '../notes/notes.css'

/** Notes index (§3.3): reverse-chron list, full history. */
export default function NotesIndex() {
  useEffect(() => { document.title = 'Notes · Rink Theory' }, [])
  const notes = listNotes()

  return (
    <Shell>
      <h1 className="rt-pagetitle">Notes</h1>
      {notes.length === 0 && (
        <p className="rt-intro">No published notes yet.</p>
      )}
      <div className="rt-notelist">
        {notes.map((n) => (
          <Link key={n.slug} to={`/notes/${n.slug}`} className="rt-noterow">
            <div className="rt-noterow__meta">
              {fmtDate(n.date)}
              {n.tags?.[0] && (
                <> · <span className="rt-noterow__tag" style={{ color: tagColor(n.tags[0]) }}>{n.tags[0]}</span></>
              )}
              {n.status === 'draft' && <> · <span className="rt-noterow__draft">Draft</span></>}
            </div>
            <h2 className="rt-noterow__title">{n.title}</h2>
            {n.dek && <p className="rt-noterow__dek">{n.dek}</p>}
          </Link>
        ))}
      </div>
    </Shell>
  )
}
