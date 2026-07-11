import { useEffect, useRef, useState } from 'react';
import './RinkTheoryLogo.css';

/**
 * Animated Rink Theory logo.
 *
 * Resting state is the plain mark (rink + center line + faceoff circle).
 * On hover / click / keyboard focus it plays one sequence:
 *   1. a puck drops onto center ice (the faceoff),
 *   2. after a beat it is fired toward the end boards,
 *   3. it exits the disc (clipped by the circle) and the mark
 *      returns to its resting state, ready to loop again.
 *
 * The animation will not re-trigger mid-sequence, and it is disabled
 * entirely for users with prefers-reduced-motion.
 */

const SEQUENCE_MS = 2100;

interface RinkTheoryLogoProps {
  /** Icon height/width in px. Default 40. */
  size?: number;
  /** Render the "Rink Theory" wordmark next to the icon. Default true. */
  withWordmark?: boolean;
  /**
   * Standalone (default): the mark is its own focusable, labelled control.
   * Set false when nesting inside another interactive element (e.g. a router
   * NavLink) so that element owns focus, the accessible name, and activation —
   * the mark then only carries the hover/click animation, avoiding a duplicate
   * tab stop and a nested-role conflict.
   */
  interactive?: boolean;
  className?: string;
}

export default function RinkTheoryLogo({
  size = 40,
  withWordmark = true,
  interactive = true,
  className = '',
}: RinkTheoryLogoProps) {
  const [playing, setPlaying] = useState(false);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) window.clearTimeout(timeoutRef.current);
    };
  }, []);

  const play = () => {
    if (playing) return;
    setPlaying(true);
    timeoutRef.current = window.setTimeout(() => {
      setPlaying(false);
      timeoutRef.current = null;
    }, SEQUENCE_MS);
  };

  return (
    <span
      className={`rt-logo ${playing ? 'rt-logo--play' : ''} ${className}`}
      onMouseEnter={play}
      onClick={play}
      onFocus={interactive ? play : undefined}
      onKeyDown={interactive ? (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          play();
        }
      } : undefined}
      role={interactive ? 'img' : undefined}
      aria-label={interactive ? 'Rink Theory' : undefined}
      aria-hidden={interactive ? undefined : true}
      tabIndex={interactive ? 0 : undefined}
    >
      <svg
        className="rt-logo__icon"
        width={size}
        height={size}
        viewBox="0 0 80 80"
        aria-hidden="true"
      >
        <defs>
          <clipPath id="rt-logo-clip">
            <circle cx="40" cy="40" r="40" />
          </clipPath>
        </defs>
        <circle className="rt-logo__disc" cx="40" cy="40" r="40" />
        <g clipPath="url(#rt-logo-clip)">
          <rect
            className="rt-logo__cut"
            x="15"
            y="23"
            width="50"
            height="34"
            rx="11"
            fill="none"
            strokeWidth="3.5"
          />
          <line
            className="rt-logo__cut"
            x1="40"
            y1="23"
            x2="40"
            y2="57"
            strokeWidth="3"
          />
          <path
            className="rt-logo__cut rt-logo__trail"
            d="M47 40 H78"
            fill="none"
            strokeWidth="3"
            strokeDasharray="5 4"
          />
          <circle
            className="rt-logo__cut rt-logo__ring"
            cx="40"
            cy="40"
            r="7"
            fill="none"
            strokeWidth="3"
          />
          <circle className="rt-logo__puck" cx="40" cy="40" r="4" />
        </g>
      </svg>
      {withWordmark && <span className="rt-logo__wordmark">Rink Theory</span>}
    </span>
  );
}
