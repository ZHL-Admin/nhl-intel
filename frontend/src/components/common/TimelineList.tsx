import './TimelineList.css';

export interface TimelineItem {
  id: string;
  leftContent: React.ReactNode;
  rightContent: React.ReactNode;
  accentColor?: string;
}

export interface TimelineGroup {
  label: string;
  items: TimelineItem[];
}

interface TimelineListProps {
  groups: TimelineGroup[];
  emptyMessage?: string;
}

export default function TimelineList({ groups, emptyMessage }: TimelineListProps) {
  const hasItems = groups.some(group => group.items.length > 0);

  if (!hasItems) {
    if (emptyMessage) {
      return <div className="timeline-list__empty">{emptyMessage}</div>;
    }
    return null;
  }

  return (
    <div className="timeline-list">
      {groups.map((group, groupIndex) => {
        if (group.items.length === 0) return null;

        return (
          <div key={groupIndex} className="timeline-list__group">
            <h3 className="timeline-list__group-title">{group.label}</h3>

            <div className="timeline-list__items">
              {group.items.map(item => (
                <div
                  key={item.id}
                  className="timeline-item"
                  style={{ borderLeftColor: item.accentColor || 'var(--color-border)' }}
                >
                  <div className="timeline-item__left">{item.leftContent}</div>
                  <div className="timeline-item__right">{item.rightContent}</div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
