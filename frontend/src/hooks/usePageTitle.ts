import { useEffect } from 'react'
import { BRAND_NAME } from '../config/brand'

/** Sets document.title to "{t} · Rink Theory" (or just the brand when no title), resets on unmount. */
export function usePageTitle(t?: string) {
  useEffect(() => {
    document.title = t ? `${t} · ${BRAND_NAME}` : BRAND_NAME
    return () => { document.title = BRAND_NAME }
  }, [t])
}
