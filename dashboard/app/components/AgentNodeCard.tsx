'use client'

import { motion } from 'framer-motion'
import { AgentData, AgentStatus } from '../data/mockAgents'

const statusConfig: Record<AgentStatus, { color: string; bg: string; border: string; icon: string; label: string }> = {
  running:   { color: 'text-blue-400',   bg: 'bg-blue-500/10',   border: 'border-blue-500/50',   icon: '⟳', label: 'RUNNING'   },
  completed: { color: 'text-emerald-400',bg: 'bg-emerald-500/10',border: 'border-emerald-500/50',icon: '✓', label: 'DONE'      },
  failed:    { color: 'text-red-400',    bg: 'bg-red-500/10',    border: 'border-red-500/50',    icon: '✗', label: 'FAILED'    },
  timeout:   { color: 'text-amber-400',  bg: 'bg-amber-500/10',  border: 'border-amber-500/50',  icon: '⚠', label: 'TIMEOUT'   },
  waiting:   { color: 'text-slate-400',  bg: 'bg-slate-500/10',  border: 'border-slate-500/40',  icon: '○', label: 'WAITING'   },
}

interface AgentNodeCardProps {
  agent: AgentData
  onClick: (agent: AgentData) => void
  selected?: boolean
}

export default function AgentNodeCard({ agent, onClick, selected }: AgentNodeCardProps) {
  const s = statusConfig[agent.status]
  return (
    <motion.div
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      onClick={() => onClick(agent)}
      className={`cursor-pointer rounded-lg border p-3 ${s.bg} ${s.border} ${selected ? 'ring-2 ring-cyan-400' : ''} transition-all`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className={`text-xs font-bold font-mono ${s.color}`}>{s.icon} {s.label}</span>
        <span className="text-xs text-slate-500 font-mono">{(agent.latencyMs / 1000).toFixed(1)}s</span>
      </div>
      <p className="text-sm font-semibold text-white truncate">{agent.name}</p>
      <p className="text-xs text-slate-400 mt-0.5 truncate">{agent.role.split('—')[0].trim()}</p>
      <div className="flex gap-2 mt-2 text-xs text-slate-500 font-mono">
        <span>🔢 {agent.llmCalls} calls</span>
        <span>·</span>
        <span>{agent.tokensUsed > 0 ? `${agent.tokensUsed}tok` : '—'}</span>
        {agent.cacheHit && <span className="text-cyan-500">· cache✓</span>}
      </div>
    </motion.div>
  )
}
