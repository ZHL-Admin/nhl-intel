/**
 * Trade Outcomes (Handoff 5, Phase D) — the who-won board + per-team trade ledger, in realized WAR.
 * A retrospective on outcomes, never a grade of the decision at the time. Two lenses: slot-expectation
 * (headline; isolates the trade) and actual-player-taken (secondary; conflates trade + drafting).
 * Reuses PlayerAvatar, Tabs, Select, Tooltip, SkeletonLoader, team logos.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react'
import {
  PageLayout, PageHeader, Tabs, Select, Tooltip, SkeletonLoader,
} from '../components/common'
import { DIVISIONS, getTeamLogoUrl } from '../utils/teams'
import {
  getTradeOutcomes, getTradeDetail, getTeamTradeLedger,
  TradeOutcomeRow, TradeDetail, TradeLedgerEntry, TeamTradeLedger,
} from '../api/trades'
import './TradeOutcomes.css'

const TEAMS = DIVISIONS.flatMap((d) => d.teams).sort((a, b) => a.abbrev.localeCompare(b.abbrev))
const SEASONS = ['2025-26', '2024-25', '2023-24', '2022-23', '2021-22', '2020-21',
  '2019-20', '2018-19', '2017-18', '2016-17', '2015-16']

const war = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`
const toneClass = (v: number) => (v > 0.05 ? 'to-pos' : v < -0.05 ? 'to-neg' : 'to-zero')

/** Teams in a trade_id "YYYY-MM-DD-AAA-BBB[-CCC]" — abbrevs after the date. */
function tradeTeams(id: string): string[] {
  return id.split('-').slice(3)
}

function ConfidenceChip({ row }: { row: TradeOutcomeRow }) {
  const flags: string[] = []
  if (row.has_pick) flags.push('includes draft picks (valued at slot expectation)')
  if (row.horizon_incomplete) flags.push('realized window unfinished — recent trade')
  if (row.has_unresolved) flags.push('a player could not be matched to our data')
  return (
    <span className="to-conf-wrap">
      <span className={`to-conf to-conf--${row.confidence}`}>{row.confidence}</span>
      {flags.length > 0 && (
        <Tooltip content={flags.join('; ')}>
          <AlertTriangle size={12} className="to-flag" />
        </Tooltip>
      )}
    </span>
  )
}

function NetCell({ v, lo, hi, headline }: { v: number; lo: number; hi: number; headline?: boolean }) {
  return (
    <span className={`to-net ${headline ? 'to-net--headline' : 'to-net--muted'}`}>
      <span className={`mono ${toneClass(v)}`}>{war(v)}</span>
      <span className="to-band mono">[{lo.toFixed(1)}, {hi.toFixed(1)}]</span>
    </span>
  )
}

function LedgerEntryRow({ e }: { e: TradeLedgerEntry }) {
  const becameLink = e.became_player_id != null
  return (
    <div className="to-led">
      <span className="to-led__asset">
        {e.player_id != null
          ? <Link to={`/players/${e.player_id}`} className="to-led__name">{e.asset}</Link>
          : <span className="to-led__name">{e.asset}</span>}
        {e.type === 'Draft Pick' && becameLink && (
          <span className="to-led__became">→ <Link to={`/players/${e.became_player_id}`}>{e.became_player_name}</Link></span>
        )}
        {e.conditional && <span className="to-led__tag">conditional</span>}
        {e.type === 'Draft Pick' && !becameLink && <span className="to-led__tag to-led__tag--muted">pick unresolved</span>}
      </span>
      <span className="to-led__vals">
        <span className="mono">{e.slot_war.toFixed(1)}</span>
        <span className="mono to-muted">{e.actual_war.toFixed(1)}</span>
      </span>
    </div>
  )
}

