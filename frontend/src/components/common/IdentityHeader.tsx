import { useNavigate } from 'react-router-dom';
import './IdentityHeader.css';

interface IdentityHeaderProps {
  backLink?: { label: string; to: string };
  leftContent: React.ReactNode;
  centerContent?: React.ReactNode;
  rightContent?: React.ReactNode;
  heroContent?: React.ReactNode;
  belowContent?: React.ReactNode;
  teamColors?: { away?: string; home?: string };
}

export default function IdentityHeader({
  backLink,
  leftContent,
  centerContent,
  rightContent,
  heroContent,
  belowContent,
  teamColors
}: IdentityHeaderProps) {
  const navigate = useNavigate();

  const getBackgroundStyle = () => {
    if (!teamColors) return {};

    if (teamColors.away && teamColors.home) {
      return {
        background: `linear-gradient(to right, color-mix(in srgb, ${teamColors.away} 10%, var(--color-bg-surface)) 0%, var(--color-bg-surface) 50%, color-mix(in srgb, ${teamColors.home} 10%, var(--color-bg-surface)) 100%)`
      };
    }

    const singleColor = teamColors.away || teamColors.home;
    if (singleColor) {
      return {
        background: `color-mix(in srgb, ${singleColor} 10%, var(--color-bg-surface))`
      };
    }

    return {};
  };

  return (
    <div className="identity-header" style={getBackgroundStyle()}>
      {backLink && (
        <button
          className="identity-header__back"
          onClick={() => navigate(backLink.to)}
        >
          <span>{backLink.label}</span>
        </button>
      )}

      <div className="identity-header__main">
        <div className="identity-header__left">{leftContent}</div>
        {centerContent && <div className="identity-header__center">{centerContent}</div>}
        {rightContent && <div className="identity-header__right">{rightContent}</div>}
      </div>

      {heroContent && <div className="identity-header__hero">{heroContent}</div>}
      {belowContent && <div className="identity-header__below">{belowContent}</div>}
    </div>
  );
}
