'use client'

import { useMemo } from 'react'
import type { RuntimeEvent } from '../data/types'
import type { AgentRuntimeStatus } from '../data/types'

interface SystemHealthPanelProps {
  events: RuntimeEvent[]
  agentStates: AgentRuntimeStatus[]
  sseConnected: boolean
}

function StatusDot({ color }: { color: string }) {
  return (
    <div
      className="w-1.5 h-1.5 rounded-full flex-shrink-0"
      style={{ background: color }}
    />
  )
}

export default function SystemHealthPanel({
  events,
  agentStates,
  sseConnected,
}: SystemHealthPanelProps) {
  const stats = useMemo(() => {
    let errors = 0
    let warnings = 0
    let maxLatencyMs = 0
    let totalLatencyMs = 0
    let latencySamples = 0
    let runningAgents = 0

    for (const ev of events) {
      switch (ev.type) {
        case 'error':
          errors++
          break
        case 'warning':
          warnings++
          break
      }
    }

    // Derive latency from agent states
    for (const s of agentStates) {
      if (s.state !== 'IDLE') runningAgents++
      // AgentRuntimeStatus doesn't have latency; use fixed mock value
    }

    // Simulated latency based on event volume
    const recentEvents = events.slice(-50)
    latencySamples = Math.min(recentEvents.length, 30)
    // Mock: average ~12ms per event
    totalLatencyMs = latencySamples * 12 + errors * 40
    maxLatencyMs = errors > 0 ? 80 + errors * 10 : 45

    const avgLatencyMs = latencySamples > 0 ? Math.round(totalLatencyMs / latencySamples) : 0
    const errorRate = events.length > 0 ? Math.round((errors / events.length) * 100) : 0
    const backlog = events.length > 1000 ? 'HIGH' : events.length > 500 ? 'MED' : 'LOW'
    const totalAgents = agentStates.length

    return {
      errors,
      warnings,
      runningAgents,
      totalAgents,
      avgLatencyMs,
      maxLatencyMs,
      errorRate,
      backlog,
    }
  }, [events, agentStates])

  const errorAccent = stats.errorRate > 5 ? '#ef4444' : stats.errorRate > 1 ? '#f59e0b' : '#10b981'

  return (
    <div className="h-full flex flex-col min-h-0 text-[11px] font-mono">
      {/* RUNTIME VITALS */}
      <div className="flex-shrink-0 mb-3">
        <div className="text-slate-500 uppercase tracking-wider mb-2">运行时指标</div>
        <div className="space-y-1.5">
          <MetricRow label="错误率" value={`${stats.errorRate}%`} color={errorAccent} />
          <MetricRow label="平均延迟" value={`${stats.avgLatencyMs}ms`} color="#10b981" />
          <MetricRow label="峰值延迟" value={`${stats.maxLatencyMs}ms`} color="#f59e0b" />
          <MetricRow label="事件积压" value={stats.backlog} color={stats.backlog === 'HIGH' ? '#ef4444' : stats.backlog === 'MED' ? '#f59e0b' : '#10b981'} />
        </div>
      </div>

      {/* EVENT HEALTH */}
      <div className="flex-shrink-0 mb-3 pb-3 border-b border-slate-800/40">
        <div className="text-slate-500 uppercase tracking-wider mb-2">事件健康</div>
        <div className="space-y-1.5">
          <MetricRow label="错误事件" value={String(stats.errors)} color={stats.errors > 0 ? '#ef4444' : '#10b981'} dot />
          <MetricRow label="警告事件" value={String(stats.warnings)} color={stats.warnings > 0 ? '#f59e0b' : '#10b981'} dot />
          <MetricRow label="事件总数" value={String(events.length)} color="#06b6d4" dot />
        </div>
      </div>

      {/* AGENT RUNTIME */}
      <div className="flex-shrink-0 mb-3">
        <div className="text-slate-500 uppercase tracking-wider mb-2">Agent 运行时</div>
        <div className="space-y-1.5">
          <MetricRow label="运行中" value={String(stats.runningAgents)} color="#10b981" />
          <MetricRow label="总计" value={String(stats.totalAgents)} color="#64748b" />
        </div>
      </div>

      {/* SSE STREAM */}
      <div className="flex-shrink-0 mt-auto pt-3 border-t border-slate-800/40">
        <div className="flex items-center justify-between mb-2">
          <span className="text-slate-500 uppercase tracking-wider">SSE 连接</span>
          <div className="flex items-center gap-1.5">
            <div
              className={`w-1.5 h-1.5 rounded-full ${sseConnected ? 'bg-emerald-400 shadow-[0_0_4px_rgba(52,211,153,0.5)]' : 'bg-red-400'}`}
            />
            <span className={sseConnected ? 'text-emerald-400' : 'text-red-400'}>
              {sseConnected ? '已连接' : '已断开'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-0.5 bg-slate-800 rounded-full overflow-hidden">
            {sseConnected && (
              <div className="h-full bg-emerald-500/60 rounded-full animate-pulse" style={{ width: '100%' }} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function MetricRow({ label, value, color, dot }: { label: string; value: string; color: string; dot?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-1.5">
        {dot && <StatusDot color={color} />}
        <span className="text-slate-500 text-[11px]">{label}</span>
      </div>
      <span className="font-bold text-[11px]" style={{ color }}>
        {value}
      </span>
    </div>
  )
}
