import { useEffect, type RefObject } from 'react'

export type LandingMotionMode = 'observe' | 'static'

export function resolveLandingMotionMode(
  prefersReducedMotion: boolean,
  supportsIntersectionObserver: boolean,
): LandingMotionMode {
  return !prefersReducedMotion && supportsIntersectionObserver ? 'observe' : 'static'
}

export function getRevealDelay(index: number): number {
  return Math.min(280, Math.max(0, Math.trunc(index)) * 70)
}

export function useLandingReveal(rootRef: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const root = rootRef.current
    if (!root) return undefined

    const revealItems = Array.from(root.querySelectorAll<HTMLElement>('[data-reveal]'))
    const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const mode = resolveLandingMotionMode(prefersReducedMotion, 'IntersectionObserver' in window)
    root.dataset.motion = mode

    revealItems.forEach((item, index) => {
      const requestedIndex = Number(item.dataset.revealIndex ?? index)
      item.style.setProperty('--reveal-delay', `${getRevealDelay(requestedIndex)}ms`)
      if (mode === 'static') item.dataset.revealState = 'visible'
    })

    if (mode === 'static') return undefined

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return
          const element = entry.target as HTMLElement
          element.dataset.revealState = 'visible'
          observer.unobserve(element)
        })
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.12 },
    )

    revealItems.forEach((item) => observer.observe(item))
    return () => observer.disconnect()
  }, [rootRef])
}
