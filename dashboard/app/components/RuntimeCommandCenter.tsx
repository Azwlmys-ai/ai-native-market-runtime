'use client'

import { useMemo, useState, useCallback } from 'react'
import type { LogEvent, LogLevel } from '../hooks/useLogEvents'

// ── Types ─────────────────────────────────────────────────

export interface AgentInfo {
  id: string
  name: string
  layer: string
}

interface Props {
  // Level filter
  levelFilter: LogLevel | 'ALL'
  onLevelFilterChange: (level: LogLevel | 'ALL') => void

  // Agent filter
  agentFilter: string | null
  onAgentFilterChange: (agentId: string | null) => void

  // Category multi-select filter
  categoryFilters: string[]
  onCategoryFilterChange: (categories: string[]) => void

  // Search
  searchQuery: string
  onSearchQueryChange: (query: string) => void

  // View mode
  runtimeViewMode: 'ops' | 'executive'
  onRuntimeViewModeChange: (mode: 'ops' | 'executive') => void

  // Context for AI suggestions
  filteredEvents: LogEvent[]
  source: 'real' | 'fallback'

  // Agent chips
  agents: AgentInfo[]
  onSelectAgent: (id: string | null) => void
}

// ── Constants ─────────────────────────────────────────────

const LEVEL_OPTIONS: { value: LogLevel | 'ALL'; label: string; color: string }[] = [
  { value: 'ALL', label: '全部', color: 'text-slate-400 border-slate-500/30 bg-slate-500/10' },
  { value: 'ERROR', label: '错误', color: 'text-red-400 border-red-500/30 bg-red-500/10' },
  { value: 'WARN', label: '警告', color: 'text-amber-400 border-amber-500/30 bg-amber-500/10' },
  { value: 'SUCCESS', label: '成功', color: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' },
  { value: 'INFO', label: '信息', color: 'text-sky-400 border-sky-500/30 bg-sky-500/10' },
]

const CATEGORY_OPTIONS = [
  { value: 'error', label: '错误/超时' },
  { value: 'stoploss', label: '止损保护' },
  { value: 'drawdown', label: '回撤警告' },
  { value: 'recovery', label: '系统恢复' },
  { value: 'connection', label: '连接事件' },
  { value: 'signal', label: '信号决策' },
  { value: 'cycle', label: '周期汇总' },
]

const AGENT_COLORS: Record<string, string> = {
  orchestrator: 'border-indigo-500/30 bg-indigo-500/10 text-indigo-400',
  agent_b: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-400',
  agent_m: 'border-violet-500/30 bg-violet-500/10 text-violet-400',
  risk: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
  execution: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
}

// ── AI Suggested Actions Engine ───────────────────────────

interface AiSuggestion {
  riskLevel: 'low' | 'medium' | 'high' | 'critical'
  riskLabel: string
  watchAgent: string | null
  direction: string
  dangerModule: string | null
  details: string[]
}

function generateAiSuggestions(
  events: LogEvent[],
  source: 'real' | 'fallback',
): AiSuggestion | null {
  if (events.length === 0) return null

  // Count categories and levels
  const cats = new Map<string, number>()
  const levels = new Map<LogLevel, number>()
  const agents = new Map<string, number>()

  for (const ev of events) {
    cats.set(ev.category, (cats.get(ev.category) ?? 0) + 1)
    levels.set(ev.level, (levels.get(ev.level) ?? 0) + 1)
    agents.set(ev.agent.toLowerCase(), (agents.get(ev.agent.toLowerCase()) ?? 0) + 1)
  }

  const errorCount = levels.get('ERROR') ?? 0
  const warnCount = levels.get('WARN') ?? 0
  const successCount = levels.get('SUCCESS') ?? 0
  const stoplossCount = cats.get('stoploss') ?? 0
  const drawdownCount = cats.get('drawdown') ?? 0
  const connectionCount = cats.get('connection') ?? 0
  const recoveryCount = cats.get('recovery') ?? 0
  const totalEvents = events.length

  // Find most active agent by event count
  let mostActiveAgent: string | null = null
  let maxAgentEvents = 0
  for (const [name, count] of agents) {
    if (count > maxAgentEvents) {
      maxAgentEvents = count
      mostActiveAgent = name
    }
  }

  // ── Priority: error > stoploss > drawdown > connection > normal ──

  // Critical: many errors
  if (errorCount >= 5) {
    return {
      riskLevel: 'critical',
      riskLabel: '严重',
      watchAgent: mostActiveAgent,
      direction: '建议重点排查 LLM Provider latency 与 API 限流状态',
      dangerModule: 'LLM Provider / Network',
      details: [
        `最近 ${events.length} 条事件中检测到 ${errorCount} 次错误`,
        '错误频率偏高，可能存在 Provider 降级或网络中断',
        '建议启用备用 Provider · 检查 API 配额 · 降低并发请求数',
        mostActiveAgent ? `重点关注 Agent: ${mostActiveAgent}` : null,
      ].filter(Boolean) as string[],
    }
  }

  // High: many errors but fewer
  if (errorCount >= 2) {
    return {
      riskLevel: 'high',
      riskLabel: '高',
      watchAgent: mostActiveAgent,
      direction: '建议检查 LLM Provider 延迟和请求成功率',
      dangerModule: 'LLM Provider',
      details: [
        `检测到 ${errorCount} 次错误 / ${warnCount} 次警告`,
        '建议观察后续周期是否持续复现',
        '检查 API 响应时间 · 确认 rate limit 状态',
        source === 'real' ? '正在读取真实运行日志' : null,
      ].filter(Boolean) as string[],
    }
  }

  // High: drawdown
  if (drawdownCount >= 1) {
    return {
      riskLevel: 'high',
      riskLabel: '高',
      watchAgent: 'risk',
      direction: '建议降低高风险策略权重，审查当前持仓组合',
      dangerModule: '风险敞口 / 持仓管理',
      details: [
        `检测到 ${drawdownCount} 次回撤警告`,
        '账户净值出现下降趋势',
        '暂停新开仓 · 审查现有持仓 · 检查资金费率变化',
        '建议收紧单笔仓位上限',
      ],
    }
  }

  // Medium: many warnings
  if (warnCount >= 3) {
    return {
      riskLevel: 'medium',
      riskLabel: '中',
      watchAgent: mostActiveAgent,
      direction: '系统运行存在不稳定因素，建议检查 WS 连接与信号拒绝率',
      dangerModule: 'WS 连接 / 信号管道',
      details: [
        `检测到 ${warnCount} 次警告事件`,
        '警告事件累积可能预示系统不稳定',
        '检查 WebSocket 连接状态 · 审查最近拒绝的信号',
        '确认链上数据延迟是否在可接受范围',
      ],
    }
  }

  // Medium: connection issues
  if (connectionCount >= 2) {
    return {
      riskLevel: 'medium',
      riskLabel: '中',
      watchAgent: 'orchestrator',
      direction: '建议检查交易所 WS 连接稳定性，考虑切换接入点',
      dangerModule: '交易所 WS 连接',
      details: [
        `检测到 ${connectionCount} 次连接事件（断开/重连）`,
        'WS 连接不稳定可能影响实时数据获取',
        '自动重连已启用 · 检查网络延迟 · 确认交易所 API 状态',
      ],
    }
  }

  // Medium: stoploss
  if (stoplossCount >= 1) {
    return {
      riskLevel: 'medium',
      riskLabel: '中',
      watchAgent: 'risk',
      direction: '风控保护已触发，建议审查止损参数与市场波动率',
      dangerModule: '风控 / 止损机制',
      details: [
        `检测到 ${stoplossCount} 次止损触发`,
        '止损触发表明市场波动超出阈值',
        '审查止损参数配置 · 检查市场波动率 · 确认仓位计算正确',
      ],
    }
  }

  // Low: recovery
  if (recoveryCount >= 1) {
    return {
      riskLevel: 'low',
      riskLabel: '低',
      watchAgent: null,
      direction: '系统已自动完成恢复，当前运行正常',
      dangerModule: null,
      details: [
        `检测到 ${recoveryCount} 次系统自愈事件`,
        '系统从异常状态自动恢复，无需人工介入',
        '所有组件运行正常 · 继续观察后续周期',
      ],
    }
  }

  // Low: all good
  if (successCount >= 3 && errorCount === 0 && warnCount === 0) {
    return {
      riskLevel: 'low',
      riskLabel: '低',
      watchAgent: null,
      direction: '系统运行正常，持续产出高质量交易信号',
      dangerModule: null,
      details: [
        `最近 ${totalEvents} 条事件全部正常`,
        '未检测到错误或警告',
        '所有 Agent 协同工作正常 · 无需调整',
        source === 'real' ? '✅ 正在读取真实运行数据' : null,
      ].filter(Boolean) as string[],
    }
  }

  // Fallback: no clear pattern
  return {
    riskLevel: 'low',
    riskLabel: '低',
    watchAgent: mostActiveAgent,
    direction: '当前无明显异常，建议保持观察',
    dangerModule: null,
    details: [
      `${successCount} 成功 · ${errorCount} 错误 · ${warnCount} 警告`,
      '事件分布正常，未触发关键告警阈值',
    ],
  }
}

// ── Helpers ───────────────────────────────────────────────

function riskStyle(level: AiSuggestion['riskLevel']): string {
  switch (level) {
    case 'critical': return 'border-red-500/60 bg-red-500/10 text-red-400'
    case 'high': return 'border-amber-500/60 bg-amber-500/10 text-amber-400'
    case 'medium': return 'border-yellow-500/50 bg-yellow-500/10 text-yellow-400'
    case 'low': return 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400'
  }
}

// ── Sub-components ────────────────────────────────────────

function FilterChip({
  label,
  active,
  onClick,
  colorClass,
}: {
  label: string
  active: boolean
  onClick: () => void
  colorClass: string
}) {
  return (
    <button
      onClick={onClick}
      className={`text-[10px] font-mono px-2 py-0.5 rounded border transition-all ${
        active
          ? `${colorClass} shadow-[0_0_8px_rgba(34,211,238,0.15)]`
          : 'text-slate-500 border-slate-700/40 hover:border-slate-500/50 hover:text-slate-400'
      }`}
    >
      {label}
    </button>
  )
}

function CategoryChip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`text-[9px] font-mono px-1.5 py-0.5 rounded border transition-all ${
        active
          ? 'text-cyan-400 border-cyan-500/40 bg-cyan-500/10 shadow-[0_0_6px_rgba(34,211,238,0.12)]'
          : 'text-slate-600 border-slate-700/30 hover:border-slate-600/40 hover:text-slate-500'
      }`}
    >
      {label}
    </button>
  )
}

