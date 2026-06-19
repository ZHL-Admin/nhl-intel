/**
 * Tools index (Phase 5.2, blueprint section 9 row "Tools"): cards linking to each signature tool.
 */
import { Link } from 'react-router-dom'
import { Users, ArrowLeftRight, Scale } from 'lucide-react'
import { PageLayout, PageHeader } from '../components/common'
import './Tools.css'

const TOOLS = [
  {
    to: '/tools/lineup-lab',
    icon: Users,
    title: 'Lineup Lab',
    blurb: 'Project any forward trio or defense pair from its members’ measured roles and skills — even players who have never shared the ice.',
  },
  {
    to: '/tools/trade-fit',
    icon: ArrowLeftRight,
    title: 'Trade Fit',
    blurb: 'Score how well a player addresses a team’s biggest archetype and component gaps versus the league’s top teams.',
  },
  {
    to: '/tools/trade-builder',
    icon: Scale,
    title: 'Trade Builder',
    blurb: 'Build a real multi-team trade with salary retention and read each side as a decomposition — talent, cost-efficiency, and fit — with a soft cap check.',
  },
]

export default function Tools() {
  return (
    <PageLayout>
      <div className="tools-index">
        <PageHeader
          title="Tools"
          subtitle="Interactive models built on the same engine as the rest of the site. Every output is explained from the numbers that produced it."
        />
        <div className="tools-index__grid">
          {TOOLS.map(({ to, icon: Icon, title, blurb }) => (
            <Link key={to} to={to} className="tools-index__card">
              <div className="tools-index__icon"><Icon size={22} /></div>
              <h2 className="tools-index__card-title">{title}</h2>
              <p className="tools-index__card-blurb">{blurb}</p>
            </Link>
          ))}
        </div>
      </div>
    </PageLayout>
  )
}
