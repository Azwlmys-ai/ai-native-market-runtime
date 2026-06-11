'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

export interface VisualizationState {
  timestamp?: string
  signals_summary?: {
    total?: number
    by_source?: Record<string, number>
    by_direction?: Record<string, number>
    average_confidence?: number | null
    average_expected_value?: number | null
    latest_signal_timestamp?: string | null
    top_markets?: Array<{
      market_id?: string | number | null
      market_name?: string | null
      direction?: string | null
      expected_value?: number | null
      confidence?: number | null
    }>
  }
  signal_details?: Array<{
    market_id?: string | number | null
    market_name?: string | null
    market_slug?: string | null
    direction?: string | null
    price?: number | null
    position_size?: number | null
    expected_value?: number | null
    confidence?: number | null
    source?: string | null
    generated_at?: string | null
    reason?: string | null
    risk_notes?: string | null
  }>
  review_summary?: {
    timestamp?: string
    total?: number
    real_signals?: number
    paper_signals?: number
    approved?: number
    rejected?: number
    approved_real?: number
    approved_paper?: number
    rejected_real?: number
    rejected_paper?: number
  }
  review_details?: {
    approved_signals?: Array<{
      market_id?: string | number | null
      market_name?: string | null
      direction?: string | null
      expected_value?: number | null
      confidence?: number | null
      decision?: string | null
      review?: string | null
      reason?: string | null
      source?: string | null
    }>
    rejected_signals?: Array<{
      market_id?: string | number | null
      market_name?: string | null
      direction?: string | null
      expected_value?: number | null
      confidence?: number | null
      decision?: string | null
      review?: string | null
      reason?: string | null
      source?: string | null
    }>
  }
  execution_summary?: {
    timestamp?: string
    total?: number
    success?: number
    dry_run?: number
    simulated?: number
    failed?: number
    status_counts?: Record<string, number>
    latest_execution_timestamp?: string | null
  }
  execution_details?: Array<{
    status?: string | null
    timestamp?: string | null
    market_id?: string | number | null
    market_name?: string | null
    direction?: string | null
    expected_value?: number | null
    confidence?: number | null
    source?: string | null
  }>
  agent_log_summary?: {
    files_scanned?: number
    files?: Array<{
      file?: string
      size_bytes?: number
      modified_at?: string
      recent_line_count?: number
      level_counts?: Record<string, number>
      recent_lines?: string[]
    }>
  }
  recent_runtime_events?: Array<{
    file?: string
    message?: string
  }>
}

interface VisualizationStateResponse {
  ok: boolean
  source: 'visualization_state'
  updatedAt: string | null
  state: VisualizationState
}

const POLL_INTERVAL_MS = 4000

export function useVisualizationState() {
  const [state, setState] = useState<VisualizationState | null>(null)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const lastGoodRef = useRef<VisualizationState | null>(null)

  const fetchState = useCallback(async () => {
    try {
      const res = await fetch('/api/visualization-state', { cache: 'no-store' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: VisualizationStateResponse = await res.json()
      if (!data.ok) throw new Error('visualization state unavailable')

      lastGoodRef.current = data.state
      setState(data.state)
      setUpdatedAt(data.updatedAt)
      setError(null)
    } catch (err) {
      setState(lastGoodRef.current)
      setError(err instanceof Error ? err.message : 'failed to fetch visualization state')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchState()
    const interval = setInterval(fetchState, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchState])

  return {
    state,
    updatedAt,
    source: 'visualization_state' as const,
    loading,
    error,
    refetch: fetchState,
  }
}
