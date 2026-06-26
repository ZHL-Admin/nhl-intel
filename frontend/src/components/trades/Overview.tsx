/**
 * Overview (Handoff 7 §4.1) — the oriented landing dashboard. Not a lone chart: a hero stat band that
 * frames the dataset and answers the founding question, the single most lopsided trade as a marquee, the
 * value map beside a leaderboard, and a patterns teaser. Everything shares the tilt language.
 */
import { useEffect, useState } from 'react'
import { ChartPanel, SkeletonLoader } from '../common'
import {
  getThesisSummary, getValueMap, getBoardItem,
  ThesisSummary, ValueMapPoint, TradeBoardItem,
} from '../../api/trades'
import ValueMap from './ValueMap'
import Leaderboards from './Leaderboards'
import TradeBalanceCard from './TradeBalanceCard'
import './trades.css'

const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`

export default function Overview({ kind, lens, onOpenTrade, onOpenEntity, onGoPatterns }: {
  kind: 'team' | 'gm'; lens: 'slot' | 'actual'
  onOpenTrade: (id: string) => void
  onOpenEntity: (k: 'team' | 'gm', id: string) => void
  onGoPatterns: () => void
}) {
  const [thesis, setThesis] = useState<ThesisSummary | null>(null)
  const [marquee, setMarquee] = useState<TradeBoardItem | null>(null)
  const [points, setPoints] = useState<ValueMapPoint[] | null>(null)

  useEffect(() => {
    getThesisSummary(lens).then((t) => {
      setThesis(t)
      if (t.biggest_fleece?.trade_id) getBoardItem(t.biggest_fleece.trade_id).then(setMarquee).catch(() => {})
    }).catch(() => setThesis(null))
  }, [lens])
  useEffect(() => { setPoints(null); getValueMap(kind, lens).then(setPoints).catch(() => setPoints([])) }, [kind, lens])

  return (
    <div className="ov">
      {/* hero stat band */}
      {thesis ? (
        <div className="ov-hero">
          <div className="ov-stat">
            <div className="ov-stat__l">trades graded</div>
            <div className="ov-stat__v">{thesis.trades_graded}</div>
            <div className="ov-stat__sub">2015-16 to a complete window</div>
          </div>
          <div className="ov-stat">
            <div className="ov-stat__l">decisive vs too-close</div>
            <div className="ov-stat__v">{thesis.decisive_pct}% / {thesis.too_close_pct}%</div>
            <div className="ov-stat__sub">most trades are even within the band</div>
          </div>
          <div className="ov-stat ov-stat--clickable" onClick={() => thesis.biggest_fleece?.trade_id && onOpenTrade(thesis.biggest_fleece.trade_id)}>
            <div className="ov-stat__l">biggest fleece</div>
            <div className="ov-stat__v">{thesis.biggest_fleece?.winner ?? '—'}</div>
            <div className="ov-stat__sub">won by {fmt(thesis.biggest_fleece?.margin ?? 0)} WAR · {thesis.biggest_fleece?.date?.slice(0, 4)}</div>
          </div>
          <div className="ov-stat ov-stat--clickable" onClick={onGoPatterns}>
            <div className="ov-stat__l">player for picks</div>
            <div className="ov-stat__v">{thesis.player_for_picks?.player_side_won_pct}%</div>
            <div className="ov-stat__sub">the side that got the player won, over {thesis.player_for_picks?.trade_count} deals</div>
          </div>
        </div>
      ) : <SkeletonLoader height={120} />}

      {/* marquee trade */}
      {marquee && (
        <div className="ov-marquee">
          <h2 className="ov-section-title">The most lopsided trade on record</h2>
          <TradeBalanceCard trade={marquee} lens={lens} defaultOpen />
        </div>
      )}

      {/* map + leaderboard */}
      <div className="ov-two">
        <ChartPanel title="The league trade map" subtitle="value gained vs given up; above the diagonal is a net winner. Click an entity for its dossier.">
          {points ? <ValueMap points={points} onSelect={(id) => onOpenEntity(kind, id)} /> : <SkeletonLoader height={460} />}
        </ChartPanel>
        <div>
          <h2 className="ov-section-title">Leaderboards</h2>
          <Leaderboards lens={lens} onOpenTrade={onOpenTrade} onOpenEntity={onOpenEntity} />
        </div>
      </div>

      {/* patterns teaser */}
      {thesis && (
        <div>
          <h2 className="ov-section-title">Do the classic trade theses hold?</h2>
          <div className="ov-teaser">
            <button className="ov-teaser__chip" onClick={onGoPatterns}>
              player for picks: the player side won <b>{thesis.player_for_picks?.player_side_won_pct}%</b>
            </button>
            <button className="ov-teaser__chip" onClick={onGoPatterns}>explore player-for-player, blockbusters, and deadline timing →</button>
          </div>
        </div>
      )}

      <p className="ov-howto">
        Reading the tilt: each bar fills toward the winner by the realized margin; the shaded band is the
        uncertainty, and when it crosses the centre the trade is too close to call. Numbers are the slot
        lens (picks valued at their slot's expectation) — a retrospective on outcomes, not a grade of the
        decision at the time.
      </p>
    </div>
  )
}
