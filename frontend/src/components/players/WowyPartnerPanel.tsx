/**
 * WOWY partner panel — on the player profile (Impact & Value tab). A sortable list of a
 * player's 5v5 linemates showing the on-ice xGF% together vs the focal player apart, the lift,
 * and shared TOI. Small-sample pairings (< 50 shared minutes) carry the shared small-sample
 * badge. Clicking a partner navigates to that player's profile. Data from mart_player_wowy via
 * GET /players/{id}/wowy.
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { WowyPartner } from '../../api/types'
import Badge from '../common/Badge'
import Tooltip from '../common/Tooltip'
import './WowyPartnerPanel.css'

const pct = (v?: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}`)
const signedPct = (v?: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}`)
const mins = (s: number) => (s / 60).toFixed(0)

type SortKey = 'toi' | 'lift'

export default function WowyPartnerPanel({ partners, name }: { partners: WowyPartner[]; name: string }) {
  const nav = useNavigate()
  const [sort, setSort] = useState<SortKey>('toi')
  const last = name.split(' ').slice(-1)[0]

  const rows = useMemo(() => {
    const r = [...partners]
    r.sort((a, b) =>
      sort === 'toi'
        ? b.toi_together_sec - a.toi_together_sec
        : (b.together_minus_focal_alone ?? -Infinity) - (a.together_minus_focal_alone ?? -Infinity))
    return r
  }, [partners, sort])

  if (!partners.length) return null

  const go = (id: number) => nav(`/players/${id}`)

  return (
    <div className="wowy">
      <div className="wowy__head">
        <h3 className="wowy__title">{last} with and without each linemate</h3>
        <div className="wowy__sort" role="tablist" aria-label="sort partners">
          <button type="button" className={`wowy__sortbtn${sort === 'toi' ? ' is-active' : ''}`} onClick={() => setSort('toi')}>Most minutes</button>
          <button type="button" className={`wowy__sortbtn${sort === 'lift' ? ' is-active' : ''}`} onClick={() => setSort('lift')}>Biggest lift</button>
        </div>
      </div>
      <p className="wowy__caption">
        {last}'s on-ice 5v5 xGF% together vs apart. <strong>Positive lift = {last} is better alongside that partner.</strong>
      </p>

      <div className="wowy__table">
        <div className="wowy__row wowy__row--head">
          <span className="wowy__c wowy__c--name">Partner</span>
          <Tooltip content="Shared 5v5 minutes with this partner."><span className="wowy__c wowy__c--num">TOI</span></Tooltip>
          <Tooltip content={`On-ice 5v5 xGF% with ${last} and this partner together.`}><span className="wowy__c wowy__c--num">Together</span></Tooltip>
          <Tooltip content={`On-ice 5v5 xGF% for ${last} apart from this partner.`}><span className="wowy__c wowy__c--num">Apart</span></Tooltip>
          <Tooltip content="Together minus apart: how much the pairing lifts on-ice xGF% versus the focal player without this partner."><span className="wowy__c wowy__c--num">Lift</span></Tooltip>
        </div>

        {rows.map((p) => {
          const lift = p.together_minus_focal_alone
          const liftClass = lift != null && lift > 0 ? ' is-pos' : lift != null && lift < 0 ? ' is-neg' : ''
          return (
            <div
              key={p.partner_id}
              className="wowy__row wowy__row--link"
              role="button"
              tabIndex={0}
              onClick={() => go(p.partner_id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(p.partner_id) } }}
            >
              <span className="wowy__c wowy__c--name">
                <span className="wowy__pname">{p.partner_name ?? `#${p.partner_id}`}</span>
                {p.small_sample && (
                  <Tooltip content="Under 50 shared minutes — a small sample; read the split with caution.">
                    <span className="wowy__ss"><Badge variant="small-sample" /></span>
                  </Tooltip>
                )}
              </span>
              <span className="wowy__c wowy__c--num wowy__num">{mins(p.toi_together_sec)}<small>m</small></span>
              <span className="wowy__c wowy__c--num wowy__num">{pct(p.xgf_pct_together)}</span>
              <span className="wowy__c wowy__c--num wowy__num">{pct(p.xgf_pct_focal_without_partner)}</span>
              <span className={`wowy__c wowy__c--num wowy__num${liftClass}`}>{signedPct(lift)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
