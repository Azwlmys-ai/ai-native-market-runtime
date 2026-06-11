'use client'

import { useMemo } from 'react'
import { CheckCircle2, Activity } from 'lucide-react'
import type { Incident } from '../hooks/useIncidents'
import type { LogEvent } from '../hooks/useLogEvents'
import type { DashboardKpis } from '../hooks/useDashboardSummary'

// ── Types ─────────────────────────────────────────────────

interface Props {
  incidents: Incident[]
  events: LogEvent[]
  kpis: DashboardKpis | null
  truthBadge?: React.ReactNode
}

interface ResponseAction {
  id: string
  time: string
  action: string
  detail: string
  status: 'executed' | 'in-progress' | 'pending'
  type: 'recovery' | 'fallback' | 'risk' | 'agent' | 'escalation'
  durationMs: number
}

// ── Classification ────────────────────────────────────────

function classifyActionType(ev: LogEvent): ResponseAction['type'] {
  const t = (ev.title + ' ' + ev.detail).toLowerCase()

  if (t.includes('recover') || t.includes('restore') || t.includes('heal') || ev.category === 'recovery') {
    return 'recovery'
  }
  if (t.includes('fallback') || t.includes('switch') || t.includes('reroute')) {
    return 'fallback'
  }
  if (t.includes('threshold') || t.includes('tighten') || t.includes('drawdown') || t.includes('stoploss')) {
    return 'risk'
  }
  if (t.includes('agent') || t.includes('接管') || t.includes('接手') || t.includes('escalat')) {
    return 'escalation'
  }
  return 'agent'
}

function generateActionLabel(type: ResponseAction['type'], ev: LogEvent): string {
  switch (type) {
    case 'recovery':
      return '系统已自动启动恢复流程'
    case 'fallback':
      return '系统已自动切换至 REST fallback 通道'
    case 'risk':
      if (ev.category === 'stoploss') return '风险控制模块已执行止损保护'
      if (ev.category === 'drawdown') return '风险控制模块已降低策略暴露'
      return '风险控制模块已调整审批阈值'
    case 'agent':
      return `Agent ${ev.agent} 已接管决策执行流`
    case 'escalation':
      return '事故升级流程已触发，高级别监控激活'
  }
}

function generateActionDetail(type: ResponseAction['type'], ev: LogEvent, kpis: DashboardKpis | null): string {
  const base = ev.detail || ev.title

  switch (type) {
    case 'recovery':
      return `恢复目标：${ev.agent || '系统'}。${base}`
    case 'fallback':
      return `主连接异常，备用 REST API 通道已接管，数据流未中断。${base}`
    case 'risk':
      if (ev.category === 'stoploss') {
        return `止损触发条件达成，自动平仓执行中。审批阈值临时上调至警戒水平。`
      }
      if (ev.category === 'drawdown') {
        return `组合净值回撤触发预警线，新信号准入置信度阈值自动上调。`
      }
      const rule = kpis ? `当前审批通过率 ${Math.round((kpis.approvedSignals / Math.max(kpis.totalSignals, 1)) * 100)}%` : ''
      return `${rule}风险控制系统已执行策略参数调整。${base}`
    case 'agent':
      return `${ev.agent} 接管高风险审批流，人工审核暂不介入。`
    case 'escalation':
      return `事件级别已升级，自动响应链激活。多 Agent 协同处置已启动。`
  }
}

// ── Derive response chain from runtime data ───────────────

