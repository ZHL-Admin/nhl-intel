import React from 'react'
import { useParams } from 'react-router-dom'
import { PageLayout, SkeletonLoader } from '../components/common'

function PlayerProfile() {
  const { playerId } = useParams<{ playerId: string }>()

  return (
    <PageLayout>
      <div style={{ textAlign: 'center', padding: 'var(--space-12) 0' }}>
        <h2 style={{
          fontSize: 'var(--text-xl)',
          color: 'var(--color-text-secondary)',
          marginBottom: 'var(--space-6)'
        }}>
          Player Profile Coming Soon
        </h2>
        <div style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-4)' }}>
            <SkeletonLoader height={100} />
            <SkeletonLoader height={100} />
            <SkeletonLoader height={100} />
            <SkeletonLoader height={100} />
          </div>
          <SkeletonLoader height={300} />
          <SkeletonLoader height={250} />
        </div>
        <p style={{
          fontSize: 'var(--text-sm)',
          color: 'var(--color-text-muted)',
          marginTop: 'var(--space-6)'
        }}>
          Player ID: {playerId}
        </p>
      </div>
    </PageLayout>
  )
}

export default PlayerProfile
