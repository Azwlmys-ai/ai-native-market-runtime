'use client'

import { useMemo } from 'react'
import type { LogEvent } from '../hooks/useLogEvents'

// ── Helpers ──────────────────────────────────────────────

const LEVEL_STYLES: Record<LogEvent['level'], { border: string; bg: string; badge: string }> = {
  ERROR: {
    border: 'border-l-red-500/50 bg-red-500/5',
    bg: 'bg-red-500/30',
    badge: 'text-red-400 bg-red-500/10 border-red-500/20',
  },
  WARN: {
    border: 'border-l-amber-500/50 bg-amber-500/5',
    bg: 'bg-amber-500/30',
    badge: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  },
  SUCCESS: {
    border: 'border-l-emerald-500/50 bg-emerald-500/5',
    bg: 'bg-emerald-500/30',
    badge: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  },
  INFO: {
    border: 'border-l-sky-500/50 bg-sky-500/5',
    bg: 'bg-sky-500/30',
    badge: 'text-sky-400 bg-sky-500/10 border-sky-500/20',
  },
}

const LEVEL_LABELS: Record<LogEvent['level'], string> = {
  ERROR: 'ERR',
  WARN: 'WARN',
  SUCCESS: 'OK',
  INFO: 'INFO',
}

const AGENT_BG: Record<string, string> = {
  orchestrator: 'bg-indigo-500/30',
  Orchestrator: 'bg-indigo-500/30',
  agent_b: 'bg-cyan-500/30',
  Agent_B: 'bg-cyan-500/30',
  agent_m: 'bg-violet-500/30',
  Agent_M: 'bg-violet-500/30',
  risk: 'bg-amber-500/30',
  execution: 'bg-emerald-500/30',
}

function agentBg(agent: string): string {
  return AGENT_BG[agent] ?? AGENT_BG[agent.toLowerCase()] ?? 'bg-slate-500/30'
}

function formatTs(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('en-US', { hour12: false })
  } catch {
    return ts.slice(-8)
  }
}

// ── Component ────────────────────────────────────────────

interface Props {
  events: LogEvent[]
  source?: 'real' | 'fallback'
  onSelectAgent?: (agentId: string | null) => void
  onSelectEvent?: (eventId: string | null) => void
  selectedEvent?: string | null
}

// ── Category grouping ────────────────────────────────────

const CATEGORY_GROUPS: Record<string, string> = {
  error: '错误 / 超时',
  stoploss: '止损保护',
  drawdown: '回撤警告',
  recovery: '系统恢复',
  connection: '连接事件',
  signal: '信号决策',
  cycle: '周期汇总',
}

function groupLabel(category: string): string {
  return CATEGORY_GROUPS[category] ?? category
}