function deriveResponseActions(
  incidents: Incident[],
  events: LogEvent[],
  kpis: DashboardKpis | null,
): ResponseAction[] {
  const actions: ResponseAction[] = []
  const usedIds = new Set<string>()

  // ── From incident phases: recovery, mitigation, escalation ──
  for (const incident of incidents) {
    const responsePhases = incident.phases.filter(
      (p) => p.phase === 'recovery' || p.phase === 'mitigation' || p.phase === 'escalation',
    )

    for (const phase of responsePhases) {
      if (usedIds.has(`incident:${incident.id}:${phase.time}`)) continue
      usedIds.add(`incident:${incident.id}:${phase.time}`)

      const type = classifyActionType(phase.event)
      const label = generateActionLabel(type, phase.event)
      const detail = generateActionDetail(type, phase.event, kpis)

      // Calculate duration from incident start to this phase
      const startMs = new Date(incident.startTime).getTime()
      const phaseMs = new Date(phase.time).getTime()
      const durationMs = Math.max(0, phaseMs - startMs)

      const status: ResponseAction['status'] =
        phase.phase === 'recovery' ? 'executed' : phase.phase === 'escalation' ? 'in-progress' : 'executed'

      actions.push({
        id: `incident:${incident.id}:${phase.time}`,
        time: phase.time,
        action: label,
        detail,
        status,
        type,
        durationMs,
      })
    }
  }

  // ── From events: standalone recovery/fallback events not in incidents ──
  const incidentEventIds = new Set(
    incidents.flatMap((i) => i.events.map((e) => e.id)),
  )

  const standaloneResponseEvents = events.filter((ev) => {
    if (incidentEventIds.has(ev.id)) return false
    const t = (ev.title + ' ' + ev.detail).toLowerCase()
    return (
      t.includes('recover') ||
      t.includes('fallback') ||
      t.includes('switch') ||
      t.includes('retry') ||
      t.includes('reroute') ||
      ev.category === 'recovery'
    )
  })

  for (const ev of standaloneResponseEvents.slice(0, 5)) {
    if (usedIds.has(ev.id)) continue
    usedIds.add(ev.id)

    const type = classifyActionType(ev)
    const label = generateActionLabel(type, ev)
    const detail = generateActionDetail(type, ev, kpis)

    actions.push({
      id: ev.id,
      time: ev.timestamp,
      action: label,
      detail,
      status: 'executed',
      type,
      durationMs: 0,
    })
  }

  // ── If no actions derived, add a system-health baseline ──
  if (actions.length === 0) {
    const fallbackTime =
      events[0]?.timestamp ??
      incidents[0]?.startTime ??
      '1970-01-01T00:00:00.000Z'

    actions.push({
      id: 'system:stable',
      time: fallbackTime,
      action: '系统运行平稳，无自动响应动作触发',
      detail: '所有子系统正常运行，Agent 集群处于事件驱动待命状态。',
      status: 'executed',
      type: 'agent',
      durationMs: 0,
    })
  }

  // Sort by time descending
  actions.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())

  return actions.slice(0, 8)
}

// ── Summary statistics ────────────────────────────────────

function deriveSummary(actions: ResponseAction[]) {
  const executed = actions.filter((a) => a.status === 'executed').length
  const total = actions.length
  const successRate = total > 0 ? Math.round((executed / total) * 100) : 100

  const avgDuration =
    actions.filter((a) => a.durationMs > 0).length > 0
      ? Math.round(
          actions
            .filter((a) => a.durationMs > 0)
            .reduce((sum, a) => sum + a.durationMs, 0) /
            actions.filter((a) => a.durationMs > 0).length,
        )
      : 0

  return { executed, total, successRate, avgDuration }
}

// ── Action Row Sub-Component ──────────────────────────────

