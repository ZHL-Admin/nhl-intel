import { GoalDetail } from '../../api/types';
import './GoalTooltip.css';

interface GoalTooltipProps {
  detail?: GoalDetail;
  /** Running-score label, e.g. "CAR 3-1" */
  label?: string | null;
  /** Team color used for the top accent border */
  accentColor: string;
  /** Position within the (relative) chart container */
  left: string;
  top: string;
  /** Flip transform so the tooltip stays in bounds */
  transform: string;
}

/**
 * Shared goal popup used by the xG worm and shot-pressure charts: scorer headshot,
 * name, running score, period/clock, strength, and assists.
 */
export default function GoalTooltip({ detail, label, accentColor, left, top, transform }: GoalTooltipProps) {
  return (
    <div className="goal-tooltip" style={{ left, top, transform, borderTopColor: accentColor }}>
      {detail?.scorer_headshot && (
        <img className="goal-tooltip__headshot" src={detail.scorer_headshot} alt={detail.scorer_name || 'Scorer'} />
      )}
      <div className="goal-tooltip__body">
        <div className="goal-tooltip__scorer">{detail?.scorer_name || label || 'Goal'}</div>
        <div className="goal-tooltip__meta">
          {label}
          {detail ? ` · P${detail.period} ${detail.time_in_period} · ${detail.strength}` : ''}
        </div>
        {detail && detail.assists.length > 0 && (
          <div className="goal-tooltip__assists">{detail.assists.join(', ')}</div>
        )}
      </div>
    </div>
  );
}
