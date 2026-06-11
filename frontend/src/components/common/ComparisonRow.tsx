import { Info } from 'lucide-react';
import Tooltip from './Tooltip';
import './ComparisonRow.css';

interface ComparisonRowProps {
  label: string;
  awayValue: string | number;
  homeValue: string | number;
  awayColor: string;
  homeColor: string;
  showBar?: boolean;
  awayRaw?: number;
  homeRaw?: number;
  tooltip?: string;
}

export default function ComparisonRow({
  label,
  awayValue,
  homeValue,
  awayColor,
  homeColor,
  showBar = true,
  awayRaw,
  homeRaw,
  tooltip
}: ComparisonRowProps) {
  const total = (awayRaw ?? 0) + (homeRaw ?? 0);
  const awayPercent = total > 0 ? ((awayRaw ?? 0) / total) * 100 : 50;

  return (
    <div className="comparison-row">
      <div className="comparison-row__away-value mono">{awayValue}</div>

      <div className="comparison-row__center">
        <div className="comparison-row__label">
          {label}
          {tooltip && (
            <Tooltip content={tooltip}>
              <Info size={12} className="comparison-row__info-icon" />
            </Tooltip>
          )}
        </div>

        {showBar && awayRaw !== undefined && homeRaw !== undefined && (
          <div className="comparison-row__bar">
            <div
              className="comparison-row__bar-segment comparison-row__bar-segment--away"
              style={{
                width: `${awayPercent}%`,
                background: awayColor
              }}
            />
            <div
              className="comparison-row__bar-segment comparison-row__bar-segment--home"
              style={{
                width: `${100 - awayPercent}%`,
                background: homeColor
              }}
            />
          </div>
        )}
      </div>

      <div className="comparison-row__home-value mono">{homeValue}</div>
    </div>
  );
}
