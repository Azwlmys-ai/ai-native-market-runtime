'use client'

import { useRuntimeSnapshot } from '../data/runtimeState'

export default function SystemMetricsBar() {
  const snapshot = useRuntimeSnapshot()
  const { metrics } = snapshot
  const online = metrics.online
  const wsOk = metrics.wsStatus === 'connected'

  interface MetricDef {
    label: string
    value: string
    color?: string
    blink?: boolean
  }

  const items: MetricDef[] = [
    {
      label: 'RUNTIME',
      value: online ? 'ONLINE' : 'OFFLINE',
      color: online ? 'text-emerald-400' : 'text-red-400',
      blink: online,
    },
    {
      label: 'AGENTS',
      value: `${metrics.activeAgents}/${metrics.totalAgents} active`,
      color: 'text-cyan-400',
    },
    {
      label: 'TASKS/S',
      value: String(metrics.tasksPerSec),
      color: 'text-slate-200',
    },
    {
      label: 'TOKENS/S',
      value: String(metrics.tokensPerSec),
      color: 'text-violet-400',
    },
    {
      label: 'PNL',
      value: `$${metrics.pnl.toLocaleString()}`,
      color: metrics.pnl >= 0 ? 'text-emerald-400' : 'text-red-400',
    },
    {
      label: 'REGIME',
      value: metrics.riskRegime,
      color: 'text-amber-400',
    },
    {
      label: 'WS',
      value: wsOk ? 'CONNECTED' : 'RECONNECTING',
      color: wsOk ? 'text-emerald-400' : 'text-red-400',
      blink: !wsOk,
    },
    {
      label: 'ERR',
      value: String(snapshot.logs.filter(l => l.type === 'escalation' || l.type === 'timeout').slice(0, 99).length),
      color: 'text-red-400',
    },
  ]

  return (
    <div className="flex items-center gap-0 overflow-x-auto flex-nowrap h-full">
      {items.map((m, i) => (
        <div
          key={m.label}
          className={`flex items-center gap-2 px-3 py-1.5 border-r border-slate-700/40 flex-shrink-0 ${i === 0 ? 'border-l border-slate-700/40' : ''}`}
        >
          <span className="text-xs text-slate-600 font-mono uppercase tracking-wide whitespace-nowrap">{m.label}</span>
          <span className={`text-xs font-bold font-mono whitespace-nowrap ${m.color ?? 'text-slate-200'} ${m.blink ? 'animate-pulse' : ''}`}>
            {m.value}
          </span>
        </div>
      ))}
    </div>
  )
}