import './Tabs.css';

interface TabsProps {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}

export default function Tabs({ options, value, onChange }: TabsProps) {
  return (
    <div className="tabs">
      {options.map((option) => (
        <button
          key={option.value}
          className={`tabs__option ${value === option.value ? 'tabs__option--selected' : ''}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
