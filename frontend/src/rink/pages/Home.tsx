import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import Masthead from '../shell/Masthead'
import Footer from '../shell/Footer'
import Rail from '../home/Rail'
import { listNotes } from '../notes/registry'
import { tagColor, fmtDate } from '../notes/tags'
import '../home/rail.css'
import '../home/home.css'
import '../notes/notes.css'

/**
 * Home (§3.1). Masthead → hero band (lead note = newest published) → two columns
 * (RECENT NOTES feed left, the live rail right) → footer.
 *
 * Thumbnails/cover figures are omitted in v1 (no thumbnail system yet): the feed
 * rows and the lead are text-only. Empty states are explicit — see below.
 */
export default function Home() {
  useEffect(() => { document.title = 'Rink Theory' }, [])
  const notes = listNotes()
  const lead = notes[0]        // newest published (or newest draft in dev)
  const recent = notes.slice(1)

  return (
    <>
      <Masthead />

      {/* Lead note in the faint-orange hero band. Absent when there are no notes. */}
      {lead && (
        <section className="rt-hero">
          <div className="rt-container">
            <article className="rt-lead">
              <div className="rt-lead__kicker">Research Note · {fmtDate(lead.date)}</div>
              <h2 className="rt-lead__headline">
                <Link to={`/notes/${lead.slug}`}>{lead.title}</Link>
              </h2>
              {lead.dek && <p className="rt-lead__dek">{lead.dek}</p>}
              <Link className="rt-lead__more" to={`/notes/${lead.slug}`}>Continue reading →</Link>
            </article>
          </div>
        </section>
      )}

      <main className="rt-main">
        <div className="rt-container rt-home">
          <div>
            {notes.length === 0 ? (
              // Zero published notes: no hero above; a quiet line here.
              <p className="rt-home__nonotes">No notes published yet.</p>
            ) : (
              <>
                <div className="rt-feedhead">Recent notes</div>
                {recent.length > 0 ? (
                  <>
                    <div className="rt-notelist">
                      {recent.map((n) => (
                        <Link key={n.slug} to={`/notes/${n.slug}`} className="rt-noterow">
                          <div className="rt-noterow__meta">
                            {fmtDate(n.date)}
                            {n.tags?.[0] && (
                              <> · <span className="rt-noterow__tag" style={{ color: tagColor(n.tags[0]) }}>{n.tags[0]}</span></>
                            )}
                            {n.status === 'draft' && <> · <span className="rt-noterow__draft">Draft</span></>}
                          </div>
                          <h3 className="rt-noterow__title">{n.title}</h3>
                          {n.dek && <p className="rt-noterow__dek">{n.dek}</p>}
                        </Link>
                      ))}
                    </div>
                    <Link className="rt-feed__all" to="/notes">All notes →</Link>
                  </>
                ) : (
                  // Exactly one note: lead shows in the hero; feed has nothing yet.
                  <p className="rt-feedempty">More notes soon.</p>
                )}
              </>
            )}
          </div>
          <Rail />
        </div>
      </main>

      <Footer />
    </>
  )
}
