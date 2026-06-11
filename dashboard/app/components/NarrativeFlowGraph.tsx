'use client'

import { useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowDown, GitBranch, Sparkles } from 'lucide-react'
import type { NarrativeItem } from '../lib/runtimeNarrative'
import type { Incident } from '../hooks/useIncidents'
import type { LogEvent } from '../hooks/useLogEvents'
import type { DashboardKpis } from '../hooks/useDashboardSummary'

// ── Types ─────────────────────────────────────────────────

interface Props {
  narratives: NarrativeItem[]
  incidents: Incident[]
  events: LogEvent[]
  kpis: DashboardKpis | null
  hasHighVol: boolean
  isHighCorrelation: boolean
  truthBadge?: React.ReactNode
}

interface FlowNode {
  id: string
  label: string
  detail: string
  level: number
  source: 'market' | 'regime' | 'risk' | 'system' | 'recovery'
  connectedFrom: string | null
}

// ── Color Map ─────────────────────────────────────────────

const sourceColors = {
  market: {
    dot: 'bg-violet-400',
    border: 'border-violet-500/40',
    bg: 'bg-violet-500/5',
    text: 'text-violet-400',
    glow: 'shadow-[0_0_12px_rgba(167,139,250,0.3)]',
  },
  regime: {
    dot: 'bg-indigo-400',
    border: 'border-indigo-500/40',
    bg: 'bg-indigo-500/5',
    text: 'text-indigo-400',
    glow: 'shadow-[0_0_12px_rgba(129,140,248,0.3)]',
  },
  risk: {
    dot: 'bg-amber-400',
    border: 'border-amber-500/40',
    bg: 'bg-amber-500/5',
    text: 'text-amber-400',
    glow: 'shadow-[0_0_12px_rgba(251,191,36,0.3)]',
  },
  system: {
    dot: 'bg-cyan-400',
    border: 'border-cyan-500/40',
    bg: 'bg-cyan-500/5',
    text: 'text-cyan-400',
    glow: 'shadow-[0_0_12px_rgba(34,211,238,0.3)]',
  },
  recovery: {
    dot: 'bg-emerald-400',
    border: 'border-emerald-500/40',
    bg: 'bg-emerald-500/5',
    text: 'text-emerald-400',
    glow: 'shadow-[0_0_12px_rgba(52,211,153,0.3)]',
  },
}

// ── Flow derivation from runtime data ─────────────────────

