'use client'

import { useState, useEffect, useCallback, useRef } from 'react'

// ── Section Registry ──────────────────────────────────────

export interface DemoSection {
  id: string
  label: string
  duration: number
}

export const DEMO_SECTIONS: DemoSection[] = [
  { id: 'demo-kpi', label: 'KPI Overview', duration: 8000 },
  { id: 'demo-narrative', label: 'Executive Narrative', duration: 10000 },
  { id: 'demo-dryrun', label: 'Dry-Run Validation', duration: 8000 },
  { id: 'demo-confidence', label: 'Runtime Confidence', duration: 7000 },
  { id: 'demo-topology', label: 'Agent Topology', duration: 10000 },
  { id: 'demo-scenarios', label: 'Enterprise Scenarios', duration: 7000 },
  { id: 'demo-roi', label: 'Executive ROI', duration: 8000 },
  { id: 'demo-keyevents', label: 'Key Runtime Events', duration: 7000 },
  { id: 'demo-feed', label: 'Live Event Feed', duration: 7000 },
]

// ── Types ─────────────────────────────────────────────────

export type AutoDemoStatus = 'OFF' | 'RUNNING' | 'PAUSED'

export interface AutoDemoState {
  status: AutoDemoStatus
  currentLabel: string
  currentSectionId: string | null
  toggleDemo: () => void
  stopDemo: () => void
}

// ── Hook ──────────────────────────────────────────────────

export function useAutoDemo(
  viewMode: 'runtime' | 'executive',
  setViewMode: (v: 'runtime' | 'executive') => void,
): AutoDemoState {
  const [status, setStatus] = useState<AutoDemoStatus>('OFF')
  const [currentIndex, setCurrentIndex] = useState(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const prevViewModeRef = useRef<'runtime' | 'executive'>('runtime')

  const currentSection = DEMO_SECTIONS[currentIndex] ?? null
  const currentSectionId = currentSection?.id ?? null
  const currentLabel = currentSection?.label ?? ''

  // ── Scroll helper ─────────────────────────────────────
  const scrollToSection = useCallback((sectionId: string) => {
    const el = document.getElementById(sectionId)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })

    // When the live feed section is active, scroll its inner
    // overflow container to the bottom so the newest events show.
    if (sectionId === 'demo-feed') {
      const inner = el.querySelector('.overflow-y-auto') as HTMLElement | null
      if (inner) {
        inner.scrollTop = inner.scrollHeight
      }
    }
  }, [])

  // ── Controls ──────────────────────────────────────────
  const stopDemo = useCallback(() => {
    setStatus('OFF')
    setCurrentIndex(0)
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    setViewMode(prevViewModeRef.current)
  }, [setViewMode])

  const toggleDemo = useCallback(() => {
    if (status === 'RUNNING') {
      // Pause
      setStatus('PAUSED')
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    } else if (status === 'PAUSED') {
      // Resume
      setStatus('RUNNING')
    } else {
      // Start: switch to Executive and begin
      prevViewModeRef.current = viewMode
      setViewMode('executive')
      setStatus('RUNNING')
    }
  }, [status, viewMode, setViewMode])

  // ── Main demo cycle ───────────────────────────────────
  useEffect(() => {
    if (status !== 'RUNNING') return

    if (!currentSection) return

    // Brief defer so DOM is painted before scrolling
    const scrollTimer = setTimeout(() => {
      scrollToSection(currentSection.id)
    }, 80)

    // Schedule next section tick
    timerRef.current = setTimeout(() => {
      setCurrentIndex((prev) => (prev + 1) % DEMO_SECTIONS.length)
    }, currentSection.duration)

    return () => {
      clearTimeout(scrollTimer)
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [status, currentIndex, currentSection, scrollToSection])

  // ── Cleanup on unmount ────────────────────────────────
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  return {
    status,
    currentLabel,
    currentSectionId,
    toggleDemo,
    stopDemo,
  }
}