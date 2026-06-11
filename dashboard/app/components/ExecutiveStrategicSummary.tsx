'use client'

import { useMemo } from 'react'
import type { DashboardKpis } from '../hooks/useDashboardSummary'
import type { NarrativeItem } from '../lib/runtimeNarrative'
import type { Incident } from '../hooks/useIncidents'

interface Props {
  kpis: DashboardKpis | null
  narratives: NarrativeItem[]
  incidents: Incident[]
  regime: string | null | undefined
}

export default function ExecutiveStrategicSummary({ kpis, narratives, incidents, regime }: Props) {
  const summary = useMemo(() => {
    // ── Derived KPIs from real DashboardKpis ─────────────────
    const autoApprovalRate =
      kpis && kpis.totalSignals > 0
        ? Math.round((kpis.approvedSignals / kpis.totalSignals) * 100)
        : 100
    const rejectionRate =
      kpis && kpis.totalSignals > 0
        ? Math.round((kpis.rejectedSignals / kpis.totalSignals) * 100)
        : 0
    const stabilityScore = kpis?.healthScore ?? 100

    // ── Market Regime assessment ─────────────────────────────
    const rawRegime = (regime ?? '').toLowerCase()
    const hasHighVol = rawRegime.includes('high')
    const isTrendPredominant = rawRegime.includes('trend')
    const isHighCorrelation =
      rawRegime.includes('correlation') || rawRegime.includes('high corr')

    // ── Risk posture ────────────────────────────────────────
    let riskPosture: string
    if (autoApprovalRate >= 85) {
      riskPosture = '宽松 — 市场环境稳定，自动审核门槛正常'
    } else if (autoApprovalRate >= 60) {
      riskPosture = '审慎 — 风险系统已适度提高审批阈值'
    } else {
      riskPosture = '收紧 — 风险系统已显著提高审批门槛，减少高风险敞口'
    }

    // ── Incident summary ─────────────────────────────────────
    const activeIncidents = incidents.filter((i) => !i.resolvedTime)
    const recentCritical = incidents.filter(
      (i) => i.severity === 'critical' || i.severity === 'high',
    )
    const incidentStatement =
      activeIncidents.length === 0
        ? '过去 30 分钟无严重 incident'
        : `${activeIncidents.length} 个 incident 进行中${recentCritical.length > 0 ? `（含 ${recentCritical.length} 个高严重度）` : ''}`

    // ── Stability assessment ─────────────────────────────────
    const stabilityLabel =
      stabilityScore >= 95 ? '稳定' : stabilityScore >= 80 ? '轻微波动' : '需关注'

    // ── Trend description ────────────────────────────────────
    const trendDesc = isTrendPredominant
      ? '趋势主导，方向性信号权重提升'
      : hasHighVol
        ? '高波动环境，套利机会增多但风险上升'
        : '波动可控，系统运行在标准参数区间'

    const correlationDesc = isHighCorrelation
      ? '多市场相关性上升，跨市场联动增强 — 注意尾部风险'
      : '市场间相关性正常，分散化保护有效'

    const regimeDesc = regime
      ? `当前市场体制：${regime}`
      : '市场体制未识别'

    return {
      riskPosture,
      incidentStatement,
      regimeDesc,
      trendDesc,
      correlationDesc,
      stabilityLabel,
      stabilityScore,
      hasHighVol,
      isTrendPredominant,
      isHighCorrelation,
      autoApprovalRate,
    }
  }, [regime, kpis, incidents, narratives])

  if (!kpis) {
    return (
      <div className="px-5 py-3 bg-slate-800/40 border-b border-slate-700/30">
        <span className="text-xs font-mono text-slate-500">战略摘要加载中…</span>
      </div>
    )
  }

  return (
    <div className="px-5 py-3.5 bg-gradient-to-r from-slate-900/80 via-slate-800/60 to-slate-900/80 border-b border-slate-700/30">
      {/* Main summary line */}
      <div className="flex items-center gap-3 mb-2">
        <span className="text-[9px] font-bold font-mono text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 px-1.5 py-0.5 rounded uppercase tracking-wider">
          战略摘要
        </span>
        <span className="text-xs font-mono text-slate-200 leading-relaxed">
          系统当前处于：
          <span className={summary.hasHighVol ? 'text-amber-400 font-semibold' : 'text-emerald-400 font-semibold'}>
            {' '}{summary.isTrendPredominant ? '趋势' : summary.hasHighVol ? '高波动' : '低波动'}
          </span>
          <span className="text-slate-400"> / </span>
          <span className={summary.isHighCorrelation ? 'text-violet-400 font-semibold' : 'text-cyan-400 font-semibold'}>
            {summary.isHighCorrelation ? '高相关' : '正常相关'}
          </span>
          {' '}市场环境，
          <span className="text-cyan-400 font-semibold"> {summary.riskPosture}</span>。
          <span className={summary.stabilityScore >= 95 ? 'text-emerald-400' : summary.stabilityScore >= 80 ? 'text-amber-400' : 'text-red-400'}>
            {' '}{summary.incidentStatement}
          </span>。
        </span>
      </div>

      {/* Detail row */}
      <div className="grid grid-cols-4 gap-3">
        <div className="flex flex-col gap-0.5">
          <span className="text-[8px] font-mono text-slate-500 uppercase tracking-wider">市场体制</span>
          <span className="text-[11px] font-mono text-slate-300">{summary.regimeDesc}</span>
          <span className="text-[9px] font-mono text-slate-500">{summary.trendDesc}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[8px] font-mono text-slate-500 uppercase tracking-wider">关联特征</span>
          <span className="text-[11px] font-mono text-slate-300">多市场联动</span>
          <span className="text-[9px] font-mono text-slate-500">{summary.correlationDesc}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[8px] font-mono text-slate-500 uppercase tracking-wider">风险姿态</span>
          <span className={`text-[11px] font-mono ${summary.autoApprovalRate >= 85 ? 'text-emerald-400' : summary.autoApprovalRate >= 60 ? 'text-amber-400' : 'text-red-400'}`}>
            审批阈值：{summary.autoApprovalRate}%
          </span>
          <span className="text-[9px] font-mono text-slate-500">{summary.riskPosture}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[8px] font-mono text-slate-500 uppercase tracking-wider">系统态势</span>
          <span className={`text-[11px] font-mono ${summary.stabilityScore >= 95 ? 'text-emerald-400' : summary.stabilityScore >= 80 ? 'text-amber-400' : 'text-red-400'}`}>
            {summary.stabilityLabel} · {summary.stabilityScore}%
          </span>
          <span className="text-[9px] font-mono text-slate-500">{summary.incidentStatement}</span>
        </div>
      </div>
    </div>
  )
}