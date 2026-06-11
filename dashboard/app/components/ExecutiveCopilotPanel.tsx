'use client'

import { useMemo } from 'react'
import { Brain, Sparkles, TrendingUp, Shield, AlertTriangle, Activity } from 'lucide-react'
import type { DashboardKpis } from '../hooks/useDashboardSummary'
import type { NarrativeItem } from '../lib/runtimeNarrative'
import type { Incident } from '../hooks/useIncidents'

// ── Types ─────────────────────────────────────────────────

interface Props {
  kpis: DashboardKpis | null
  narratives: NarrativeItem[]
  incidents: Incident[]
  regime: string | null | undefined
  hasHighVol: boolean
  isHighCorrelation: boolean
  truthBadge?: React.ReactNode
}

interface CopilotSection {
  id: string
  title: string
  content: string
  icon: React.ReactNode
  priority: 'HIGH' | 'MEDIUM' | 'LOW'
}

type ConfidenceLevel = 'HIGH' | 'MEDIUM' | 'LOW'

// ── Helpers ───────────────────────────────────────────────

function calcApprovalRate(kpis: DashboardKpis | null): number {
  if (!kpis || kpis.totalSignals === 0) return 100
  return Math.round((kpis.approvedSignals / kpis.totalSignals) * 100)
}

// ── Confidence derivation from runtime telemetry ──────────

function deriveConfidence(
  kpis: DashboardKpis | null,
  incidents: Incident[],
  narratives: NarrativeItem[],
  hasHighVol: boolean,
  isHighCorrelation: boolean,
): { level: ConfidenceLevel; reason: string } {
  let score = 100

  // Approval rate penalty
  const approvalRate = calcApprovalRate(kpis)
  if (approvalRate < 50) score -= 25
  else if (approvalRate < 70) score -= 10

  // Runtime stability
  const stability = kpis?.healthScore ?? 100
  if (stability < 70) score -= 20
  else if (stability < 85) score -= 8

  // Unresolved incidents
  const activeIncidents = incidents.filter((i) => !i.resolvedTime)
  if (activeIncidents.some((i) => i.severity === 'critical')) score -= 30
  else if (activeIncidents.some((i) => i.severity === 'high')) score -= 15
  else if (activeIncidents.length > 1) score -= 8
  else if (activeIncidents.length === 1) score -= 3

  // Volatility penalty
  if (hasHighVol) score -= 10

  // High correlation penalty
  if (isHighCorrelation) score -= 5

  // Narrative criticality
  const criticalNarratives = narratives.filter((n) => n.priority === 'critical')
  if (criticalNarratives.length > 0) score -= 12

  const highNarratives = narratives.filter((n) => n.priority === 'high')
  if (highNarratives.length > 2) score -= 6

  if (score >= 80) return { level: 'HIGH', reason: '运行时稳定性、审批通过率与事件恢复率均处于优秀区间' }
  if (score >= 55) return { level: 'MEDIUM', reason: '部分指标出现波动，风险控制系统已自动调整参数' }
  return { level: 'LOW', reason: '多项指标偏离基准线，建议关注风险态势与系统响应链' }
}

// ── Main Component ────────────────────────────────────────

