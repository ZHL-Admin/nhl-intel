import React, { useState, useRef, useEffect } from 'react';
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

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const next = e.key === 'ArrowRight'
      ? (index + 1) % tabs.length
      : (index - 1 + tabs.length) % tabs.length;
    tabRefs.current[next]?.focus();
    onChange(tabs[next].value);
  };

  return (
    <div className="tab-nav">
      <div className="tab-nav__tabs" role="tablist">
        {tabs.map((tab, index) => (
          <button
            key={tab.value}
            ref={el => tabRefs.current[index] = el}
            role="tab"
            aria-selected={activeTab === tab.value}
            tabIndex={activeTab === tab.value ? 0 : -1}
            className={`tab-nav__tab ${activeTab === tab.value ? 'tab-nav__tab--active' : ''}`}
            onClick={() => onChange(tab.value)}
            onKeyDown={(e) => handleKeyDown(e, index)}
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
