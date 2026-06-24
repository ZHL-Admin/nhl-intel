import { MoonStar } from 'lucide-react'

/** Replaces §02 content when the offseason is quiet (no logged moves). Never an empty ledger. */
export default function QuietState({ nextSeason }: { nextSeason: string }) {
  return (
    <div className="qstate">
      <span className="qstate__icon"><MoonStar size={22} /></span>
      <div className="qstate__body">
        <p className="qstate__head">No impactful moves logged yet</p>
        <p className="qstate__text">
          This roster still projects essentially as last season for {nextSeason}. As trades and
          signings are logged, the ledger and the rating change will fill in here.
        </p>
      </div>
    </div>
  )
}