export default function RuntimeEventFeed({ events, source, onSelectAgent, onSelectEvent, selectedEvent }: Props) {
  const loading = false
  const error = null

  // ⚡ Toggle-select helper: deselect if already selected, otherwise select new
  function toggleEvent(evId: string, agentId: string | null) {
    if (onSelectEvent) {
      onSelectEvent(selectedEvent === evId ? null : evId)
    }
    if (agentId && onSelectAgent) {
      onSelectAgent(agentId)
    }
  }

  // Group events by category for aggregated display
  const groupedEvents = useMemo(() => {
    const groups = new Map<string, LogEvent[]>()
    for (const ev of events.slice(0, 100)) {
      const cat = ev.category
      if (!groups.has(cat)) groups.set(cat, [])
      groups.get(cat)!.push(ev)
    }
    return Array.from(groups.entries())
  }, [events])

  if (loading) {
    return (
      <div className="h-full flex flex-col min-h-0">
        <Header source={source} count={0} />
        <div className="flex-1 flex items-center justify-center">
          <span className="text-[10px] text-slate-500 font-mono">加载日志事件...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full flex flex-col min-h-0">
        <Header source={source} count={0} />
        <div className="flex-1 flex items-center justify-center">
          <span className="text-[10px] text-red-400 font-mono">{error}</span>
        </div>
      </div>
    )
  }

  if (groupedEvents.length === 0) {
    return (
      <div className="h-full flex flex-col min-h-0">
        <Header source={source} count={0} />
        <div className="flex-1 flex flex-col items-center justify-center text-center gap-2">
          <p className="text-xs text-slate-500 font-mono">等待事件...</p>
          <p className="text-[10px] text-slate-600 font-mono">
            {source === 'real'
              ? '无关键事件，系统运行正常'
              : '日志事件将在编排器运行时出现'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col min-h-0">
      <Header source={source} count={groupedEvents.reduce((s, [, evs]) => s + evs.length, 0)} />
      <div className="flex-1 overflow-y-auto space-y-2 pr-0.5">
        {groupedEvents.map(([category, catEvents]) => {
          // Determine worst level in group for coloring
          const worstLevel = catEvents.some(e => e.level === 'ERROR') ? 'ERROR'
            : catEvents.some(e => e.level === 'WARN') ? 'WARN'
            : catEvents.some(e => e.level === 'SUCCESS') ? 'SUCCESS'
            : 'INFO'
          const styles = LEVEL_STYLES[worstLevel] ?? LEVEL_STYLES.INFO
          // Find first event as the representative
          const rep = catEvents[0]
          const hasAgentId = rep.agentId !== null

          return (
            <div
              key={category}
              className={`rounded-md border-l-2 p-1.5 group transition-colors ${styles.border} ${
                hasAgentId ? 'cursor-pointer hover:bg-slate-800/40' : ''
              }`}
              onClick={() => {
                if (hasAgentId && onSelectAgent) {
                  onSelectAgent(rep.agentId)
                } else if (onSelectAgent) {
                  onSelectAgent(null)
                }
              }}
              title={hasAgentId ? `Click to highlight agent: ${rep.agentId}` : undefined}
            >
              {/* Category header */}
              <div className="flex items-center justify-between mb-1">
                <span className={`text-[9px] font-bold font-mono uppercase ${LEVEL_STYLES[worstLevel]?.badge.split(' ')[0] ?? 'text-slate-400'} px-1 rounded`}>
                  {groupLabel(category)}
                </span>
                <div className="flex items-center gap-1.5">
                  {hasAgentId && (
                    <span className="text-[7px] font-mono text-slate-500 bg-slate-800/50 px-1 rounded">
                      🔗 {rep.agentId}
                    </span>
                  )}
                  <span className="text-[8px] font-mono text-slate-600">
                    {catEvents.length}
                  </span>
                </div>
              </div>
              {/* Representative event title */}
              <p className="text-[10px] text-slate-200 font-mono leading-relaxed break-words m-0 mb-1">
                {rep.title}
              </p>
              {/* Show up to 3 recent events within this group */}
              {catEvents.slice(0, 3).map((ev) => (
                <div
                  key={ev.id}
                  onClick={(e) => {
                    e.stopPropagation()
                    toggleEvent(ev.id, ev.agentId)
                  }}
                  className={`flex items-center gap-1.5 text-[8px] text-slate-500 font-mono pl-1.5 border-l border-slate-700/30 mb-0.5 rounded-sm cursor-pointer hover:bg-slate-800/40 transition-colors ${
                    selectedEvent === ev.id
                      ? 'bg-cyan-500/10 border-cyan-500/40 shadow-[0_0_6px_rgba(34,211,238,0.15)]'
                      : ''
                  }`}
                  title={onSelectEvent ? '点击高亮该事件' : undefined}
                >
                  <span className="text-slate-600 flex-shrink-0">{formatTs(ev.timestamp)}</span>
                  <span
                    className={`px-1 py-px rounded text-white flex-shrink-0 ${agentBg(ev.agent)}`}
                  >
                    {ev.agent}
                  </span>
                  <span
                    className={`px-1 py-px rounded text-[7px] font-bold uppercase ${styles.badge}`}
                  >
                    {LEVEL_LABELS[ev.level]}
                  </span>
                  {ev.title && (
                    <span className="truncate max-w-[120px] text-slate-400/70 hidden group-hover:inline">
                      {ev.title}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Sub-components ───────────────────────────────────────

function Header({ source, count }: { source: string | undefined; count: number }) {
  return (
    <div className="flex items-center justify-between mb-2 pb-1.5 border-b border-slate-700/50 flex-shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-bold font-mono text-slate-400 uppercase tracking-widest">
          运行时事件流
        </span>
        <span className="text-[7px] font-mono text-slate-600 bg-slate-800/50 px-1 rounded">
          按类别聚合
        </span>
        {source === 'real' && (
          <span className="text-[8px] font-bold font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/30 uppercase tracking-wider">
            REAL DATA
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[9px] font-mono text-slate-600">{count} 事件</span>
        <span className="text-[8px] font-bold font-mono text-red-400 bg-red-500/10 border border-red-500/20 px-1.5 rounded">
          只读
        </span>
      </div>
    </div>
  )
}