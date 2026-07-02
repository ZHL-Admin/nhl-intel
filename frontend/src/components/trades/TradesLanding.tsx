/**
 * TradesLanding (Handoff 8) — Tab 1, the default landing. Two cards: a prominent search card (find a
 * team, GM, player, or trade) with a 32-team quick-jump, and the notable-trades feed. Serves the dominant
 * "my team" and "settle an argument about one trade" intents before any chart.
 */
import { TeamQuickJump } from '../common'
import TradeSearch from './TradeSearch'
import TradesFeed from './TradesFeed'
import './trades.css'

export default function TradesLanding({ base, onOpenEntity, onOpenTrade }: {
  base: string
  onOpenEntity: (kind: 'team' | 'gm', id: string) => void
  onOpenTrade: (tradeId: string) => void
}) {
  return (
    <div className="tr-landing">
      <div className="t-panel">
        <TradeSearch large onPickEntity={onOpenEntity} onPickTrade={onOpenTrade} />
        <p className="t-panel__sub tr-search__sub">Jump to a team or GM's record, a player, or a specific deal.</p>
        <div className="tr-quickjump-wrap">
          <TeamQuickJump onPick={(ab) => onOpenEntity('team', ab)} />
        </div>
      </div>

      <div className="t-divider" />

      <TradesFeed base={base} />
    </div>
  )
}
