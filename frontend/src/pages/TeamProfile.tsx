import React from 'react'
import { useParams } from 'react-router-dom'
import { PageLayout } from '../components/common'

function TeamProfile() {
  const { teamId } = useParams<{ teamId: string }>()

  return (
    <PageLayout>
      <h1>Team Profile: {teamId}</h1>
    </PageLayout>
  )
}

export default TeamProfile