function deriveNarrativeFlow(
  narratives: NarrativeItem[],
  incidents: Incident[],
  events: LogEvent[],
  kpis: DashboardKpis | null,
  hasHighVol: boolean,
  isHighCorrelation: boolean,
): FlowNode[] {
  const nodes: FlowNode[] = []

  // ── Level 0: Market trigger ────────────────────────────
  if (hasHighVol || isHighCorrelation) {
    const triggers: string[] = []
    if (hasHighVol) triggers.push('市场波动率上升')
    if (isHighCorrelation) triggers.push('多市场相关性增强')
    nodes.push({
      id: 'market-trigger',
      label: triggers.join(' / '),
      detail: hasHighVol && isHighCorrelation
        ? '波动率突破基准区间，跨市场联动增强，组合分散效应下降'
        : hasHighVol
          ? '波动率攀升至异常水平，资产定价不确定性增加'
          : '资产间相关度上升，尾部风险概率提升',
      level: 0,
      source: 'market',
      connectedFrom: null,
    })
  }

  // ── Level 1: Regime shift ──────────────────────────────
  const regime = kpis?.regime ?? ''
  if (regime || hasHighVol || isHighCorrelation) {
    nodes.push({
      id: 'regime-shift',
      label: hasHighVol ? '体制切换至防御模式' : isHighCorrelation ? '风险关联体制激活' : '市场体制评估更新',
      detail: hasHighVol
        ? '系统检测到高波动信号，自动切换至审慎风险体制'
        : isHighCorrelation
          ? '高相关度触发风险关联体制，组合分散化参数调整'
          : `当前市场体制：${regime || '标准模式'}`,
      level: 1,
      source: 'regime',
      connectedFrom: nodes.length > 0 ? nodes[nodes.length - 1].id : null,
    })
  }

  // ── Level 2: Risk control response ─────────────────────
  const approvalRate = kpis && kpis.totalSignals > 0
    ? Math.round((kpis.approvedSignals / kpis.totalSignals) * 100)
    : 100
  const rejectionRate = 100 - approvalRate

  if (hasHighVol || isHighCorrelation || approvalRate < 85) {
    const label = hasHighVol
      ? '风险控制模块收紧敞口'
      : isHighCorrelation
        ? '集中度风险对冲激活'
        : '审批阈值自动上调'

    const detail = hasHighVol
      ? `高波动策略暴露自动降低，信号审批标准上调至严格区间。当前通过率 ${approvalRate}%`
      : isHighCorrelation
        ? `相关性对冲参数调整，跨市场净敞口收缩。风险预算再分配执行中`
        : `审批通过率 ${approvalRate}%，${rejectionRate}% 信号被风控拦截。系统优先保障资金安全`

    nodes.push({
      id: 'risk-response',
      label,
      detail,
      level: 2,
      source: 'risk',
      connectedFrom: nodes.length > 0 ? nodes[nodes.length - 1].id : null,
    })
  }

  // ── Level 3: System action ─────────────────────────────
  const activeIncidents = incidents.filter((i) => !i.resolvedTime)
  const errorCount = kpis?.errorCount ?? 0
  const reconnectCount = kpis?.reconnects ?? 0

  const systemActions: string[] = []
  if (approvalRate < 70) systemActions.push('拒绝率增加')
  if (reconnectCount > 0) systemActions.push('自动重连机制触发')
  if (errorCount > 0) systemActions.push('错误隔离激活')
  if (activeIncidents.length > 0) systemActions.push('事故响应流程启动')

  if (systemActions.length > 0) {
    nodes.push({
      id: 'system-action',
      label: systemActions[0] + (systemActions.length > 1 ? ` (+${systemActions.length - 1} 项响应)` : ''),
      detail: systemActions.length > 1
        ? systemActions.join('、') + '等系统自动响应已激活'
        : systemActions[0],
      level: 3,
      source: 'system',
      connectedFrom: nodes.length > 0 ? nodes[nodes.length - 1].id : null,
    })
  } else if (nodes.length > 0) {
    nodes.push({
      id: 'system-stable',
      label: '系统维持标准运行参数',
      detail: '无异常响应触发，所有子系统正常运行。Agent 集群处于事件驱动待命状态',
      level: 3,
      source: 'system',
      connectedFrom: nodes[nodes.length - 1].id,
    })
  }

  // ── Level 4: Recovery / Resolution ─────────────────────
  const recoveryEvents = events.filter(
    (e) => e.category === 'recovery' || e.title.toLowerCase().includes('recover'),
  )
  const resolvedIncidents = incidents.filter((i) => i.resolvedTime)

  if (recoveryEvents.length > 0 || resolvedIncidents.length > 0) {
    nodes.push({
      id: 'recovery',
      label: '系统自动恢复',
      detail: resolvedIncidents.length > 0
        ? `${resolvedIncidents.length} 起事故已自动恢复，恢复流程完整。系统回归正常运行状态`
        : `${recoveryEvents.length} 次自动恢复执行，系统自愈机制生效`,
      level: nodes.length > 0 ? nodes[nodes.length - 1].level + 1 : 4,
      source: 'recovery',
      connectedFrom: nodes.length > 0 ? nodes[nodes.length - 1].id : null,
    })
  }

  // ── Map narrative items that have priority info ─────────
  const criticalNarratives = narratives.filter((n) => n.priority === 'critical')
  if (criticalNarratives.length > 0 && nodes.length > 0) {
    nodes.push({
      id: 'narrative-alert',
      label: `关键叙事：${criticalNarratives[0].headline.slice(0, 30)}`,
      detail: criticalNarratives[0].detail || criticalNarratives[0].headline,
      level: nodes[nodes.length - 1].level + 0.5,
      source: 'risk',
      connectedFrom: nodes[nodes.length - 1].id,
    })
  }

  return nodes
}

// ── Flow Node Sub-Component ───────────────────────────────

