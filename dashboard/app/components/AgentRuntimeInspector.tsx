'use client'

import { useMemo } from 'react'
import { useLogEvents, type LogEvent, type LogLevel } from '../hooks/useLogEvents'
import type { AgentRuntimeStatus } from '../data/types'

// ── Types ─────────────────────────────────────────────────

export interface AgentInfo {
  id: string
  name: string
  layer: string
  status: string
  currentTask: string
  latencyMs: number
  tokensUsed: number
  llmCalls: number
  cacheHit: boolean
  queueSize: number
  successRate: number
}

interface Props {
  agent: AgentInfo | null
  agentRuntimeState: AgentRuntimeStatus | null
  selectedEvent: string | null
}

// ── Helpers ──────────────────────────────────────────────

const LEVEL_STYLE: Record<LogLevel, { bg: string; border: string; text: string; dot: string }> = {
  SUCCESS: {
    bg: 'bg-emerald-500/10',
    border: 'border-l-emerald-500/60',
    text: 'text-emerald-400',
    dot: 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]',
  },
  ERROR: {
    bg: 'bg-red-500/10',
    border: 'border-l-red-500/60',
    text: 'text-red-400',
    dot: 'bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.5)]',
  },
  WARN: {
    bg: 'bg-amber-500/10',
    border: 'border-l-amber-500/60',
    text: 'text-amber-400',
    dot: 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.5)]',
  },
  INFO: {
    bg: 'bg-sky-500/10',
    border: 'border-l-sky-500/60',
    text: 'text-sky-400',
    dot: 'bg-sky-400 shadow-[0_0_6px_rgba(56,189,248,0.5)]',
  },
}

const LEVEL_LABEL: Record<LogLevel, string> = {
  SUCCESS: '成功',
  ERROR: '错误',
  WARN: '警告',
  INFO: '信息',
}

const AGENT_ID_MAP: Record<string, string> = {
  orchestrator: 'orchestrator',
  agent_b: 'agent_b',
  agent_m: 'agent_m',
  risk: 'risk',
  execution: 'execution',
}

function resolveAgentId(agent: AgentInfo): string {
  return AGENT_ID_MAP[agent.id] ?? agent.id.toLowerCase()
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return ts.slice(-8)
  }
}

function formatRelativeTime(ts: string): string {
  try {
    const ms = Date.now() - new Date(ts).getTime()
    if (ms < 0) return '刚刚'
    const sec = Math.floor(ms / 1000)
    if (sec < 60) return `${sec}秒前`
    const min = Math.floor(sec / 60)
    if (min < 60) return `${min}分钟前`
    const hrs = Math.floor(min / 60)
    if (hrs < 24) return `${hrs}小时前`
    const days = Math.floor(hrs / 24)
    return `${days}天前`
  } catch {
    return ts
  }
}

// ── Smart Diagnosis Engine ────────────────────────────────

interface Diagnosis {
  issue: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  recommendation: string
  action: string
}

