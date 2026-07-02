/**
 * TeamsGms (Handoff 9) — Tab 2, one card. Confidence-aware: the point-estimate net records are mostly
 * inside band noise, so the ranked region is sorted by the EB-shrunk rank_value, layers a σ cue
 * (clear / leans / noise), shows raw net beside it, and COLLAPSES the indistinguishable majority into a
 * "within noise of even" cluster instead of a false 1..N ordering. The value map keeps raw coordinates —
 * the cue is visual emphasis only. Framing leads with uncertainty, not "who's best at trading".
 */
import { useEffect, useMemo, useState } from 'react'
import { Tabs, Select, SkeletonLoader } from '../common'
import { getTeamColor, getTeamLogoUrl } from '../../utils/teams'
import { getValueMap, ValueMapPoint } from '../../api/trades'
import ValueMap from './ValueMap'
import Tilt from './Tilt'
import './trades.css'

const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`
type Kind = 'team' | 'gm'

function RankedRow({ e, kind, onOpenEntity }: { e: ValueMapPoint; kind: Kind; onOpenEntity: (k: Kind, id: string) => void }) {
  return (
    <div className={`tg-row ${e.separation === 'clear' ? 'tg-row--clear' : 'tg-row--leans'}`} onClick={() => onOpenEntity(kind, e.id)}>
      <span className="lb-name">
        <img src={getTeamLogoUrl(e.team_abbrev_for_color)} alt="" className="tbl-logo" loading="lazy" />
        <span>{e.label}</span>
        {e.separation === 'clear'
          ? <span className="lb-sep lb-sep--clear">clearly separated</span>
          : <span className="lb-sep lb-sep--leans">leans (within ±band)</span>}
        {e.low_n && <span className="lb-sep lb-sep--leans">few trades</span>}
      </span>
      <Tilt signed={e.net_war} bandHw={e.net_band_hw} color={getTeamColor(e.team_abbrev_for_color)}
        even={e.separation === 'noise'} incomplete={false} size="sparkline" animate={false} />
      <span className={`lb-net ${e.net_war >= 0 ? 'dos-pos' : 'dos-neg'}`} title={`confidence-shrunk rank value ${fmt(e.rank_value)}`}>
        {fmt(e.net_war)} <span className="tg-row__adj">adj {fmt(e.rank_value)}</span>
      </span>
    </div>
  )
}

export default function TeamsGms({ kind, onKind, onOpenEntity }: {
  kind: Kind; onKind: (k: Kind) => void
  onOpenEntity: (kind: Kind, id: string) => void
}) {
  const [points, setPoints] = useState<ValueMapPoint[] | null>(null)
  const [rank, setRank] = useState<'best' | 'worst'>('best')

  useEffect(() => { setPoints(null); getValueMap(kind).then(setPoints).catch(() => setPoints([])) }, [kind])

  const { separated, noiseCount, lowNCount } = useMemo(() => {
    if (!points) return { separated: null as ValueMapPoint[] | null, noiseCount: 0, lowNCount: 0 }
    // emphasize only entities that separate from even AND have enough trades to trust; low-n entities
    // (a tiny band can manufacture a big z on a meaningless net) are set aside, not ranked.
    const sep = points.filter((p) => p.separation !== 'noise' && !p.low_n)
    const side = sep.filter((p) => rank === 'best' ? p.net_war > 0 : p.net_war < 0)
    // rank_value is the primary key; it collapses to the league mean when the spread is all noise, so
    // break ties on raw net to keep a sensible order.
    side.sort((a, b) => (rank === 'best' ? b.rank_value - a.rank_value : a.rank_value - b.rank_value)
      || (rank === 'best' ? b.net_war - a.net_war : a.net_war - b.net_war))
    return {
      separated: side,
      noiseCount: points.filter((p) => p.separation === 'noise' && !p.low_n).length,
      lowNCount: points.filter((p) => p.low_n).length,
    }
  }, [points, rank])

  const noun = kind === 'team' ? 'teams' : 'GMs'

  return (
    <div className="t-panel">
      <div className="t-cardhead">
        <div className="t-cardhead__titles">
          <h2 className="t-panel__title">{kind === 'team' ? 'Teams as traders' : 'GMs as traders'}</h2>
          <p className="t-panel__sub">
            Trade records spread widely, but most of the spread is measurement noise. Only a couple of front
            offices separate from even beyond their margin of error — the rest aren't distinguishable from luck.
          </p>
        </div>
        <div className="t-cardhead__controls">
          <Tabs options={[{ value: 'team', label: 'Teams' }, { value: 'gm', label: 'GMs' }]}
            value={kind} onChange={(v) => onKind(v as Kind)} />
        </div>
      </div>

      <div className="tg-two">
        <div>
          {points ? <ValueMap points={points} onSelect={(id) => onOpenEntity(kind, id)} /> : <SkeletonLoader height={460} />}
        </div>
        <div>
          <div className="t-cardhead">
            <h3 className="t-region-title">{rank === 'best' ? 'Separated above even' : 'Separated below even'}</h3>
            <Select value={rank} onChange={(v) => setRank(v as any)}
              options={[{ value: 'best', label: 'Best' }, { value: 'worst', label: 'Worst' }]} />
          </div>
          {separated ? (
            <>
              {separated.length
                ? separated.map((e) => <RankedRow key={e.id} e={e} kind={kind} onOpenEntity={onOpenEntity} />)
                : <div className="vm-empty">None separated from even on this side.</div>}
              {noiseCount > 0 && (
                <div className="lb-cluster">
                  <b>{noiseCount} {noun}</b> within noise of even — records not distinguishable from luck (net inside ±1 band of zero).
                </div>
              )}
              {lowNCount > 0 && (
                <div className="t-note" style={{ marginTop: 'var(--space-2)' }}>
                  {lowNCount} {noun} with too few settled trades to rank (set aside).
                </div>
              )}
            </>
          ) : <SkeletonLoader height={360} />}
        </div>
      </div>

      <p className="t-note" style={{ marginTop: 'var(--space-4)' }}>
        Ranked by a confidence-aware figure (records shrunk toward even by their own uncertainty), not raw net;
        raw net is shown beside each row. Settled-only — still-maturing trades aren't counted here and appear,
        flagged, in each entity's dossier deal list.
      </p>
    </div>
  )
}
