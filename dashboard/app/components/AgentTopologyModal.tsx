'use client'

import { useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import AgentTopology from './AgentTopology'
import type { AgentRuntimeStatus } from '../data/types'
import type { AgentRuntimeActivity } from '../hooks/useAgentRuntimeActivity'
import type { AgentLayer } from '../data/runtimeState'

interface Props {
  open: boolean
  onClose: () => void
  selectedId: string | null
  onSelectAgent: (id: string | null) => void
  agentStates: AgentRuntimeStatus[]
  agentActivity?: AgentRuntimeActivity[]
  activitySource?: 'real' | 'fallback'
  collapsedLayers?: Set<AgentLayer>
  highlightedAgentIds?: Set<string>
  filterAgentIds?: string[] | null
  onToggleLayer?: (layer: AgentLayer) => void
}

export default function AgentTopologyModal({
  open,
  onClose,
  selectedId,
  onSelectAgent,
  agentStates,
  agentActivity,
  activitySource,
  collapsedLayers = new Set(),
  highlightedAgentIds = new Set(),
  filterAgentIds = null,
  onToggleLayer,
}: Props) {
  // ESC key handler
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    },
    [onClose],
  )

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown)
      return () => document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open, handleKeyDown])

  // Prevent body scrolling when modal is open
  useEffect(() => {
    if (open) {
      const prev = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      return () => {
        document.body.style.overflow = prev
      }
    }
  }, [open])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="fixed inset-0 z-[9999] flex items-center justify-center"
        >
          {/* Backdrop with deep blue executive style */}
          <div
            className="absolute inset-0 bg-[#020617]/90 backdrop-blur-xl"
            onClick={onClose}
          />

          {/* Modal container */}
          <motion.div
            initial={{ scale: 0.92, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.92, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className="relative w-[96vw] h-[90vh] rounded-2xl border border-cyan-500/20 shadow-[0_0_60px_rgba(6,182,212,0.15),0_0_120px_rgba(6,182,212,0.05)] overflow-hidden bg-[#0b1a35]"
          >
            {/* Inner glow rings */}
            <div className="absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/[0.04] pointer-events-none" />
            <div className="absolute inset-2 rounded-xl ring-1 ring-inset ring-cyan-500/[0.06] pointer-events-none" />

            {/* Full-screen topology */}
            <AgentTopology
              selectedId={selectedId}
              onSelectAgent={onSelectAgent}
              agentStates={agentStates}
              agentActivity={agentActivity}
              activitySource={activitySource}
              collapsedLayers={collapsedLayers}
              highlightedAgentIds={highlightedAgentIds}
              filterAgentIds={filterAgentIds}
              onToggleLayer={onToggleLayer}
              expanded
              onRequestClose={onClose}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}