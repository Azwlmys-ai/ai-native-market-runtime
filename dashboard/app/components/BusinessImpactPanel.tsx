'use client'

import { useMemo } from 'react'
import { TrendingUp, TrendingDown, ShieldCheck, Zap, Clock, RotateCcw, Users } from 'lucide-react'
import type { DashboardKpis } from '../hooks/useDashboardSummary'
import type { Incident } from '../hooks/useIncidents'
import type { LogEvent } from '../hooks/useLogEvents'

// ── Types ─────────────────────────────────────────────────

interface Props {
  kpis: DashboardKpis | null
  incidents: Incident[]
  events: LogEvent[]
  truthBadge?: React.ReactNode
}

interface ImpactMetric {
  id: string
  label: string
  value: string
  trend: 'up' | 'down' | 'stable'
  trendLabel: string
  explanation: string
  icon: React.ReactNode
  color: 'emerald' | 'cyan' | 'amber' | 'violet'
}

// ── Helpers ───────────────────────────────────────────────

function safeDiv(a: number, b: number): number {
  return b > 0 ? a / b : 0
}

// ── Business Impact derivation from runtime data ──────────

function deriveBusinessImpact(
  kpis: DashboardKpis | null,
  incidents: Incident[],
  events: LogEvent[],
): ImpactMetric[] {
  // ── 1. 避免潜在亏损 ──────────────────────────────────
  // Derived from: rejected signals × estimated avg signal exposure
  // Conservative estimation: each rejected signal prevents ~$50-$200 potential loss
  const rejectedSignals = kpis?.rejectedSignals ?? 0
  const totalSignals = kpis?.totalSignals ?? 0
  const rejectionRate = safeDiv(rejectedSignals, totalSignals) * 100

  // Heuristic: each rejection prevents estimated loss based on market conditions
  // High rejection rate → tighter market → smaller per-signal loss
  const estimatedLossPerSignal = rejectionRate > 50 ? 80 : rejectionRate > 30 ? 120 : 180
  const avoidedLoss = rejectedSignals * estimatedLossPerSignal
  const avoidedLossFormatted =
    avoidedLoss >= 1000
      ? `$${(avoidedLoss / 1000).toFixed(1)}K`
      : `$${avoidedLoss}`

  const avoidedLossTrend: 'up' | 'down' | 'stable' =
    rejectionRate > 40 ? 'up' : rejectionRate > 20 ? 'stable' : 'down'

  // ── 2. AI 自动审批次数 ────────────────────────────────
  const approvedSignals = kpis?.approvedSignals ?? 0
  const autoApprovalRate = safeDiv(approvedSignals, totalSignals) * 100

  const autoApprovalTrend: 'up' | 'down' | 'stable' =
    autoApprovalRate >= 85 ? 'up' : autoApprovalRate >= 50 ? 'stable' : 'down'

  // ── 3. 自动化节省工时 ──────────────────────────────────
  // Each auto-approved signal saves ~5-15 minutes of manual review
  // Each auto-recovery saves ~10-30 minutes of ops intervention
  const savedMinutesPerSignal = 8
  const totalSavedMinutes = approvedSignals * savedMinutesPerSignal

  const recoveryEvents = events.filter(
    (e) => e.category === 'recovery' || e.title.toLowerCase().includes('recover'),
  ).length
  const totalSavedMinutesWithRecovery = totalSavedMinutes + recoveryEvents * 15

  const savedHours = totalSavedMinutesWithRecovery / 60
  const savedHoursFormatted =
    savedHours >= 1 ? `${savedHours.toFixed(1)} 小时` : `${Math.round(totalSavedMinutesWithRecovery)} 分钟`

  const savedTrend: 'up' | 'down' | 'stable' =
    approvedSignals > 5 ? 'up' : approvedSignals > 2 ? 'stable' : 'down'

  // ── 4. 风险升级阻止次数 ────────────────────────────────
  // Incidents that were resolved without reaching critical
  const resolvedIncidents = incidents.filter((i) => i.resolvedTime)
  const preventedEscalations = resolvedIncidents.filter(
    (i) => i.severity !== 'critical' && i.severity !== 'high',
  ).length
  const activeIncidents = incidents.filter((i) => !i.resolvedTime).length

  const escalationTrend: 'up' | 'down' | 'stable' =
    activeIncidents === 0 ? 'up' : activeIncidents < 2 ? 'stable' : 'down'

  // ── 5. 自动恢复次数 ────────────────────────────────────
  const autoRecoveries =
    recoveryEvents +
    events.filter((e) => e.title.toLowerCase().includes('fallback')).length +
    events.filter((e) => e.title.toLowerCase().includes('retry')).length

  const recoveryTrend: 'up' | 'down' | 'stable' =
    autoRecoveries > 3 ? 'up' : autoRecoveries > 0 ? 'stable' : 'down'

  // ── 6. 多 Agent 协同效率 ────────────────────────────────
  const totalAgents = kpis?.activeAgents ?? 0
  const errorCount = kpis?.errorCount ?? 0
  const healthScore = kpis?.healthScore ?? 100

  const collaborationEfficiency =
    totalAgents > 0 && errorCount === 0
      ? '高效协同'
      : errorCount <= 2
        ? '正常运行'
        : '轻微波动'

  const collabTrend: 'up' | 'down' | 'stable' =
    healthScore >= 95 ? 'up' : healthScore >= 80 ? 'stable' : 'down'

  return [
    {
      id: 'avoided-loss',
      label: '避免潜在亏损',
      value: avoidedLossFormatted,
      trend: avoidedLossTrend,
      trendLabel: avoidedLossTrend === 'up' ? '风控持续拦截高风险信号' : avoidedLossTrend === 'stable' ? '拦截量平稳' : '审批阈值正常',
      explanation: `${rejectedSignals} 条信号被 AI 风控层自动拒绝，按单信号 $${estimatedLossPerSignal} 保守估算`,
      icon: <ShieldCheck className="w-4 h-4" />,
      color: 'emerald',
    },
    {
      id: 'auto-approvals',
      label: 'AI 自动审批次数',
      value: `${approvedSignals} 条`,
      trend: autoApprovalTrend,
      trendLabel: autoApprovalTrend === 'up' ? '审批流高效运转' : autoApprovalTrend === 'stable' ? '审批保持审慎' : '严格防御模式',
      explanation: `${approvedSignals}/${totalSignals} 信号自动批准，审批通过率 ${autoApprovalRate.toFixed(0)}%`,
      icon: <Zap className="w-4 h-4" />,
      color: 'cyan',
    },
    {
      id: 'saved-hours',
      label: '自动化节省工时',
      value: savedHoursFormatted,
      trend: savedTrend,
      trendLabel: savedTrend === 'up' ? '自动化持续释放人力' : '自动化平稳运行',
      explanation: `AI 自动审批 ${approvedSignals} 条信号 + 自动恢复 ${recoveryEvents} 次，累计节省人工审核与运维时间`,
      icon: <Clock className="w-4 h-4" />,
      color: 'violet',
    },
    {
      id: 'prevented-escalations',
      label: '风险升级阻止次数',
      value: `${preventedEscalations} 次`,
      trend: escalationTrend,
      trendLabel: escalationTrend === 'up' ? '风险遏制有效' : escalationTrend === 'stable' ? '关注进行中事故' : '需要人工关注',
      explanation: `${resolvedIncidents.length} 起事故中 ${preventedEscalations} 起在升级前被自动恢复，当前 ${activeIncidents} 起进行中`,
      icon: <TrendingDown className="w-4 h-4" />,
      color: 'amber',
    },
    {
      id: 'auto-recoveries',
      label: '自动恢复次数',
      value: `${autoRecoveries} 次`,
      trend: recoveryTrend,
      trendLabel: recoveryTrend === 'up' ? '自愈能力持续运作' : recoveryTrend === 'stable' ? '恢复机制正常' : '恢复事件较少',
      explanation: `包含 fallback 切换、自动重连、异常恢复等自动化恢复动作`,
      icon: <RotateCcw className="w-4 h-4" />,
      color: 'cyan',
    },
    {
      id: 'agent-collaboration',
      label: '多 Agent 协同效率',
      value: collaborationEfficiency,
      trend: collabTrend,
      trendLabel: collabTrend === 'up' ? 'Agent 集群协同优秀' : collabTrend === 'stable' ? '协同保持稳定' : '需要关注 Agent 状态',
      explanation: `${totalAgents} 个 Agent 在线，健康评分 ${healthScore}%，错误数 ${errorCount}`,
      icon: <Users className="w-4 h-4" />,
      color: 'violet',
    },
  ]
}

