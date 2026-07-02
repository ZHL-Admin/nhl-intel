/**
 * TradesFeed (Handoff 8, revised) — the notable-trades card on the Trades landing. Two side-by-side
 * top-10 columns: Most recent (left) and Most lopsided (right). Each row expands the full single-trade
 * detail IN PLACE (no navigation). Shows everything — settled and still-maturing (the latter flagged).
 */
import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { SkeletonLoader } from '../common'
import { getTeamColor, getTeamLogoUrl } from '../../utils/teams'
import { getTradeBoard, TradeBoardItem } from '../../api/trades'
import Tilt from './Tilt'
import TradeBalanceCard from './TradeBalanceCard'
import './trades.css'

const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`
const TOP = 10

// the single biggest asset on the trade, as the row's headline (by realized slot WAR)
function headline(t: TradeBoardItem): string {
  let best = '', val = -Infinity
  for (const s of t.sides) for (const a of s.assets) {
    if (a.war_slot > val) { val = a.war_slot; best = a.label }
  }
  return best
}

function FeedRow({ t, base }: { t: TradeBoardItem; base: string }) {
  const [open, setOpen] = useState(false)
  const win = t.sides.find((s) => s.team_id === t.winner_team_id)
  const lose = t.sides.find((s) => s.team_id !== t.winner_team_id)
  const color = win ? getTeamColor(win.team_abbrev) : 'var(--color-text-muted)'
  const verdictWord = t.incomplete ? 'maturing' : t.verdict === 'decisive' ? '' : t.verdict === 'edge' ? 'edge' : 'even'
  // always show every team's logo + abbrev (winner first when there is one; "over" vs "·" between them)
  const ordered = win && lose ? [win, lose] : t.sides
  const sep = win ? 'over' : '·'
  return (
    <>
      <button className="feed-row" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="feed-row__teams">
          {ordered.map((s, i) => (
            <span key={s.team_abbrev} className="feed-row__tm">
              {i > 0 && <span className="tbl-muted feed-row__sep">{sep}</span>}
              <img src={getTeamLogoUrl(s.team_abbrev)} alt="" className="tbl-logo" loading="lazy" />
              <span className="mono">{s.team_abbrev}</span>
            </span>
          ))}
          <span className="tbl-muted feed-row__meta">· {headline(t)} · {t.date.slice(0, 4)}{verdictWord ? ` · ${verdictWord}` : ''}</span>
        </span>
        <Tilt signed={t.margin_slot} bandHw={t.band_hw_slot} color={color}
          even={t.verdict === 'even'} edge={t.verdict === 'edge' && !t.incomplete}
          incomplete={t.incomplete} size="sparkline" animate={false} />
        <span className="feed-row__net">{fmt(t.margin_slot)}</span>
        <span className="feed-row__chev">{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
      </button>
      {open && (
        <div className="feed-expand">
          <TradeBalanceCard trade={t} defaultOpen fullHref={`${base}/trade/${encodeURIComponent(t.trade_id)}`} />
        </div>
      )}
    </>
  )
}

function FeedCard({ base, sort, title, sub }: { base: string; sort: 'recent' | 'lopsided'; title: string; sub: string }) {
  const [rows, setRows] = useState<TradeBoardItem[] | null>(null)
  useEffect(() => { getTradeBoard({ sort, limit: TOP }).then(setRows).catch(() => setRows([])) }, [sort])
  return (
    <div className="t-panel">
      <div className="t-cardhead">
        <div className="t-cardhead__titles">
          <h2 className="t-panel__title">{title}</h2>
          <p className="t-panel__sub">{sub}</p>
        </div>
      </div>
      <div className="feed-frame">
        {rows ? (rows.length ? rows.map((t) => <FeedRow key={t.trade_id} t={t} base={base} />)
          : <div className="vm-empty">No trades.</div>) : <SkeletonLoader height={320} />}
      </div>
    </div>
  )
}

export default function TradesFeed({ base }: { base: string }) {
  return (
    <div className="feed-two">
      <FeedCard base={base} sort="recent" title="Most recent" sub="The 10 newest trades. Expand any row for the full breakdown." />
      <FeedCard base={base} sort="lopsided" title="Most lopsided" sub="The 10 widest realized margins. Expand any row for the full breakdown." />
    </div>
  )
}
