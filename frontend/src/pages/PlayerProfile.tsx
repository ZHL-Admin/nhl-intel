import React from 'react'
import { useParams } from 'react-router-dom'
import { PageLayout } from '../components/common'

function PlayerProfile() {
  const { playerId } = useParams<{ playerId: string }>()

  return (
    <PageLayout>
      <h1>Player Profile: {playerId}</h1>
    </PageLayout>
  )
}

export default PlayerProfile
