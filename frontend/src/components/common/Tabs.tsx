import './Tabs.css';

export interface TabOption {
  value: string;
  label: string;
  /** Small secondary tag inside the button (e.g. the method/unit under a concept-first label). */
  tag?: string;
  /** Render non-interactive (e.g. a lens that doesn't apply to the current scope). */
  disabled?: boolean;
}

interface TabsProps {
  options: TabOption[];
  value: string;
  onChange: (value: string) => void;
}

export default function Tabs({ options, value, onChange }: TabsProps) {
  return (
    <div className="tabs">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          disabled={option.disabled}
          aria-disabled={option.disabled}
          className={`tabs__option ${value === option.value ? 'tabs__option--selected' : ''}${option.disabled ? ' tabs__option--disabled' : ''}`}
          onClick={() => !option.disabled && onChange(option.value)}
        >
          <span className="tabs__option-label">{option.label}</span>
          {option.tag && <span className="tabs__option-tag">{option.tag}</span>}
        </button>
      ))}
    </div>
  );
}
