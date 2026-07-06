/**
 * Writing library (P4). `/learn/writing` lists posts from the manifest (config/writing.ts), newest
 * first; `/learn/writing/:slug` renders the post's markdown from frontend/content/writing. The
 * manifest ships empty (owner-supplied copy), so the index shows an honest empty state until then.
 */
import { useParams, Link } from 'react-router-dom'
import { PageLayout, PageCard } from '../components/common'
import { usePageTitle } from '../hooks/usePageTitle'
import DocMarkdown from '../components/learn/DocMarkdown'
import { WRITING } from '../config/writing'
import { getWritingDoc } from '../utils/docs'
import './Learn.css'

const fmtDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })

function WritingIndex() {
  usePageTitle('Writing')
  return (
    <PageLayout>
      <PageCard title="Writing" subtitle="Essays and deep dives on how the numbers behave.">
        {WRITING.length === 0
          ? <p className="lib__empty">No posts yet — the first one is on the way.</p>
          : WRITING.map((p) => (
              <Link key={p.slug} to={`/learn/writing/${p.slug}`} className="lib__row">
                <span className="lib__row-title">{p.title}</span>
                <span className="lib__row-blurb">{p.dek}</span>
                <span className="lib__row-date">{fmtDate(p.date)}</span>
              </Link>
            ))}
      </PageCard>
    </PageLayout>
  )
}

function WritingPost({ slug }: { slug: string }) {
  const entry = WRITING.find((p) => p.slug === slug)
  const doc = getWritingDoc(slug)
  const found = !!(entry && doc)
  usePageTitle(found ? entry!.title : 'Writing')
  return (
    <PageLayout>
      <PageCard
        title={found ? entry!.title : 'Not found'}
        subtitle={found ? `${fmtDate(entry!.date)} · ${entry!.dek}` : undefined}
        back={{ to: '/learn/writing', label: 'Writing' }}
      >
        {found
          ? <DocMarkdown content={doc!} />
          : <p className="lib__notfound">This post isn’t available yet.</p>}
      </PageCard>
    </PageLayout>
  )
}

export default function Writing() {
  const { slug } = useParams<{ slug: string }>()
  return slug ? <WritingPost slug={slug} /> : <WritingIndex />
}