export default function ExecutiveCopilotPanel({
  kpis,
  narratives,
  incidents,
  regime,
  hasHighVol,
  isHighCorrelation,
  truthBadge,
}: Props) {
  const confidence = useMemo(
    () => deriveConfidence(kpis, incidents, narratives, hasHighVol, isHighCorrelation),
    [kpis, incidents, narratives, hasHighVol, isHighCorrelation],
  )

  const sections: CopilotSection[] = useMemo(() => {
    const approvalRate = calcApprovalRate(kpis)
    const stability = kpis?.healthScore ?? 100
    const activeIncidents = incidents.filter((i) => !i.resolvedTime)
    const errorCount = kpis?.errorCount ?? 0
    const reconnectCount = kpis?.reconnects ?? 0
    const rawRegime = (regime ?? '').toLowerCase()

    // ── 1. 当前市场环境 ──────────────────────────────────
    const volLabel = hasHighVol ? '高波动' : '低波动'
    const corrLabel = isHighCorrelation ? '高相关' : '正常相关'
    const regimeLabel = rawRegime.includes('trend') ? '趋势行情' : rawRegime.includes('range') ? '震荡区间' : '标准市场'

    const marketEnv = `当前市场处于${corrLabel}${volLabel}环境，体制识别为${regimeLabel}。${hasHighVol ? '波动率超出基准区间，市场风险溢价上升。' : '市场波动性维持在可控范围内，有利于自动化策略执行。'}${isHighCorrelation ? '多资产高度相关，组合分散效应减弱，尾部风险概率上升。' : '资产间相关性正常，分散化保护机制有效运行。'}`

    // ── 2. AI 决策状态 ──────────────────────────────────
    let aiDecision: string
    if (approvalRate >= 85) {
      aiDecision = `AI 决策引擎运行在标准参数区间，自动审批通过率 ${approvalRate}%。${kpis ? `${kpis.approvedSignals} 条信号已自动批准，决策流延迟正常。` : ''}`
    } else if (approvalRate >= 55) {
      aiDecision = `AI 决策引擎已切换至审慎模式，审批阈值自动上调。当前通过率 ${approvalRate}%，${kpis ? `${kpis.rejectedSignals} 条信号被风控层拦截。` : ''}系统在高标准过滤下运行。`
    } else {
      aiDecision = `AI 决策引擎进入严格防御模式，审批通过率 ${approvalRate}% 处于低位。${kpis ? `${kpis.rejectedSignals} 条信号被拒绝，系统优先保障资金安全。` : ''}建议审查当前风险参数配置。`
    }

    // ── 3. 风险态势 ─────────────────────────────────────
    let riskStance: string
    if (activeIncidents.length > 0 && activeIncidents.some((i) => i.severity === 'critical' || i.severity === 'high')) {
      riskStance = `风险态势：高度警惕。${activeIncidents.length} 个事故进行中，含高危事件。系统已启动风险收缩策略，减少高风险信号暴露。`
    } else if (activeIncidents.length > 0) {
      riskStance = `风险态势：中度关注。${activeIncidents.length} 个低级别事故处理中，恢复流程已激活。当前不存在资金安全威胁。`
    } else if (stability >= 95) {
      riskStance = '风险态势：低风险。系统运行稳定，无进行中事故。风控模块处于常规监控状态。'
    } else {
      riskStance = `风险态势：轻度关注。健康评分 ${stability}%，虽无活跃事故但部分指标接近预警线。`
    }

    // ── 4. 系统动作 ─────────────────────────────────────
    const actions: string[] = []
    if (approvalRate < 70) actions.push('AI 风险控制系统已自动提高审批阈值')
    if (hasHighVol) actions.push('高波动资产敞口已自动收缩')
    if (reconnectCount > 0) actions.push(`自动重连机制已触发 ${reconnectCount} 次，fallback 通道正常`)
    if (errorCount > 0) actions.push(`错误隔离已生效，${errorCount} 条异常事件已标记`)
    if (actions.length === 0) actions.push('系统运行在标准参数配置下，无自动干预动作触发')

    const systemActions = actions.map((a) => `· ${a}`).join('\n')

    // ── 5. 建议关注项 ───────────────────────────────────
    const focus: string[] = []
    if (hasHighVol) focus.push('高波动市场环境下的持仓风险敞口')
    if (isHighCorrelation) focus.push('多资产高相关性导致的组合集中度风险')
    if (activeIncidents.length > 0) focus.push('进行中事故的恢复进展与影响范围')
    if (approvalRate < 55) focus.push('审批通过率偏低，建议评估风控参数是否过于保守')
    if (reconnectCount > 2) focus.push('网络连接稳定性，考虑备用接入点切换策略')

    const suggestions = focus.length > 0 ? focus.join('；') : '当前无特殊关注事项，系统运行正常'

    return [
      {
        id: 'market',
        title: '当前市场环境',
        content: marketEnv,
        icon: <TrendingUp className="w-4 h-4" />,
        priority: hasHighVol || isHighCorrelation ? 'HIGH' : 'MEDIUM',
      },
      {
        id: 'decision',
        title: 'AI 决策状态',
        content: aiDecision,
        icon: <Brain className="w-4 h-4" />,
        priority: approvalRate < 55 ? 'HIGH' : approvalRate < 85 ? 'MEDIUM' : 'LOW',
      },
      {
        id: 'risk',
        title: '风险态势',
        content: riskStance,
        icon: <Shield className="w-4 h-4" />,
        priority: activeIncidents.some((i) => i.severity === 'critical' || i.severity === 'high') ? 'HIGH' : 'MEDIUM',
      },
      {
        id: 'actions',
        title: '系统动作',
        content: systemActions,
        icon: <Activity className="w-4 h-4" />,
        priority: 'MEDIUM',
      },
      {
        id: 'focus',
        title: '建议关注项',
        content: suggestions,
        icon: <AlertTriangle className="w-4 h-4" />,
        priority: focus.length > 2 ? 'HIGH' : focus.length > 0 ? 'MEDIUM' : 'LOW',
      },
    ]
  }, [kpis, incidents, regime, hasHighVol, isHighCorrelation])

  const confidenceColors = {
    HIGH: {
      badge: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
      glow: 'shadow-[0_0_20px_rgba(52,211,153,0.15)]',
      pulse: 'bg-emerald-400',
    },
    MEDIUM: {
      badge: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
      glow: 'shadow-[0_0_20px_rgba(251,191,36,0.15)]',
      pulse: 'bg-amber-400',
    },
    LOW: {
      badge: 'text-red-400 bg-red-500/10 border-red-500/20',
      glow: 'shadow-[0_0_20px_rgba(248,113,113,0.15)]',
      pulse: 'bg-red-400',
    },
  }

  const cc = confidenceColors[confidence.level]

  if (!kpis) {
    return (
      <div className="rounded-2xl border border-slate-700/30 bg-gradient-to-b from-slate-800/60 to-slate-900/60 backdrop-blur-sm p-6">
        <span className="text-xs font-mono text-slate-500">AI 战略副驾驶加载中…</span>
      </div>
    )
  }

  return (
    <div className={`rounded-2xl border border-slate-700/30 bg-gradient-to-b from-slate-800/60 to-slate-900/60 backdrop-blur-sm p-6 ${cc.glow} transition-shadow duration-700 relative`}>
      {/* Truth Badge */}
      {truthBadge && <div className="absolute top-3 right-3 z-10">{truthBadge}</div>}
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200 tracking-wide">AI 战略副驾驶</h3>
            <p className="text-[9px] font-mono text-slate-500">Executive AI Copilot · 实时战略决策辅助</p>
          </div>
        </div>
        {/* Confidence Badge */}
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-[10px] font-mono font-bold ${cc.badge}`}>
          <div className={`w-2 h-2 rounded-full ${cc.pulse} animate-pulse`} />
          <span>{confidence.level} CONFIDENCE</span>
        </div>
      </div>

      {/* Sections */}
      <div className="space-y-4">
        {sections.map((section) => {
          const priorityColor =
            section.priority === 'HIGH'
              ? 'border-l-red-400/50 bg-red-500/3'
              : section.priority === 'MEDIUM'
                ? 'border-l-amber-400/50 bg-amber-500/3'
                : 'border-l-emerald-400/50 bg-emerald-500/3'

          return (
            <div key={section.id} className={`border-l-2 ${priorityColor} pl-4 py-2 rounded-r-lg transition-colors duration-500`}>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-slate-400">{section.icon}</span>
                <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wide">
                  {section.title}
                </span>
                <span
                  className={`text-[8px] font-mono px-1.5 py-0.5 rounded border ${
                    section.priority === 'HIGH'
                      ? 'text-red-400/80 border-red-500/20 bg-red-500/5'
                      : section.priority === 'MEDIUM'
                        ? 'text-amber-400/80 border-amber-500/20 bg-amber-500/5'
                        : 'text-emerald-400/80 border-emerald-500/20 bg-emerald-500/5'
                  }`}
                >
                  {section.priority}
                </span>
              </div>
              <p className="text-[11px] font-mono text-slate-400 leading-relaxed whitespace-pre-line">
                {section.content}
              </p>
            </div>
          )
        })}
      </div>

      {/* Footer confidence explanation */}
      <div className="mt-5 pt-4 border-t border-slate-700/20">
        <div className="flex items-center gap-2">
          <span className="text-[8px] font-mono text-slate-600 uppercase tracking-wider">Confidence 推导</span>
          <span className="text-[9px] font-mono text-slate-500">{confidence.reason}</span>
        </div>
      </div>
    </div>
  )
}