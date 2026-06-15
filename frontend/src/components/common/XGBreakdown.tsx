import { ShotAttempt } from '../../api/types';
import './XGBreakdown.css';

/** A shot-like object carrying the in-house xG decomposition fields. */
type XGShot = Pick<
  ShotAttempt,
  | 'xg'
  | 'base_rate'
  | 'xg_contrib_location'
  | 'xg_contrib_shot_type'
  | 'xg_contrib_strength'
  | 'xg_contrib_sequence'
  | 'xg_contrib_game_state'
>;

interface Part {
  label: string;
  value: number;
}

const BUCKETS: { key: keyof XGShot; label: string }[] = [
  { key: 'xg_contrib_location', label: 'location' },
  { key: 'xg_contrib_shot_type', label: 'shot type' },
  { key: 'xg_contrib_strength', label: 'strength' },
  { key: 'xg_contrib_sequence', label: 'sequence' },
  { key: 'xg_contrib_game_state', label: 'game state' },
];

const fmtSigned = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(2)}`;

/**
 * Ordered, non-trivial decomposition parts (largest absolute contribution first).
 * Shared by the React component and the d3 tooltip HTML formatter so both shot maps
 * render an identical breakdown. Returns null when the shot has no model xG (e.g.
 * blocked or empty-net shots).
 */
export function xgParts(shot: XGShot, minAbs = 0.005): Part[] | null {
  if (shot.xg == null) return null;
  const parts: Part[] = [];
  if (shot.base_rate != null) parts.push({ label: 'base', value: shot.base_rate });
  for (const b of BUCKETS) {
    const v = shot[b.key];
    if (v != null && Math.abs(v) >= minAbs) parts.push({ label: b.label, value: v });
  }
  return parts;
}

/** Plain-text one-liner, e.g. "0.21 xG: location +0.12, sequence +0.05". */
export function xgBreakdownText(shot: XGShot): string | null {
  if (shot.xg == null) return null;
  const contribs = (xgParts(shot) ?? [])
    .filter((p) => p.label !== 'base')
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .map((p) => `${p.label} ${fmtSigned(p.value)}`);
  return `${shot.xg.toFixed(2)} xG${contribs.length ? ': ' + contribs.join(', ') : ''}`;
}

/** HTML string for the d3-rendered ShotMap tooltips (which set innerHTML). */
export function xgBreakdownHTML(shot: XGShot): string {
  const text = xgBreakdownText(shot);
  if (!text) return '';
  return `<div class="xg-breakdown xg-breakdown--inline">${text}</div>`;
}

/**
 * Shared xG decomposition display (Phase 2.2). Shows the shot's xG and the ordered
 * contribution of each named bucket. Consumed by both shot maps (via the HTML helpers)
 * and any React tooltip.
 */
export default function XGBreakdown({ shot }: { shot: XGShot }) {
  if (shot.xg == null) return null;
  const parts = (xgParts(shot) ?? [])
    .filter((p) => p.label !== 'base')
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  return (
    <div className="xg-breakdown">
      <div className="xg-breakdown__total">{shot.xg.toFixed(2)} xG</div>
      <ul className="xg-breakdown__list">
        {parts.map((p) => (
          <li key={p.label} className="xg-breakdown__row">
            <span className="xg-breakdown__label">{p.label}</span>
            <span
              className={`xg-breakdown__value xg-breakdown__value--${p.value >= 0 ? 'pos' : 'neg'}`}
            >
              {fmtSigned(p.value)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
