'use client'

import { useMemo } from 'react'
import { buildNarratives, type NarrativeItem } from '../lib/runtimeNarrative'
import { useMultiMarketData } from './useMultiMarketData'
import type { LogEvent } from './useLogEvents'
import type { AgentRuntimeStatus } from '../data/types'
import type { Incident } from './useIncidents'
import type { DashboardKpis } from './useDashboardSummary'

interface NarrativeInputs {
  events: LogEvent[]
  agentStates: AgentRuntimeStatus[]
  incidents: Incident[]
  kpis: DashboardKpis | null
}

export type { NarrativeItem }

export function useRuntimeNarrative(inputs: NarrativeInputs): {
  narratives: NarrativeItem[]
  loading: boolean
} {
  const { data: multiMarket, loading: marketLoading } = useMultiMarketData()

  const { events, agentStates, incidents, kpis } = inputs

  const narratives = useMemo(
    () =>
      buildNarratives({
        events,
        agentStates,
        incidents,
        kpis,
        multiMarket,
      }),
    [events, agentStates, incidents, kpis, multiMarket],
  )

  return { narratives, loading: marketLoading && narratives.length === 0 }
}
