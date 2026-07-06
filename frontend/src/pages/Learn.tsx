/**
 * Learn hub (P4) — the credibility pillar. Inset cards to the site's explainer surfaces. The About
 * card ships hidden until its copy exists (D-note: placeholder lorem is forbidden).
 */
import { Link } from 'react-router-dom'
import { PageLayout, PageCard } from '../components/common'
import { usePageTitle } from '../hooks/usePageTitle'
import './Learn.css'

interface LearnCard { name: string; blurb: string; to: string }

const CARDS: LearnCard[] = [
  { name: 'Archetypes', blurb: 'The playing-style clusters, and how a player lands in one.', to: '/learn/archetypes' },
  { name: 'Methods', blurb: 'Every model on the site, documented and open to check.', to: '/learn/methods' },
  { name: 'Writing', blurb: 'Essays and deep dives on how the numbers behave.', to: '/learn/writing' },
  // About card is intentionally omitted until the owner supplies its copy (no lorem).
]

export default function Learn() {
  usePageTitle('Learn')
  return (
    <PageLayout>
      <PageCard title="Learn" subtitle="How everything here is measured, and why you can check it.">
        <div className="learn__grid">
          {CARDS.map((c) => (
            <Link key={c.to} to={c.to} className="page-inset learn__card">
              <span className="learn__card-name">{c.name}</span>
              <span className="learn__card-blurb">{c.blurb}</span>
            </Link>
          ))}
        </div>
      </PageCard>
    </PageLayout>
  )
}
