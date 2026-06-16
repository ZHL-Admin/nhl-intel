/**
 * Tools index (Phase 5.2, blueprint section 9 row "Tools"): cards linking to each signature tool.
 */
import { Link } from 'react-router-dom'
import { Users } from 'lucide-react'
import { PageLayout } from '../components/common'
import './Tools.css'

const TOOLS = [
  {
    to: '/tools/lineup-lab',
    icon: Users,
    title: 'Lineup Lab',
    blurb: 'Project any forward trio or defense pair from its members’ measured roles and skills — even players who have never shared the ice.',
  },
]

export default function Tools() {
  return (
    <PageLayout>
      <div className="tools-index">
        <h1 className="tools-index__title">Tools</h1>
        <p className="tools-index__sub">
          Interactive models built on the same engine as the rest of the site. Every output is
          explained from the numbers that produced it.
        </p>
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