function generateDiagnosis(events: LogEvent[], agentRuntimeState: AgentRuntimeStatus | null): Diagnosis | null {
  if (events.length === 0) return null

  // Count categories and levels
  const cats = new Map<string, number>()
  const levels = new Map<LogLevel, number>()
  for (const ev of events) {
    cats.set(ev.category, (cats.get(ev.category) ?? 0) + 1)
    levels.set(ev.level, (levels.get(ev.level) ?? 0) + 1)
  }

  const errorCount = levels.get('ERROR') ?? 0
  const warnCount = levels.get('WARN') ?? 0
  const stoplossCount = cats.get('stoploss') ?? 0
  const drawdownCount = cats.get('drawdown') ?? 0
  const connectionCount = cats.get('connection') ?? 0
  const recoveryCount = cats.get('recovery') ?? 0
  const signalCount = cats.get('signal') ?? 0

  // Priority: ERROR > stoploss > drawdown > connection > recovery > normal
  if (errorCount >= 3) {
    return {
      issue: 'Agent 持续异常 — 最近检测到多次错误/超时',
      severity: 'critical',
      recommendation: '错误频率过高，建议立即排查 LLM Provider 延迟、API 限流或网络连通性',
      action: '检查 Provider 状态 · 启用备用 Provider · 暂停该 Agent 自动调度',
    }
  }

  if (stoplossCount >= 2) {
    return {
      issue: '止损保护多次触发 — 市场波动超出风控阈值',
      severity: 'high',
      recommendation: '止损连续触发表明当前仓位风险敞口过大，建议降低单笔仓位上限',
      action: '降低风险敞口 · 检查市场波动率 · 审查止损参数配置',
    }
  }

  if (drawdownCount >= 1) {
    return {
      issue: '检测到回撤扩大 — 账户净值持续下降',
      severity: 'high',
      recommendation: '回撤警告表明当前策略组合正在亏损，建议暂停新开仓并审查现有持仓',
      action: '暂停新交易 · 审查持仓组合 · 检查资金费率变化',
    }
  }

  if (warnCount >= 2) {
    return {
      issue: '多个警告事件 — 系统运行存在不稳定因素',
      severity: 'medium',
      recommendation: '警告事件累积，建议检查最近日志以确认是否需要人工干预',
      action: '检查 WS 连接状态 · 审查最近拒绝信号 · 确认链上数据延迟',
    }
  }

  if (connectionCount >= 2) {
    return {
      issue: '连接频繁变化 — 交易所 WS 连接不稳定',
      severity: 'medium',
      recommendation: 'WS 连接频繁断开/重连可能影响实时数据获取，建议检查网络或切换接入点',
      action: '检查网络稳定性 · 确认交易所 API 状态 · 自动重连已启用',
    }
  }

  if (errorCount === 1) {
    return {
      issue: '检测到单次错误 — 疑似瞬时异常',
      severity: 'low',
      recommendation: '单次错误已记录，系统已自动恢复。建议观察后续周期是否复现',
      action: '继续观察 · 检查错误详情 · 无需立即干预',
    }
  }

  if (recoveryCount >= 1) {
    return {
      issue: '系统自愈完成 — 已从异常状态恢复',
      severity: 'low',
      recommendation: '系统已自动完成恢复流程，所有组件运行正常',
      action: '无需人工介入 · 系统自愈正常工作',
    }
  }

  if (signalCount >= 3 && errorCount === 0 && warnCount === 0) {
    return {
      issue: 'Agent 运行正常 — 持续产出高质量交易信号',
      severity: 'low',
      recommendation: '当前周期未检测到任何异常，信号生成频率正常',
      action: '继续保持 · 无需调整',
    }
  }

  // Check runtime state
  if (agentRuntimeState) {
    switch (agentRuntimeState.state) {
      case 'ERROR':
        return {
          issue: 'Agent 状态异常 — 处于 ERROR 状态',
          severity: 'high',
          recommendation: 'Agent 当前处于错误状态，可能已停止处理任务',
          action: '检查错误日志 · 手动触发恢复 · 必要时重启 Agent',
        }
      case 'WARNING':
        return {
          issue: 'Agent 状态警告 — 处于 WARNING 状态',
          severity: 'medium',
          recommendation: 'Agent 检测到潜在问题但仍在运行',
          action: '审查警告原因 · 持续监控',
        }
    }
  }

  return null
}

function severityStyle(severity: Diagnosis['severity']): string {
  switch (severity) {
    case 'critical':
      return 'border-red-500/60 bg-red-500/10 text-red-400'
    case 'high':
      return 'border-amber-500/60 bg-amber-500/10 text-amber-400'
    case 'medium':
      return 'border-yellow-500/60 bg-yellow-500/10 text-yellow-400'
    case 'low':
      return 'border-emerald-500/60 bg-emerald-500/10 text-emerald-400'
  }
}

function severityLabel(severity: Diagnosis['severity']): string {
  switch (severity) {
    case 'critical': return '严重'
    case 'high': return '高'
    case 'medium': return '中'
    case 'low': return '低'
  }
}

// ── Component ────────────────────────────────────────────

