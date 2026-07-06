import { useState, createContext, useContext } from 'react';
import { Maximize2, Minimize2 } from 'lucide-react';
import { PageCardContext } from './PageCard';
import './ChartPanel.css';

interface ChartPanelProps {
  sectionNumber?: string;
  title: string;
  subtitle?: string;
  expandable?: boolean;
  defaultExpanded?: boolean;
  /** Size the content to its natural height (SVG maps, tables) instead of a fixed chart height. */
  autoHeight?: boolean;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

interface ChartPanelContextValue {
  height: number;
}

const ChartPanelContext = createContext<ChartPanelContextValue>({ height: 280 });

export function useChartPanelHeight(): number {
  const context = useContext(ChartPanelContext);
  return context.height;
}

export default function ChartPanel({
  sectionNumber,
  title,
  subtitle,
  expandable = true,
  defaultExpanded = false,
  autoHeight = false,
  children,
  footer
}: ChartPanelProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const height = isExpanded ? 560 : 280;
  const insidePageCard = useContext(PageCardContext);

  return (
    <div className={`chart-panel${insidePageCard ? ' chart-panel--flat' : ''}`}>
      <div className="chart-panel-header">
        <div className="chart-panel-header-text">
          {sectionNumber && (
            <div className="chart-panel-section-number">{sectionNumber}</div>
          )}
          <h3 className="chart-panel-title">{title}</h3>
          {subtitle && (
            <div className="chart-panel-subtitle">{subtitle}</div>
          )}
        </div>
        {/* autoHeight panels (SVG maps, tables) size to content — no fixed height, no expand toggle. */}
        {expandable && !autoHeight && (
          <button
            className="chart-panel-expand-button"
            onClick={() => setIsExpanded(!isExpanded)}
            aria-label={isExpanded ? 'Collapse chart' : 'Expand chart'}
          >
            {isExpanded ? (
              <Minimize2 size={16} />
            ) : (
              <Maximize2 size={16} />
            )}
          </button>
        )}
      </div>

      <div className="chart-panel-divider" />

      <div
        className="chart-panel-content"
        style={autoHeight ? undefined : { height: `${height}px` }}
      >
        <ChartPanelContext.Provider value={{ height }}>
          {children}
        </ChartPanelContext.Provider>
      </div>

      {footer && (
        <>
          <div className="chart-panel-divider" />
          <div className="chart-panel-footer">
            {footer}
          </div>
        </>
      )}
    </div>
  );
}
