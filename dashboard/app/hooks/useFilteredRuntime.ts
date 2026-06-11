'use client'

import { useState, useMemo, useCallback } from 'react'
import { useLogEvents, type LogEvent, type LogLevel } from './useLogEvents'

// ═══════════════════════════════════════════════════════════
// useFilteredRuntime — legacy runtime log filter pipeline retained for existing panels.
// ═══════════════════════════════════════════════════════════

export type FilterState = {
  levelFilter: LogLevel | 'ALL'
  agentFilter: string | null
  categoryFilters: string[]
  searchQuery: string
  runtimeViewMode: 'ops' | 'executive'
}

const DEFAULT_FILTER_STATE: FilterState = {
  levelFilter: 'ALL',
  agentFilter: null,
  categoryFilters: [],
  searchQuery: '',
  runtimeViewMode: 'ops',
}

export function useFilteredRuntime(initial?: Partial<FilterState>) {
  const { events: allEvents, source } = useLogEvents()

  // ── Filter State ─────────────────────────────────────
  const [levelFilter, setLevelFilter] = useState<LogLevel | 'ALL'>(
    initial?.levelFilter ?? DEFAULT_FILTER_STATE.levelFilter,
  )
  const [agentFilter, setAgentFilter] = useState<string | null>(
    initial?.agentFilter ?? DEFAULT_FILTER_STATE.agentFilter,
  )
  const [categoryFilters, setCategoryFilters] = useState<string[]>(
    initial?.categoryFilters ?? DEFAULT_FILTER_STATE.categoryFilters,
  )
  const [searchQuery, setSearchQuery] = useState(
    initial?.searchQuery ?? DEFAULT_FILTER_STATE.searchQuery,
  )
  const [runtimeViewMode, setRuntimeViewMode] = useState<'ops' | 'executive'>(
    initial?.runtimeViewMode ?? DEFAULT_FILTER_STATE.runtimeViewMode,
  )

  // ── Single filtered pipeline ─────────────────────────
  const filteredEvents: LogEvent[] = useMemo(() => {
    let events = allEvents

    // Executive view: auto-suppress INFO, aggregate
    if (runtimeViewMode === 'executive') {
      // Suppress INFO events (keep only actionable ones)
      events = events.filter((e) => e.level !== 'INFO')
      // Deduplicate same title+agent within last 60s
      const seen = new Set<string>()
      events = events.filter((e) => {
        const key = `${e.title}|${e.agent}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
    }

    // Level filter
    if (levelFilter !== 'ALL') {
      events = events.filter((e) => e.level === levelFilter)
    }

    // Agent filter
    if (agentFilter) {
      events = events.filter(
        (e) => e.agent.toLowerCase() === agentFilter.toLowerCase(),
      )
    }

    // Category multi-select
    if (categoryFilters.length > 0) {
      events = events.filter((e) => categoryFilters.includes(e.category))
    }

    // Search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      events = events.filter(
        (e) =>
          e.title.toLowerCase().includes(q) ||
          e.detail.toLowerCase().includes(q) ||
          e.tags.some((t) => t.toLowerCase().includes(q)) ||
          e.agent.toLowerCase().includes(q),
      )
    }

    return events.slice(0, 20)
  }, [
    allEvents,
    runtimeViewMode,
    levelFilter,
    agentFilter,
    categoryFilters,
    searchQuery,
  ])

  // ── Stable filter setters ────────────────────────────
  const setAgentFilterAndSync = useCallback((agentId: string | null) => {
    setAgentFilter(agentId)
  }, [])

  const filterState: FilterState = useMemo(
    () => ({
      levelFilter,
      agentFilter,
      categoryFilters,
      searchQuery,
      runtimeViewMode,
    }),
    [levelFilter, agentFilter, categoryFilters, searchQuery, runtimeViewMode],
  )

  const activeFilterCount = useMemo(() => {
    let count = 0
    if (levelFilter !== 'ALL') count++
    if (agentFilter) count++
    count += categoryFilters.length
    if (searchQuery.trim()) count++
    return count
  }, [levelFilter, agentFilter, categoryFilters, searchQuery])

  return {
    // Data
    allEvents,
    filteredEvents,
    source,
    filterState,
    activeFilterCount,

    // Setters
    setLevelFilter,
    setAgentFilter: setAgentFilterAndSync,
    setCategoryFilters,
    setSearchQuery,
    setRuntimeViewMode,
  }
}
