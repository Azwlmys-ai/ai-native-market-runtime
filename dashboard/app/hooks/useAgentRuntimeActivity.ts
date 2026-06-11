'use client'

import { useState, useEffect } from 'react'

// ── Types (mirror API response) ────────────────────────

export interface AgentRuntimeActivity {
  id: string
  name: string
  status: 'idle' | 'running' | 'warning' | 'error'
  currentTask: string
  lastActiveAt: string | null
  signalsProcessed: number
  successCount: number
  failureCount: number
  avgLatencyMs: number
  recentEvent: string | null
  throughput: number
}

interface AgentsRuntimeResponse {
  source: 'real' | 'fallback'
  updatedAt: string
  agents: AgentRuntimeActivity[]
}

// ── Hook ───────────────────────────────────────────────

interface UseAgentRuntimeActivityResult {
  agents: AgentRuntimeActivity[]
  source: 'real' | 'fallback'
  loading: boolean
  error: string | null
  updatedAt: string | null
}

// Legacy data path: retained for AgentTopology activity overlays.
export function useAgentRuntimeActivity(): UseAgentRuntimeActivityResult {
  const [agents, setAgents] = useState<AgentRuntimeActivity[]>([])
  const [source, setSource] = useState<'real' | 'fallback'>('fallback')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    let interval: ReturnType<typeof setInterval> | null = null

    async function run() {
      try {
        const res = await fetch('/api/agents-runtime')
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data: AgentsRuntimeResponse = await res.json()

        if (!active) return

        setAgents(data.agents)
        setSource(data.source)
        setUpdatedAt(data.updatedAt)
        setError(null)
      } catch (e) {
        if (!active) return
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    // Immediate first fetch
    run()

    // Poll every 5 seconds
    interval = setInterval(run, 5000)

    return () => {
      active = false
      if (interval) clearInterval(interval)
    }
  }, [])

  return { agents, source, loading, error, updatedAt }
}
