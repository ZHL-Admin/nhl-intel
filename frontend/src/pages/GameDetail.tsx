import React from 'react'
import { useParams } from 'react-router-dom'
import { PageLayout } from '../components/common'

function GameDetail() {
  const { gameId } = useParams<{ gameId: string }>()

  return (
    <PageLayout>
      <h1>Game Detail: {gameId}</h1>
    </PageLayout>
  )
}

export default GameDetail
