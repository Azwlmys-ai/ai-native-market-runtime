'use client'

import type { RuntimeEvent } from '../data/types'

interface Props {
  events: RuntimeEvent[]
}

export default function ExecutiveKeyRuntimeEvents({ events }: Props) {
  // Filter to high-value events only — exclude low-level info events
  const keyEvents = events
    .filter((e) => {
      const msg = e.message.toLowerCase()
      // Include only significant events
      return (
        e.severity === 'error' ||
        e.severity === 'warning' ||
        msg.includes('stoploss') ||
        msg.includes('risk override') ||
        msg.includes('reconnect') ||
        msg.includes('recovery') ||
        msg.includes('consensus') ||
        msg.includes('high-confidence') ||
        msg.includes('arbitrage') ||
        msg.includes('rejected') ||
        msg.includes('triggered') ||
        msg.includes('recovered') ||
        msg.includes('activated') ||
        (e.type === 'review_rejected')
      )
    })
    .slice(0, 12)

  if (keyEvents.length === 0) {
    return (
      <div className="flex-shrink-0 px-6 py-4">
        <div className="mb-3 flex items-center gap-2">
          <span className="text-[9px] font-mono text-purple-400 bg-purple-500/10 border border-purple-500/20 px-1.5 py-0.5 rounded">
            关键运行事件
          </span>
        </div>
        <div className="rounded-lg border border-slate-500/10 bg-slate-500/3 p-6 text-center">
          <span className="text-[10px] font-mono text-slate-600">
            等待系统事件流...
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-shrink-0 px-6 py-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-[9px] font-mono text-purple-400 bg-purple-500/10 border border-purple-500/20 px-1.5 py-0.5 rounded">
          关键运行事件
        </span>
        <span className="text-[11px] font-mono text-slate-500">
          最近高价值事件 — 验证系统真实行为
        </span>
        <span className="text-[9px] font-mono text-slate-600 ml-auto">
          {keyEvents.length} 条事件
        </span>
      </div>

      <div className="rounded-lg border border-white/[0.03] bg-slate-900/20 overflow-hidden">
        {/* Column headers */}
        <div className="grid grid-cols-[auto_1fr_auto] gap-3 px-4 py-2 border-b border-white/[0.03] bg-slate-900/40 text-[9px] font-mono text-slate-600 uppercase tracking-wider">
          <span className="w-20">时间</span>
          <span>事件描述</span>
          <span className="w-16 text-right">严重度</span>
        </div>

        {/* Event rows */}
        <div className="divide-y divide-white/[0.02]">
          {keyEvents.map((event) => (
            <EventRow key={event.id} event={event} />
          ))}
        </div>
      </div>

      <div className="mt-2">
        <p className="text-[8px] font-mono text-slate-700 italic leading-snug">
          💬 以上为经过过滤的高价值事件，展示系统真实行为：风险拦截、自动恢复、共识决策。完整事件流可切换到 Runtime 模式查看。
        </p>
      </div>
    </div>
  )
}

function EventRow({ event }: { event: RuntimeEvent }) {
  const isError = event.severity === 'error'
  const isWarning = event.severity === 'warning'

  const severityBadge = isError
    ? 'text-red-400 bg-red-500/10 border-red-500/20'
    : isWarning
    ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
    : 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'

  const severityLabel = isError ? 'CRITICAL' : isWarning ? 'WARNING' : 'NORMAL'

  const sourceLabel =
    event.source === 'orchestrator'
      ? 'Orch'
      : event.source === 'agent_b'
      ? 'Agent-B'
      : event.source === 'agent_m'
      ? 'Agent-M'
      : event.source === 'risk'
      ? 'Risk'
      : event.source === 'execution'
      ? 'Exec'
      : event.source

  return (
    <div
      className={`grid grid-cols-[auto_1fr_auto] gap-3 px-4 py-2 items-center ${
        isError ? 'bg-red-500/3' : ''
      }`}
    >
      {/* Timestamp */}
      <span className="w-20 text-[10px] font-mono text-slate-500">{event.ts.slice(0, 8)}</span>

      {/* Event description */}
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-[9px] font-mono text-slate-600 bg-slate-800/60 px-1 py-0 rounded flex-shrink-0">
          {sourceLabel}
        </span>
        <span className="text-[11px] font-mono text-slate-300 truncate">{event.message}</span>
      </div>

      {/* Severity */}
      <div className="w-16 flex justify-end">
        <span
          className={`text-[8px] font-mono border px-1.5 py-0.5 rounded ${severityBadge}`}
        >
          {severityLabel}
        </span>
      </div>
    </div>
  )
}