function AgentChip({
  agent,
  active,
  onClick,
}: {
  agent: AgentInfo
  active: boolean
  onClick: () => void
}) {
  const color = AGENT_COLORS[agent.id.toLowerCase()] ?? 'border-slate-500/30 bg-slate-500/10 text-slate-400'
  return (
    <button
      onClick={onClick}
      className={`text-[9px] font-mono px-1.5 py-0.5 rounded border transition-all ${
        active
          ? `${color} shadow-[0_0_8px_rgba(34,211,238,0.15)]`
          : 'text-slate-500 border-slate-700/30 hover:border-slate-600/40 hover:text-slate-400'
      }`}
    >
      {agent.name}
    </button>
  )
}

// ── Main Component ────────────────────────────────────────

export default function RuntimeCommandCenter({
  levelFilter,
  onLevelFilterChange,
  agentFilter,
  onAgentFilterChange,
  categoryFilters,
  onCategoryFilterChange,
  searchQuery,
  onSearchQueryChange,
  runtimeViewMode,
  onRuntimeViewModeChange,
  filteredEvents,
  source,
  agents,
  onSelectAgent,
}: Props) {
  const [expanded, setExpanded] = useState(true)

  // Toggle category filter
  const toggleCategory = useCallback(
    (cat: string) => {
      if (categoryFilters.includes(cat)) {
        onCategoryFilterChange(categoryFilters.filter((c) => c !== cat))
      } else {
        onCategoryFilterChange([...categoryFilters, cat])
      }
    },
    [categoryFilters, onCategoryFilterChange],
  )

  // AI suggestions
  const aiSuggestion = useMemo(
    () => generateAiSuggestions(filteredEvents.slice(0, 50), source),
    [filteredEvents, source],
  )

  // Stats
  const stats = useMemo(() => {
    const allLevels: LogLevel[] = ['ERROR', 'WARN', 'SUCCESS', 'INFO']
    const counts: Record<string, number> = { ERROR: 0, WARN: 0, SUCCESS: 0, INFO: 0 }
    for (const ev of filteredEvents) {
      counts[ev.level] = (counts[ev.level] ?? 0) + 1
    }
    return { total: filteredEvents.length, counts, allLevels }
  }, [filteredEvents])

  return (
    <div className="flex-shrink-0 border-b border-white/[0.04] bg-slate-900/60">
      {/* Header Row */}
      <div className="flex items-center justify-between px-4 py-1.5">
        <div className="flex items-center gap-2">
          {/* Collapse toggle */}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-[8px] font-mono text-slate-500 hover:text-cyan-400 transition-colors"
          >
            {expanded ? '▲' : '▼'}
          </button>

          <span className="text-[10px] font-bold font-mono text-slate-400 uppercase tracking-widest">
            指挥中心
          </span>
          <span className="text-[8px] font-mono text-cyan-400 bg-cyan-500/10 px-1.5 py-0.5 rounded border border-cyan-500/20">
            CMD CENTER
          </span>

          {/* Level stats */}
          <div className="flex items-center gap-1 ml-2">
            {stats.allLevels.map((lvl) => {
              const count = stats.counts[lvl]
              if (count === 0) return null
              const color =
                lvl === 'ERROR'
                  ? 'text-red-400'
                  : lvl === 'WARN'
                    ? 'text-amber-400'
                    : lvl === 'SUCCESS'
                      ? 'text-emerald-400'
                      : 'text-sky-400'
              return (
                <span key={lvl} className={`text-[8px] font-mono ${color}`}>
                  {count}
                  <span className="text-slate-600 ml-0.5">{lvl}</span>
                </span>
              )
            })}
            {stats.counts.ERROR > 0 && (
              <span className="text-[7px] font-bold font-mono text-red-400 bg-red-500/10 border border-red-500/20 px-1 rounded animate-pulse">
                告警
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Source badge */}
          <span
            className={`text-[8px] font-bold font-mono px-1.5 py-0.5 rounded border ${
              source === 'real'
                ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
                : 'text-amber-400 bg-amber-500/10 border-amber-500/30'
            }`}
          >
            {source === 'real' ? 'REAL' : 'FALLBACK'}
          </span>

          {/* View mode toggle */}
          <div className="flex items-center rounded border border-cyan-500/20 overflow-hidden">
            <button
              onClick={() => onRuntimeViewModeChange('ops')}
              className={`text-[9px] font-mono px-2 py-0.5 transition-colors ${
                runtimeViewMode === 'ops'
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'text-slate-600 hover:text-slate-400'
              }`}
            >
              Runtime Ops
            </button>
            <button
              onClick={() => onRuntimeViewModeChange('executive')}
              className={`text-[9px] font-mono px-2 py-0.5 transition-colors border-l border-cyan-500/20 ${
                runtimeViewMode === 'executive'
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'text-slate-600 hover:text-slate-400'
              }`}
            >
              Exec View
            </button>
          </div>
        </div>
      </div>

      {/* Expanded Content */}
      {expanded && (
        <div className="px-4 pb-2 space-y-2">
          {/* Row 1: Level Filter + Search */}
          <div className="flex items-center gap-3">
            {/* Level Filter */}
            <div className="flex items-center gap-1">
              <span className="text-[8px] font-mono text-slate-600 mr-1">级别</span>
              {LEVEL_OPTIONS.map((opt) => (
                <FilterChip
                  key={opt.value}
                  label={opt.label}
                  active={levelFilter === opt.value}
                  onClick={() => onLevelFilterChange(opt.value)}
                  colorClass={opt.color}
                />
              ))}
            </div>

            {/* Separator */}
            <div className="w-px h-4 bg-white/[0.06]" />

            {/* Agent Filter */}
            <div className="flex items-center gap-1">
              <span className="text-[8px] font-mono text-slate-600 mr-1">Agent</span>
              <AgentChip
                agent={{ id: '__all__', name: '全部', layer: '' }}
                active={agentFilter === null}
                onClick={() => onAgentFilterChange(null)}
              />
              {agents.map((a) => (
                <AgentChip
                  key={a.id}
                  agent={a}
                  active={agentFilter === a.id}
                  onClick={() => {
                    if (agentFilter === a.id) {
                      onAgentFilterChange(null)
                      onSelectAgent(null)
                    } else {
                      onAgentFilterChange(a.id)
                      onSelectAgent(a.id)
                    }
                  }}
                />
              ))}
            </div>

            {/* Separator */}
            <div className="w-px h-4 bg-white/[0.06]" />

            {/* Search */}
            <div className="relative flex-1 max-w-xs">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => onSearchQueryChange(e.target.value)}
                placeholder="搜索事件..."
                className="w-full bg-slate-800/50 border border-slate-700/50 rounded text-[10px] font-mono text-slate-300 px-2 py-1 outline-none focus:border-cyan-500/50 focus:bg-slate-800/80 transition-colors placeholder:text-slate-600"
              />
              {searchQuery && (
                <button
                  onClick={() => onSearchQueryChange('')}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 text-[8px] text-slate-500 hover:text-cyan-400"
                >
                  ✕
                </button>
              )}
            </div>
          </div>

          {/* Row 2: Category Filter */}
          <div className="flex items-center gap-1">
            <span className="text-[8px] font-mono text-slate-600 mr-1">分类</span>
            {CATEGORY_OPTIONS.map((cat) => (
              <CategoryChip
                key={cat.value}
                label={cat.label}
                active={categoryFilters.includes(cat.value)}
                onClick={() => toggleCategory(cat.value)}
              />
            ))}
            {categoryFilters.length > 0 && (
              <button
                onClick={() => onCategoryFilterChange([])}
                className="text-[7px] font-mono text-slate-500 hover:text-cyan-400 ml-1"
              >
                清除
              </button>
            )}
          </div>

          {/* Row 3: AI Suggested Actions */}
          {aiSuggestion && (
            <div
              className={`rounded-lg border p-2.5 ${riskStyle(aiSuggestion.riskLevel)} bg-opacity-10`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                <span className="text-[10px] font-bold font-mono uppercase tracking-wider">
                  AI 指挥建议
                </span>
                <span
                  className={`text-[8px] font-bold font-mono px-1.5 py-0.5 rounded border ${riskStyle(aiSuggestion.riskLevel)}`}
                >
                  风险: {aiSuggestion.riskLabel}
                </span>
                {aiSuggestion.watchAgent && (
                  <span className="text-[8px] font-mono text-slate-500 ml-1">
                    👁 关注: <span className="text-cyan-400">{aiSuggestion.watchAgent}</span>
                  </span>
                )}
              </div>
              <p className="text-[10px] font-mono font-bold text-white mb-1.5">
                {aiSuggestion.direction}
              </p>
              {aiSuggestion.dangerModule && (
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span className="text-[8px] font-mono text-slate-500">⚠ 危险模块</span>
                  <span className="text-[9px] font-mono text-red-400 bg-red-500/10 border border-red-500/20 px-1.5 py-0.5 rounded">
                    {aiSuggestion.dangerModule}
                  </span>
                </div>
              )}
              <div className="space-y-0.5 mt-1.5 pt-1.5 border-t border-current/20">
                {aiSuggestion.details.map((d, i) => (
                  <p key={i} className="text-[9px] font-mono text-slate-300">
                    ▸ {d}
                  </p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}