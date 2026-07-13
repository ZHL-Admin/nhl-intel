/**
 * Methods library (P4). `/learn/methods` is a grouped index of the methodology docs; each row links
 * to `/learn/methods/:slug`, which renders that doc on-site. Curated entries (config/methods.ts)
 * group and title the important docs; any other .md on disk still appears under "More" so nothing is
 * hidden. No dates are shown — the docs carry no date header.
 */
import { useParams, Link } from 'react-router-dom'
import { PageLayout, PageCard } from '../components/common'
import { usePageTitle } from '../hooks/usePageTitle'
import DocMarkdown from '../components/learn/DocMarkdown'
import { METHODS, GROUP_ORDER, MORE_GROUP, USED_ON } from '../config/methods'
import { GAMES_ENABLED } from '../config/features'
import { getMethodDoc, ALL_METHOD_SLUGS } from '../utils/docs'
import './Learn.css'

interface Row { slug: string; title: string; blurb?: string }

function buildGroups(): { group: string; rows: Row[] }[] {
  const curatedSlugs = new Set(METHODS.map((m) => m.slug))
  const groups: { group: string; rows: Row[] }[] = []

  for (const group of GROUP_ORDER) {
    if (group === MORE_GROUP) continue
    const rows = METHODS.filter((m) => m.group === group).map((m) => ({ slug: m.slug, title: m.title, blurb: m.blurb }))
    if (rows.length) groups.push({ group, rows })
  }

  // Any doc on disk not curated above → "More", filename as title, so new docs never go missing.
  const extra = ALL_METHOD_SLUGS.filter((s) => !curatedSlugs.has(s)).sort()
    .map((s) => ({ slug: s, title: s }))
  if (extra.length) groups.push({ group: MORE_GROUP, rows: extra })

  return groups
}

function MethodsIndex() {
  usePageTitle('Methods')
  const groups = buildGroups()
  return (
    <PageLayout>
      <PageCard title="Methods" subtitle="Every model on the site, documented and open to check.">
        {groups.map(({ group, rows }) => (
          <section key={group} className="lib__group">
            <h2 className="lib__group-head">{group}</h2>
            {rows.map((r) => (
              <Link key={r.slug} to={`/learn/methods/${r.slug}`} className="lib__row">
                <span className="lib__row-title">{r.title}</span>
                {r.blurb && <span className="lib__row-blurb">{r.blurb}</span>}
              </Link>
            ))}
          </section>
        ))}
      </PageCard>
    </PageLayout>
  )
}

function MethodDoc({ slug }: { slug: string }) {
  const doc = getMethodDoc(slug)
  const meta = METHODS.find((m) => m.slug === slug)
  const title = meta?.title ?? slug
  usePageTitle(doc ? title : 'Methods')
  return (
    <PageLayout>
      <PageCard title={doc ? title : 'Not found'} back={{ to: '/learn/methods', label: 'Methods' }}>
        {doc
          ? <DocMarkdown content={doc} />
          : <p className="lib__notfound">No methodology doc found for “{slug}”.</p>}
        {doc && USED_ON[slug]?.length > 0 && (
          <div className="method-usedon">
            <span className="method-usedon__label">Used on</span>
            {USED_ON[slug].filter((u) => GAMES_ENABLED || !u.to.startsWith('/games')).map((u) => <Link key={u.to + u.label} to={u.to} className="method-usedon__link">{u.label}</Link>)}
          </div>
        )}
      </PageCard>
    </PageLayout>
  )
}

export default function Methods() {
  const { slug } = useParams<{ slug: string }>()
  return slug ? <MethodDoc slug={slug} /> : <MethodsIndex />
}
