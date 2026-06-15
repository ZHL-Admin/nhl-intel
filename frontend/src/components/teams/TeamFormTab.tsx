/**
 * TeamProfile "Form" tab (Phase 3.3): Streak Doctor card with a last-N window selector.
 */
import { useState, useEffect } from 'react'
import { StreakDoctorCard, Tabs, SkeletonLoader } from '../common'
import { getTeamStreak } from '../../api/teams'
import { StreakCard } from '../../api/types'

const WINDOWS = [5, 10, 20]

export default function TeamFormTab({ teamId }: { teamId: number }) {
  const [windowGames, setWindowGames] = useState(10)
  const [card, setCard] = useState<StreakCard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setCard(null)
    setError(null)
    getTeamStreak(teamId, windowGames)
      .then((c) => active && setCard(c))
      .catch(() => active && setError('Could not load form.'))
    return () => { active = false }
  }, [teamId, windowGames])

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: 'var(--space-5, 20px) var(--space-6, 24px)', display: 'flex', flexDirection: 'column', gap: 'var(--space-4, 16px)' }}>
      <Tabs
        options={WINDOWS.map((w) => ({ value: String(w), label: `Last ${w}` }))}
        value={String(windowGames)}
        onChange={(v) => setWindowGames(parseInt(v))}
      />
      {error && <p style={{ color: 'var(--color-text-secondary, #888)' }}>{error}</p>}
      {!card && !error && <SkeletonLoader />}
      {card && <StreakDoctorCard card={card} />}
    </div>
  )
}