function TradeRow({ row, lens }: { row: TradeOutcomeRow; lens: 'slot' | 'actual' }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<TradeDetail | null>(null)
  const others = tradeTeams(row.trade_id).filter((t) => t !== row.team)

  const toggle = () => {
    setOpen((o) => !o)
    if (!detail) getTradeDetail(row.trade_id).then(setDetail).catch(() => setDetail(null))
  }
  const mine = detail?.teams.find((t) => t.team === row.team)

  return (
    <>
      <tr className="to-row" onClick={toggle}>
        <td className="to-row__chev">{open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}</td>
        <td className="to-row__team">
          <img src={getTeamLogoUrl(row.team)} alt="" className="to-logo" loading="lazy" />
          <span className="mono to-row__abbr">{row.team}</span>
          <span className="to-row__vs">vs {others.join(', ')}</span>
        </td>
        <td className="to-row__date mono">{row.trade_date}</td>
        <td className="num"><NetCell v={row.net_war_slot} lo={row.net_war_slot_low} hi={row.net_war_slot_high} headline={lens === 'slot'} /></td>
        <td className="num"><NetCell v={row.net_war_actual} lo={row.net_war_actual_low} hi={row.net_war_actual_high} headline={lens === 'actual'} /></td>
        <td className="num"><ConfidenceChip row={row} /></td>
      </tr>
      {open && (
        <tr className="to-detail">
          <td colSpan={6}>
            {!detail ? <SkeletonLoader height={80} /> : (
              <div className="to-detail__grid">
                <div>
                  <div className="to-detail__head">{row.team} received <span className="to-muted">(slot · actual WAR)</span></div>
                  {mine?.received.length ? mine.received.map((e, i) => <LedgerEntryRow key={i} e={e} />)
                    : <div className="to-muted">—</div>}
                </div>
                <div>
                  <div className="to-detail__head">{row.team} sent</div>
                  {mine?.sent.length ? mine.sent.map((e, i) => <LedgerEntryRow key={i} e={e} />)
                    : <div className="to-muted">—</div>}
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

function Board({ rows, lens }: { rows: TradeOutcomeRow[]; lens: 'slot' | 'actual' }) {
  return (
    <table className="to-table">
      <thead>
        <tr>
          <th></th><th>Team / trade</th><th>Date</th>
          <th className="num"><Tooltip content="Net realized WAR with picks valued at their slot's empirical expectation. The headline lens — it isolates the trade decision from the drafting that followed.">Net (slot)</Tooltip></th>
          <th className="num"><Tooltip content="Net realized WAR with picks valued by the player they actually became. Secondary — it conflates the trade with the drafting, and censors picks from incomplete (2019+) drafts.">Net (actual)</Tooltip></th>
          <th className="num">Conf.</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => <TradeRow key={r.trade_id + r.team} row={r} lens={lens} />)}
      </tbody>
    </table>
  )
}

export default function TradeOutcomes() {
  const [lens, setLens] = useState<'slot' | 'actual'>('slot')
  const [order, setOrder] = useState<'winners' | 'losers'>('winners')
  const [season, setSeason] = useState('')
  const [includeIncomplete, setIncludeIncomplete] = useState(false)
  const [rows, setRows] = useState<TradeOutcomeRow[] | null>(null)

  const [teamId, setTeamId] = useState<number | ''>('')
  const [ledger, setLedger] = useState<TeamTradeLedger | null>(null)

  useEffect(() => {
    setRows(null)
    getTradeOutcomes({ lens, order, season: season || undefined, include_incomplete: includeIncomplete, limit: 40 })
      .then(setRows).catch(() => setRows([]))
  }, [lens, order, season, includeIncomplete])

  useEffect(() => {
    if (teamId === '') { setLedger(null); return }
    setLedger(null)
    getTeamTradeLedger(teamId).then(setLedger).catch(() => setLedger(null))
  }, [teamId])

  const teamOptions = useMemo(
    () => [{ value: '', label: 'Pick a team…' }, ...TEAMS.map((t) => ({ value: String(t.id), label: t.abbrev }))], [])
  const seasonOptions = useMemo(
    () => [{ value: '', label: 'All seasons' }, ...SEASONS.map((s) => ({ value: s, label: s }))], [])

  return (
    <PageLayout>
      <div className="to">
        <PageHeader
          title="Trade Outcomes"
          subtitle="Who actually won each trade since 2015-16, measured in realized WAR. A retrospective on outcomes — not a grade of the decision at the time, when the information available was different."
        />

        <section className="to-section">
          <div className="to-controls">
            <Tabs options={[{ value: 'slot', label: 'Slot lens' }, { value: 'actual', label: 'Actual-player lens' }]}
              value={lens} onChange={(v) => setLens(v as 'slot' | 'actual')} />
            <Tabs options={[{ value: 'winners', label: 'Biggest wins' }, { value: 'losers', label: 'Biggest losses' }]}
              value={order} onChange={(v) => setOrder(v as 'winners' | 'losers')} />
            <Select options={seasonOptions} value={season} onChange={setSeason} />
            <label className="to-check">
              <input type="checkbox" checked={includeIncomplete} onChange={(e) => setIncludeIncomplete(e.target.checked)} />
              include recent (unfinished window)
            </label>
          </div>
          {rows ? <Board rows={rows} lens={lens} /> : <SkeletonLoader height={400} />}
        </section>

        <section className="to-section">
          <h2 className="to-h2">Team trade ledger</h2>
          <p className="to-sub">Every deal a team has made, netted. Slot lens; click a row to see the assets.</p>
          <Select options={teamOptions} value={teamId === '' ? '' : String(teamId)}
            onChange={(v) => setTeamId(v === '' ? '' : Number(v))} />
          {teamId !== '' && (ledger ? (
            <div className="to-ledger">
              <div className="to-ledger__summary">
                <img src={getTeamLogoUrl(ledger.team_abbrev)} alt="" className="to-logo" />
                <span className="mono">{ledger.team_abbrev}</span>
                <span className="to-muted">{ledger.n_trades} trades</span>
                <span>net <span className={`mono ${toneClass(ledger.total_net_slot)}`}>{war(ledger.total_net_slot)}</span> WAR (slot)</span>
                <span className="to-muted">· <span className="mono">{war(ledger.total_net_actual)}</span> (actual)</span>
              </div>
              <Board rows={ledger.trades} lens="slot" />
            </div>
          ) : <SkeletonLoader height={300} />)}
        </section>

        <p className="to-footnote">
          Picks are valued two ways: at the <strong>slot's empirical expectation</strong> (the headline — what
          a pick at that round is worth on average, isolating the trade), and by the <strong>player the pick
          actually became</strong> (secondary — this conflates the trade with the drafting and is unresolved
          when a pick was flipped or its draft is too recent). Pick ownership and three-team sub-deals are not
          in the data and are assumed/flagged. Values are wide-band estimates in WAR; recent trades have
          unfinished realized windows. See the <Link to="/learn/archetypes">methodology</Link> for the full
          assumptions and match rates.
        </p>
      </div>
    </PageLayout>
  )
}
