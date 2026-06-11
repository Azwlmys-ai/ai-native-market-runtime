'use client'

import { createContext, useContext, useState, useCallback } from 'react'

export type ViewMode = 'executive' | 'engineer'

interface ExecutiveModeContextValue {
  mode: ViewMode
  setMode: (mode: ViewMode) => void
  toggleMode: () => void
  /** When true, the Incident Command Center is open fullscreen */
  incidentCommandOpen: boolean
  /** ID of the incident to show in Command Center */
  commandIncidentId: string | null
  openIncidentCommand: (incidentId: string) => void
  closeIncidentCommand: () => void
}

const ExecutiveModeContext = createContext<ExecutiveModeContextValue | null>(null)

export function useExecutiveMode(): ExecutiveModeContextValue {
  const ctx = useContext(ExecutiveModeContext)
  if (!ctx) throw new Error('useExecutiveMode must be used within ExecutiveModeProvider')
  return ctx
}

export function ExecutiveModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<ViewMode>('engineer')
  const [incidentCommandOpen, setIncidentCommandOpen] = useState(false)
  const [commandIncidentId, setCommandIncidentId] = useState<string | null>(null)

  const toggleMode = useCallback(() => {
    setMode((prev) => (prev === 'executive' ? 'engineer' : 'executive'))
  }, [])

  const openIncidentCommand = useCallback((incidentId: string) => {
    setCommandIncidentId(incidentId)
    setIncidentCommandOpen(true)
  }, [])

  const closeIncidentCommand = useCallback(() => {
    setIncidentCommandOpen(false)
    setCommandIncidentId(null)
  }, [])

  return (
    <ExecutiveModeContext.Provider
      value={{
        mode,
        setMode,
        toggleMode,
        incidentCommandOpen,
        commandIncidentId,
        openIncidentCommand,
        closeIncidentCommand,
      }}
    >
      {children}
    </ExecutiveModeContext.Provider>
  )
}