function FlowNodeComponent({
  node,
  isFirst,
  index,
}: {
  node: FlowNode
  isFirst: boolean
  isLast: boolean
  index: number
}) {
  const cs = sourceColors[node.source]

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.15, duration: 0.5, ease: 'easeOut' }}
      className="relative"
    >
      {/* Connector from previous */}
      {!isFirst && (
        <div className="flex justify-center mb-1">
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 24, opacity: 1 }}
            transition={{ delay: index * 0.15 + 0.2, duration: 0.4 }}
            className="w-px bg-gradient-to-b from-indigo-500/40 to-transparent"
          />
          <motion.div
            initial={{ y: -10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: index * 0.15 + 0.3, duration: 0.3 }}
            className="absolute -mt-0.5"
          >
            <ArrowDown className="w-3 h-3 text-indigo-400/60" />
          </motion.div>
        </div>
      )}

      {/* Node card */}
      <motion.div
        className={`rounded-xl border ${cs.border} ${cs.bg} p-4 backdrop-blur-sm ${cs.glow} transition-shadow duration-500`}
        whileHover={{ scale: 1.02 }}
        transition={{ duration: 0.2 }}
      >
        <div className="flex items-start gap-3">
          {/* Source indicator */}
          <div className={`mt-0.5 w-3 h-3 rounded-full ${cs.dot} flex-shrink-0`} />

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-[11px] font-bold ${cs.text} tracking-wide`}>
                {node.label}
              </span>
              <span className="text-[8px] font-mono text-slate-600 uppercase">
                {node.source === 'market' ? '市场驱动' :
                 node.source === 'regime' ? '体制响应' :
                 node.source === 'risk' ? '风险控制' :
                 node.source === 'system' ? '系统动作' : '自动恢复'}
              </span>
            </div>
            <p className="text-[10px] font-mono text-slate-500 leading-relaxed">
              {node.detail}
            </p>
          </div>

          {/* Glow effect on right edge */}
          <div className={`w-1 h-full absolute right-0 top-0 rounded-r-xl bg-gradient-to-l ${cs.dot} opacity-20`} />
        </div>
      </motion.div>
    </motion.div>
  )
}

// ── Main Component ────────────────────────────────────────

export default function NarrativeFlowGraph({
  narratives,
  incidents,
  events,
  kpis,
  hasHighVol,
  isHighCorrelation,
  truthBadge,
}: Props) {
  const flowNodes = useMemo(
    () => deriveNarrativeFlow(narratives, incidents, events, kpis, hasHighVol, isHighCorrelation),
    [narratives, incidents, events, kpis, hasHighVol, isHighCorrelation],
  )

  if (flowNodes.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-700/30 bg-gradient-to-b from-slate-800/60 to-slate-900/60 backdrop-blur-sm p-6">
        <div className="flex items-center gap-3 mb-4">
          <GitBranch className="w-5 h-5 text-slate-500" />
          <h3 className="text-sm font-bold text-slate-200 tracking-wide">AI 决策因果链</h3>
        </div>
        <p className="text-xs font-mono text-slate-500">系统运行平稳，暂无因果链触发。</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-slate-700/30 bg-gradient-to-b from-slate-800/60 to-slate-900/60 backdrop-blur-sm p-6 relative">
      {truthBadge && <div className="absolute top-3 right-3 z-10">{truthBadge}</div>}
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
            <GitBranch className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200 tracking-wide">AI 决策因果链</h3>
            <p className="text-[9px] font-mono text-slate-500">Narrative Flow · 事件因果推导</p>
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-indigo-500/20 bg-indigo-500/5 text-[10px] font-mono text-indigo-400">
          <Sparkles className="w-3 h-3" />
          <span>实时推导</span>
        </div>
      </div>

      {/* Flow nodes */}
      <div className="max-w-2xl mx-auto">
        <AnimatePresence>
          {flowNodes.map((node, idx) => (
            <FlowNodeComponent
              key={node.id}
              node={node}
              isFirst={idx === 0}
              isLast={idx === flowNodes.length - 1}
              index={idx}
            />
          ))}
        </AnimatePresence>

        {/* Terminal glow at bottom */}
        {flowNodes.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: flowNodes.length * 0.15 + 0.3 }}
            className="flex justify-center mt-2 mb-1"
          >
            <div className="w-2 h-2 rounded-full bg-emerald-400/60 shadow-[0_0_12px_rgba(52,211,153,0.4)]" />
          </motion.div>
        )}
      </div>

      {/* Legend */}
      <div className="mt-6 pt-4 border-t border-slate-700/20 flex items-center gap-3 text-[8px] font-mono text-slate-600">
        <span className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-full bg-violet-400" /> 市场驱动
        </span>
        <span className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-full bg-indigo-400" /> 体制响应
        </span>
        <span className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-full bg-amber-400" /> 风险控制
        </span>
        <span className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-full bg-cyan-400" /> 系统动作
        </span>
        <span className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-full bg-emerald-400" /> 自动恢复
        </span>
        <span className="ml-auto text-slate-600">因果链从运行时事件、叙事和事故数据自动推导</span>
      </div>
    </div>
  )
}
