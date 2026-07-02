import { useContext } from 'react';
import { PageCardContext } from './PageCard';
import './IdentityHeader.css';

interface IdentityHeaderProps {
  backLink?: { label: string; to: string };
  /** Float the back link in the top-left corner so it doesn't add to the header's height */
  absoluteBack?: boolean;
  leftContent: React.ReactNode;
  centerContent?: React.ReactNode;
  rightContent?: React.ReactNode;
  heroContent?: React.ReactNode;
  belowContent?: React.ReactNode;
  teamColors?: { away?: string; home?: string };
}

export default function IdentityHeader({
  leftContent,
  centerContent,
  rightContent,
  heroContent,
  belowContent
}: IdentityHeaderProps) {
  const insidePageCard = useContext(PageCardContext);

  return (
    <div className={`identity-header${insidePageCard ? ' identity-header--flat' : ''}`}>

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