// ── Metric Card Sub-Component ──────────────────────────────

function MetricCard({ metric }: { metric: ImpactMetric }) {
  const colorSet = {
    emerald: {
      border: 'border-emerald-500/20',
      bg: 'bg-emerald-500/5',
      text: 'text-emerald-400',
      iconBg: 'bg-emerald-500/10',
    },
    cyan: {
      border: 'border-cyan-500/20',
      bg: 'bg-cyan-500/5',
      text: 'text-cyan-400',
      iconBg: 'bg-cyan-500/10',
    },
    amber: {
      border: 'border-amber-500/20',
      bg: 'bg-amber-500/5',
      text: 'text-amber-400',
      iconBg: 'bg-amber-500/10',
    },
    violet: {
      border: 'border-violet-500/20',
      bg: 'bg-violet-500/5',
      text: 'text-violet-400',
      iconBg: 'bg-violet-500/10',
    },
  }

  const cs = colorSet[metric.color]

  return (
    <div className={`rounded-xl border ${cs.border} ${cs.bg} p-4 backdrop-blur-sm group hover:${cs.border.replace('/20', '/30')} transition-all duration-300`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className={`w-8 h-8 rounded-lg ${cs.iconBg} border ${cs.border} flex items-center justify-center`}>
          <span className={cs.text}>{metric.icon}</span>
        </div>
        <div className="flex items-center gap-1">
          {metric.trend === 'up' ? (
            <TrendingUp className="w-3 h-3 text-emerald-400" />
          ) : metric.trend === 'down' ? (
            <TrendingDown className="w-3 h-3 text-red-400" />
          ) : (
            <div className="w-3 h-0.5 rounded-full bg-slate-500" />
          )}
          <span
            className={`text-[8px] font-mono ${
              metric.trend === 'up' ? 'text-emerald-400' : metric.trend === 'down' ? 'text-red-400' : 'text-slate-500'
            }`}
          >
            {metric.trendLabel}
          </span>
        </div>
      </div>

      {/* Value */}
      <div className={`text-xl font-bold font-mono ${cs.text} mb-1`}>
        {metric.value}
      </div>

      {/* Label */}
      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2">
        {metric.label}
      </div>

      {/* Explanation tooltip */}
      <div className="text-[9px] font-mono text-slate-600 leading-relaxed opacity-0 group-hover:opacity-100 transition-opacity duration-300">
        {metric.explanation}
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────

export default function BusinessImpactPanel({ kpis, incidents, events, truthBadge }: Props) {
  const metrics = useMemo(
    () => deriveBusinessImpact(kpis, incidents, events),
    [kpis, incidents, events],
  )

  if (!kpis) {
    return (
      <div className="rounded-2xl border border-slate-700/30 bg-gradient-to-b from-slate-800/60 to-slate-900/60 backdrop-blur-sm p-6">
        <span className="text-xs font-mono text-slate-500">业务影响评估加载中…</span>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-slate-700/30 bg-gradient-to-b from-slate-800/60 to-slate-900/60 backdrop-blur-sm p-6 relative">
      {/* Truth Badge */}
      {truthBadge && <div className="absolute top-3 right-3 z-10">{truthBadge}</div>}
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200 tracking-wide">业务影响评估</h3>
            <p className="text-[9px] font-mono text-slate-500">Business Impact · Runtime → ROI 转换</p>
          </div>
        </div>
        {/* Summary chip */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-cyan-500/20 bg-cyan-500/5 text-[10px] font-mono text-cyan-400">
          <Zap className="w-3 h-3" />
          <span>实时推导</span>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-3 gap-4">
        {metrics.map((m) => (
          <MetricCard key={m.id} metric={m} />
        ))}
      </div>

      {/* Footer note */}
      <div className="mt-4 pt-3 border-t border-slate-700/20 flex items-center gap-2">
        <span className="text-[8px] font-mono text-slate-600 uppercase tracking-wider">推导依据</span>
        <span className="text-[9px] font-mono text-slate-500">
          所有指标基于真实 Runtime Activity 推导，采用保守估算模型。避免潜在亏损 = 被拒信号数 × 单信号估算风险敞口；节省工时 = 自动审批数 × 平均人工审核时长 + 自动恢复 × 平均运维干预时长。
        </span>
      </div>
    </div>
  )
}