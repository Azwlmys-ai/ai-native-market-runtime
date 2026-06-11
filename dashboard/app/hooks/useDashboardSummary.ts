'use client'

import { useState, useEffect, useRef } from 'react'

export interface DashboardKpis {
  totalSignals: number
  approvedSignals: number
  rejectedSignals: number
  timeoutSignals: number
  activeAgents: number
  errorCount: number
  warningCount: number
  healthScore: number
  pnl: number
  reconnects: number
  runtimeStatus: 'ONLINE' | 'DEGRADED' | 'OFFLINE'
  regime: string
}

interface DashboardSummaryData {
  source: 'real' | 'mixed' | 'fallback'
  updatedAt: string
  kpis: DashboardKpis
}

// Legacy data path: page.tsx now prefers KPI values derived from useVisualizationState.
export function useDashboardSummary(): {
  kpis: DashboardKpis | null
  source: 'real' | 'mixed' | 'fallback'
  loading: boolean
  error: boolean
} {
  const [data, setData] = useState<DashboardSummaryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true

    async function fetchAndSet() {
      try {
        const res = await fetch('/api/dashboard-summary', { cache: 'no-store' })
        if (!res.ok) throw new Error('HTTP ' + res.status)
        const json: DashboardSummaryData = await res.json()
        if (mountedRef.current) {
          setData(json)
          setError(false)
        }
      } catch {
        if (mountedRef.current) {
          setError(true)
        }
      } finally {
        if (mountedRef.current) {
          setLoading(false)
        }
      }
    }

    // Initial fetch
    fetchAndSet()

    // Poll every 5 seconds
    const interval = setInterval(fetchAndSet, 5000)

    return () => {
      mountedRef.current = false
      clearInterval(interval)
    }
  }, [])

  return {
    kpis: data?.kpis ?? null,
    source: data?.source ?? 'fallback',
    loading,
    error,
  }
}