export default function AgentRuntimeInspector({ agent, agentRuntimeState, selectedEvent }: Props) {
  const { events: allEvents, source, loading, error: fetchError } = useLogEvents()

  // Resolve agent identity for filtering
  const agentId = useMemo(() => (agent ? resolveAgentId(agent) : null), [agent])

  // Filter events for this agent
  const agentEvents = useMemo(() => {
    if (!agentId) return []
    return allEvents
      .filter(
        (ev) =>
          ev.agentId === agentId ||
          ev.agent.toLowerCase() === agentId.toLowerCase()
      )
      .slice(0, 20) // latest 20
  }, [allEvents, agentId])

  const recentEvents = useMemo(() => agentEvents.slice(0, 10), [agentEvents])

  // Smart diagnosis
  const diagnosis = useMemo(
    () => generateDiagnosis(agentEvents, agentRuntimeState),
    [agentEvents, agentRuntimeState]
  )

  // Determine current status display
  const displayStatus = agentRuntimeState?.state ?? 'IDLE'

  // Empty state
  if (!agent) {
    return (
      <div className="flex-1 min-h-0 p-3 flex flex-col items-center justify-center bg-slate-900/20 border-l border-white/[0.03]">
        <div className="w-10 h-10 rounded-full bg-slate-800/50 flex items-center justify-center mb-3">
          <svg className="w-5 h-5 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
        </div>
        <p className="text-[11px] font-mono text-slate-500">选择 Agent 查看运行详情</p>
        <p className="text-[9px] font-mono text-slate-600 mt-1">点击拓扑节点或运行时事件</p>
      </div>
    )
  }

  // Loading
  if (loading) {
    return (
      <div className="flex-1 min-h-0 p-3 flex flex-col bg-slate-900/20 border-l border-white/[0.03] overflow-hidden">
        <InspectorHeader agent={agent} />
        <div className="flex-1 flex items-center justify-center">
          <span className="text-[10px] text-slate-500 font-mono animate-pulse">加载运行数据...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 min-h-0 bg-slate-900/20 border-l border-white/[0.03] flex flex-col overflow-hidden">
      {/* ── Header ── */}
      <InspectorHeader agent={agent} />

      {/* ── Scrollable Body ── */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* ── Basic Info ── */}
        <AgentBasicInfo
          agent={agent}
          displayStatus={displayStatus}
          agentRuntimeState={agentRuntimeState}
          recentEvents={recentEvents}
        />

        {/* ── Smart Diagnosis ── */}
        {diagnosis && <DiagnosisCard diagnosis={diagnosis} />}
        {!diagnosis && agentEvents.length === 0 && (
          <div className="rounded-lg border border-slate-700/30 bg-slate-800/20 p-3 text-center">
            <p className="text-[10px] font-mono text-slate-500">暂无实时运行数据</p>
            <p className="text-[8px] font-mono text-slate-600 mt-1">
              {source === 'real' ? '系统运行正常，未检测到关键事件' : '等待运行事件产生'}
            </p>
          </div>
        )}

        {/* ── Fetch Error ── */}
        {fetchError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-2">
            <p className="text-[9px] font-mono text-red-400">获取日志失败: {fetchError}</p>
          </div>
        )}

        {/* ── Recent Events Timeline ── */}
        {recentEvents.length > 0 && (
          <EventTimeline
            events={recentEvents}
            selectedEvent={selectedEvent}
          />
        )}

        {/* ── Layer Description ── */}
        <LayerDescription layer={agent.layer} />
      </div>
    </div>
  )
}

// ── Sub-components ───────────────────────────────────────

function InspectorHeader({ agent }: { agent: AgentInfo }) {
  return (
    <div className="flex-shrink-0 px-3 py-2.5 border-b border-white/[0.04] bg-slate-900/40">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-[11px] font-bold font-mono text-slate-400 uppercase tracking-widest">
          Agent 运行检查器
        </h2>
        <span className="text-[8px] font-mono text-cyan-400 bg-cyan-500/10 px-1.5 py-0.5 rounded border border-cyan-500/20">
          INSPECTOR
        </span>
      </div>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-sm font-bold font-mono text-white">{agent.name}</span>
        <span className="text-[9px] font-mono text-slate-500">
          {agent.id}
        </span>
      </div>
    </div>
  )
}

function AgentBasicInfo({
  agent,
  displayStatus,
  agentRuntimeState,
  recentEvents,
}: {
  agent: AgentInfo
  displayStatus: string
  agentRuntimeState: AgentRuntimeStatus | null
  recentEvents: LogEvent[]
}) {
  const lastActive = agentRuntimeState?.updatedAt
    ? formatRelativeTime(agentRuntimeState.updatedAt)
    : '未知'
  const lastEventTime = recentEvents.length > 0
    ? recentEvents[0].timestamp
    : null

  const statusColor =
    displayStatus === 'RUNNING' || displayStatus === 'APPROVED' || displayStatus === 'EXECUTING' || displayStatus === 'DRY_RUN'
      ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
      : displayStatus === 'ERROR'
        ? 'text-red-400 bg-red-500/10 border-red-500/30'
        : displayStatus === 'WARNING' || displayStatus === 'RECOVERING'
          ? 'text-amber-400 bg-amber-500/10 border-amber-500/30'
          : 'text-slate-400 bg-slate-500/10 border-slate-500/30'

  return (
    <div className="rounded-lg border border-white/[0.06] bg-slate-800/30 p-3 space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[9px] font-mono text-slate-500">当前状态</span>
        <span
          className={`text-[10px] font-bold font-mono px-2 py-0.5 rounded border ${statusColor}`}
        >
          {displayStatus}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        <InfoItem label="层级" value={agent.layer.toUpperCase()} />
        <InfoItem label="延迟" value={`${agent.latencyMs}ms`} />
        <InfoItem label="Token" value={String(agent.tokensUsed)} />
        <InfoItem label="LLM 调用" value={String(agent.llmCalls)} />
        <InfoItem label="成功率" value={`${agent.successRate}%`} />
        <InfoItem label="队列" value={String(agent.queueSize)} />
      </div>

      <div className="pt-2 border-t border-white/[0.04] space-y-1">
        <InfoItem label="最后活跃" value={lastActive} />
        {lastEventTime && <InfoItem label="最近事件" value={formatTime(lastEventTime)} />}
        <InfoItem label="当前任务" value={agent.currentTask || '无'} />
      </div>
    </div>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-[8px] font-mono text-slate-600">{label}</span>
      <span className="text-[10px] font-mono text-slate-300">{value}</span>
    </div>
  )
}

