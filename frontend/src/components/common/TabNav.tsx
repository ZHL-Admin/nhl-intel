import { useState, useRef, useEffect } from 'react';
import './TabNav.css';

interface TabNavProps {
  tabs: { value: string; label: string }[];
  activeTab: string;
  onChange: (value: string) => void;
}

export default function TabNav({ tabs, activeTab, onChange }: TabNavProps) {
  const [indicatorStyle, setIndicatorStyle] = useState({ left: 0, width: 0 });
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    const activeIndex = tabs.findIndex(tab => tab.value === activeTab);
    const activeRef = tabRefs.current[activeIndex];

    if (activeRef) {
      setIndicatorStyle({
        left: activeRef.offsetLeft,
        width: activeRef.offsetWidth
      });
    }
  }, [activeTab, tabs]);

  return (
    <div className="tab-nav">
      <div className="tab-nav__tabs">
        {tabs.map((tab, index) => (
          <button
            key={tab.value}
            ref={el => tabRefs.current[index] = el}
            className={`tab-nav__tab ${activeTab === tab.value ? 'tab-nav__tab--active' : ''}`}
            onClick={() => onChange(tab.value)}
          >
            {tab.label}
          </button>
        ))}
        <div
          className="tab-nav__indicator"
          style={{
            transform: `translateX(${indicatorStyle.left}px)`,
            width: `${indicatorStyle.width}px`
          }}
        />
      </div>
    </div>
  );
}
