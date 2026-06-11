'use client'

import { useState, useEffect, useCallback } from 'react'

// ── Types ────────────────────────────────────────────────

export type LogLevel = 'INFO' | 'SUCCESS' | 'WARN' | 'ERROR'

export interface LogEvent {
  id: string
  timestamp: string
  level: LogLevel
  category: string
  title: string
  detail: string
  agent: string
  agentId: string | null
  tags: string[]
}

interface ApiResponse {
  source: 'real' | 'fallback'
  updatedAt: string
  events: LogEvent[]
}

// ── Hook ─────────────────────────────────────────────────

const POLL_INTERVAL_MS = 5000

// Legacy data path: retained for existing runtime log panels and filters.
export function useLogEvents() {
  const [events, setEvents] = useState<LogEvent[]>([])
  const [source, setSource] = useState<'real' | 'fallback'>('fallback')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchEvents = useCallback(async () => {
    try {
      const res = await fetch('/api/runtime-logs')
      if (!res.ok) {
        setSource('fallback')
        return
      }
      const data: ApiResponse = await res.json()
      setSource(data.source)
      if (data.events && data.events.length > 0) {
        setEvents(data.events)
      }
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch logs')
      setSource('fallback')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => fetchEvents(), 0)
    const interval = setInterval(fetchEvents, POLL_INTERVAL_MS)
    return () => {
      clearTimeout(timer)
      clearInterval(interval)
    }
  }, [fetchEvents])

  return { events, source, loading, error, refetch: fetchEvents }
}