function DiagnosisCard({ diagnosis }: { diagnosis: Diagnosis }) {
  const sevStyle = severityStyle(diagnosis.severity)
  return (
    <div className={`rounded-lg border p-3 ${sevStyle} bg-opacity-10`}>
      <div className="flex items-center gap-1.5 mb-1.5">
        <div className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
        <span className="text-[10px] font-bold font-mono uppercase tracking-wider">智能诊断</span>
        <span
          className={`text-[8px] font-bold font-mono px-1.5 py-0.5 rounded border ${sevStyle}`}
        >
          风险等级: {severityLabel(diagnosis.severity)}
        </span>
      </div>
      <p className="text-[11px] font-mono font-bold text-white mb-2">{diagnosis.issue}</p>
      <div className="space-y-1.5 mt-2 pt-2 border-t border-current/20">
        <div>
          <span className="text-[8px] font-mono text-slate-500">原因分析</span>
          <p className="text-[10px] font-mono text-slate-300 mt-0.5">{diagnosis.recommendation}</p>
        </div>
        <div>
          <span className="text-[8px] font-mono text-slate-500">推荐动作</span>
          <p className="text-[10px] font-mono text-cyan-400 mt-0.5">{diagnosis.action}</p>
        </div>
      </div>
    </div>
  )
}

function EventTimeline({
  events,
  selectedEvent,
}: {
  events: LogEvent[]
  selectedEvent: string | null
}) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-slate-800/30 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[9px] font-bold font-mono text-slate-400 uppercase tracking-wider">
          最近运行事件
        </span>
        <span className="text-[7px] font-mono text-slate-600">{events.length} 条</span>
      </div>
      <div className="space-y-1.5 max-h-60 overflow-y-auto pr-0.5">
        {events.map((ev) => {
          const style = LEVEL_STYLE[ev.level] ?? LEVEL_STYLE.INFO
          const isSelected = selectedEvent === ev.id
          return (
            <div
              key={ev.id}
              className={`relative pl-3 border-l-2 rounded-sm transition-all ${style.border} ${
                isSelected
                  ? 'bg-cyan-500/10 shadow-[0_0_8px_rgba(34,211,238,0.15)]'
                  : 'hover:bg-slate-800/40'
              }`}
            >
              <div
                className={`absolute left-[-3.5px] top-1.5 w-1.5 h-1.5 rounded-full ${style.dot}`}
              />
              <div className="py-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-[8px] font-mono text-slate-600">
                    {formatTime(ev.timestamp)}
                  </span>
                  <span
                    className={`text-[7px] font-bold font-mono px-1 rounded ${style.text} ${style.bg} border border-current/20`}
                  >
                    {LEVEL_LABEL[ev.level]}
                  </span>
                  <span className="text-[8px] font-mono text-slate-500">
                    {ev.category}
                  </span>
                </div>
                <p className="text-[10px] font-mono text-slate-300 mt-0.5 leading-relaxed">
                  {ev.title}
                </p>
                {ev.detail && (
                  <p className="text-[8px] font-mono text-slate-500 mt-0.5 line-clamp-2">
                    {ev.detail}
                  </p>
                )}
                {ev.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {ev.tags.map((tag) => (
                      <span
                        key={tag}
                        className="text-[7px] font-mono text-slate-600 bg-slate-800/50 px-1 rounded"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LayerDescription({ layer }: { layer: string }) {
  const desc =
    layer === 'supervisor'
      ? '编排周期执行，调度子 Agent，汇总结果。负责整体流程控制和异常恢复。'
      : layer === 'data'
        ? '摄取市场数据、新闻和链上数据源。过滤并标准化输入数据供下游 Agent 消费。'
        : layer === 'signal'
          ? '将多源数据合成为交易信号，附带优势估计（edge）和置信度评分。'
          : layer === 'risk'
            ? '根据风险限额、市场状态和持仓规模规则审查信号，决定 approve/reject。'
            : layer === 'execution'
              ? '分配资金，确定头寸规模，执行交易（当前为模拟执行 dry-run）。'
              : layer === 'learning'
                ? '收集周期结果，更新模型权重，优化策略参数，实现持续学习。'
                : '未知层级'

  return (
    <div className="rounded-lg border border-white/[0.04] bg-slate-800/20 p-3">
      <span className="text-[9px] font-bold font-mono text-slate-400 uppercase tracking-wider">
        层级职责
      </span>
      <p className="text-[10px] font-mono text-slate-500 mt-1.5 leading-relaxed">{desc}</p>
    </div>
  )
}

// Re-export LogEvent for convenience
export type { LogEvent, LogLevel }