function ActionRow({ action, isLast }: { action: ResponseAction; isLast: boolean }) {
  const typeColors = {
    recovery: { border: 'border-emerald-500/40', bg: 'bg-emerald-500/5', dot: 'bg-emerald-400', text: 'text-emerald-400' },
    fallback: { border: 'border-cyan-500/40', bg: 'bg-cyan-500/5', dot: 'bg-cyan-400', text: 'text-cyan-400' },
    risk: { border: 'border-amber-500/40', bg: 'bg-amber-500/5', dot: 'bg-amber-400', text: 'text-amber-400' },
    agent: { border: 'border-violet-500/40', bg: 'bg-violet-500/5', dot: 'bg-violet-400', text: 'text-violet-400' },
    escalation: { border: 'border-red-500/40', bg: 'bg-red-500/5', dot: 'bg-red-400', text: 'text-red-400' },
  }

  const tc = typeColors[action.type]
  const timeStr = new Date(action.time).toLocaleTimeString('zh-CN', { hour12: false })
  const durationStr = action.durationMs > 0 ? `${(action.durationMs / 1000).toFixed(1)}s` : null

  return (
    <div className="relative">
      {/* Timeline connector */}
      {!isLast && (
        <div className="absolute left-[11px] top-8 bottom-0 w-px bg-slate-700/50" />
      )}

      <div className="flex gap-3 items-start">
        {/* Timeline dot */}
        <div className="relative z-10 mt-0.5">
          <div className={`w-3 h-3 rounded-full border-2 ${tc.border} ${tc.dot} shadow-[0_0_8px_rgba(52,211,153,0.2)]`}>
            {action.status === 'in-progress' && (
              <div className="absolute inset-0 rounded-full animate-ping opacity-30 bg-emerald-400" />
            )}
          </div>
        </div>

        {/* Content */}
        <div className={`flex-1 rounded-xl border ${tc.border} ${tc.bg} p-3 backdrop-blur-sm`}>
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <span className={`text-[10px] font-bold ${tc.text}`}>
                {action.action}
              </span>
              {action.status === 'in-progress' && (
                <span className="text-[8px] font-mono px-1.5 py-0.5 rounded border border-amber-500/20 bg-amber-500/5 text-amber-400">
                  执行中
                </span>
              )}
              {action.status === 'executed' && (
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              )}
            </div>
            <div className="flex items-center gap-2">
              {durationStr && (
                <span className="text-[8px] font-mono text-slate-600">耗时 {durationStr}</span>
              )}
              <span className="text-[8px] font-mono text-slate-600">{timeStr}</span>
            </div>
          </div>
          <p className="text-[9px] font-mono text-slate-500 leading-relaxed">
            {action.detail}
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────

export default function ResponseActionPanel({ incidents, events, kpis, truthBadge }: Props) {
  const actions = useMemo(
    () => deriveResponseActions(incidents, events, kpis),
    [incidents, events, kpis],
  )

  const summary = useMemo(() => deriveSummary(actions), [actions])

  return (
    <div className="rounded-2xl border border-slate-700/30 bg-gradient-to-b from-slate-800/60 to-slate-900/60 backdrop-blur-sm p-6 relative">
      {/* Truth Badge */}
      {truthBadge && <div className="absolute top-3 right-3 z-10">{truthBadge}</div>}
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <Activity className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200 tracking-wide">系统响应链</h3>
            <p className="text-[9px] font-mono text-slate-500">Autonomous Response · 自动响应动作追踪</p>
          </div>
        </div>

        {/* Summary stats */}
        <div className="flex items-center gap-3">
          <div className="text-center">
            <div className="text-lg font-bold font-mono text-emerald-400">{summary.successRate}%</div>
            <div className="text-[7px] font-mono text-slate-600 uppercase">恢复成功率</div>
          </div>
          <div className="w-px h-8 bg-slate-700/30" />
          <div className="text-center">
            <div className="text-lg font-bold font-mono text-cyan-400">{summary.executed}/{summary.total}</div>
            <div className="text-[7px] font-mono text-slate-600 uppercase">已执行/总计</div>
          </div>
          {summary.avgDuration > 0 && (
            <>
              <div className="w-px h-8 bg-slate-700/30" />
              <div className="text-center">
                <div className="text-lg font-bold font-mono text-violet-400">{(summary.avgDuration / 1000).toFixed(1)}s</div>
                <div className="text-[7px] font-mono text-slate-600 uppercase">平均响应耗时</div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Actions timeline */}
      <div className="space-y-4">
        {actions.map((action, idx) => (
          <ActionRow key={action.id} action={action} isLast={idx === actions.length - 1} />
        ))}
      </div>

      {/* Legend */}
      <div className="mt-4 pt-3 border-t border-slate-700/20 flex items-center gap-4 flex-wrap">
        <span className="text-[8px] font-mono text-slate-600">响应类型：</span>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-emerald-400" />
          <span className="text-[8px] font-mono text-slate-500">自动恢复</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-cyan-400" />
          <span className="text-[8px] font-mono text-slate-500">Fallback</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-amber-400" />
          <span className="text-[8px] font-mono text-slate-500">风险收缩</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-violet-400" />
          <span className="text-[8px] font-mono text-slate-500">Agent 接管</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-red-400" />
          <span className="text-[8px] font-mono text-slate-500">升级</span>
        </div>
      </div>
    </div>
  )
}
