import React from 'react'
import { useParams } from 'react-router-dom'
import { PageLayout, SkeletonLoader } from '../components/common'

function GameDetail() {
  const { gameId } = useParams<{ gameId: string }>()

  return (
    <PageLayout>
      <div style={{ textAlign: 'center', padding: 'var(--space-12) 0' }}>
        <h2 style={{
          fontSize: 'var(--text-xl)',
          color: 'var(--color-text-secondary)',
          marginBottom: 'var(--space-6)'
        }}>
          Game Detail Coming Soon
        </h2>
        <div style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <SkeletonLoader height={200} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
            <SkeletonLoader height={120} />
            <SkeletonLoader height={120} />
          </div>
          <SkeletonLoader height={300} />
        </div>
        <p style={{
          fontSize: 'var(--text-sm)',
          color: 'var(--color-text-muted)',
          marginTop: 'var(--space-6)'
        }}>
          Game ID: {gameId}
        </p>
      </div>
    </PageLayout>
  )
}

export default GameDetail
