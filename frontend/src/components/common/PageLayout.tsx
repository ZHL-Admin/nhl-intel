import React from 'react'
import NavBar from './NavBar'
import './PageLayout.css'

interface PageLayoutProps {
  children: React.ReactNode
}

function PageLayout({ children }: PageLayoutProps) {
  return (
    <>
      <NavBar />
      <main className="page-layout">
        <div className="page-layout__container">
          {children}
        </div>
      </main>
    </>
  )
}

export default PageLayout
