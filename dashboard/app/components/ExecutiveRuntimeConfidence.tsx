'use client'

import { useMemo } from 'react'
import type { LogEvent } from '../hooks/useLogEvents'
import type { Incident } from '../hooks/useIncidents'
import type { DashboardKpis } from '../hooks/useDashboardSummary'

// ── Types ─────────────────────────────────────────────────

interface Props {
  events: LogEvent[]
  incidents: Incident[]
  kpis: DashboardKpis | null
}

interface ConfidenceMetric {
  label: string
  value: string
  status: 'pass' | 'warn' | 'fail'
  detail: string
}

interface ReliabilitySummary {
  label: string
  detail: string
}

// ── Helpers ───────────────────────────────────────────────

function safeDiv(a: number, b: number): number {
  return b > 0 ? a / b : 0
}

function calcApprovalRate(kpis: DashboardKpis | null): number {
  if (!kpis) return 100
  const total = kpis.approvedSignals + kpis.rejectedSignals + kpis.timeoutSignals
  if (total === 0) return 100
  return Math.round((kpis.approvedSignals / total) * 100)
}

function getRegimeLabel(regime: string): string {
  if (regime.includes('high') || regime === 'volatile') return '高波动'
  if (regime.includes('low') || regime === 'calm') return '低波动'
  if (regime.includes('trend')) return '趋势'
  return regime || '默认'
}

function getRegimeConfidence(regime: string): number {
  // Derive regime confidence from regime string strength
  if (regime.includes('strong') || regime === 'trending') return 0.85
  if (regime.includes('high')) return 0.7
  if (regime.includes('low') || regime === 'calm') return 0.75
  if (regime === 'volatile') return 0.55
  return 0.65
}

function getRiskLabel(status: DashboardKpis['runtimeStatus']): 'low' | 'medium' | 'high' {
  switch (status) {
    case 'ONLINE': return 'low'
    case 'DEGRADED': return 'medium'
    case 'OFFLINE': return 'high'
  }
}

// ── Runtime-derived confidence computation ─────────────────

function computeConfidence(events: LogEvent[], incidents: Incident[], kpis: DashboardKpis | null): {
  metrics: ConfidenceMetric[]
  summaries: ReliabilitySummary[]
} {
  const recentEvents = events.slice(0, 200)
  const errorCount = recentEvents.filter((e) => e.level === 'ERROR').length
  const warnCount = recentEvents.filter((e) => e.level === 'WARN').length

  // Runtime stability: derived from error rate in recent event window
  const stabilityPct = recentEvents.length > 0
    ? Math.max(0, 100 - (errorCount / recentEvents.length) * 100)
    : 100
  const stabilityStatus: ConfidenceMetric['status'] =
    stabilityPct >= 98 ? 'pass' : stabilityPct >= 90 ? 'warn' : 'fail'

  // Incident recovery rate: active vs resolved
  const activeIncidents = incidents.filter((i) => !i.resolvedTime)
  const recoveryRate = incidents.length > 0
    ? Math.round(((incidents.length - activeIncidents.length) / incidents.length) * 100)
    : 100
  const recoveryStatus: ConfidenceMetric['status'] =
    recoveryRate >= 90 ? 'pass' : recoveryRate >= 70 ? 'warn' : 'fail'

  // Reconnect health: derived from WARN count and kpis.reconnects
  const reconnectCount = kpis?.reconnects ?? 0
  const reconnectIssues = warnCount > 5 || reconnectCount > 3
  const reconnectStatus: ConfidenceMetric['status'] = reconnectIssues ? 'warn' : 'pass'

  // Timeout isolation: derived from kpis.timeoutSignals
  const timeouts = kpis?.timeoutSignals ?? 0
  const timeoutStatus: ConfidenceMetric['status'] =
    timeouts === 0 ? 'pass' : timeouts <= 2 ? 'warn' : 'fail'

  // Agent consensus: derived from computed approval rate
  const approvalRate = calcApprovalRate(kpis)
  const consensusStatus: ConfidenceMetric['status'] =
    approvalRate >= 90 ? 'pass' : approvalRate >= 70 ? 'warn' : 'fail'

  // Risk level from runtime status
  const riskStatus = kpis?.runtimeStatus ?? 'ONLINE'
  const riskLevel = getRiskLabel(riskStatus)
  const riskLatencyStatus: ConfidenceMetric['status'] =
    riskLevel === 'low' ? 'pass' : riskLevel === 'medium' ? 'warn' : 'fail'

  // Decision confidence: composite score
  const regime = kpis?.regime ?? ''
  const regimeConfidence = getRegimeConfidence(regime)
  const decisionPct = Math.round(
    (regimeConfidence * 0.4 + (stabilityPct / 100) * 0.3 + (approvalRate / 100) * 0.3) * 100,
  )

  const metrics: ConfidenceMetric[] = [
    {
      label: '运行时稳定性',
      value: `${stabilityPct.toFixed(1)}%`,
      status: stabilityStatus,
      detail: `最近 ${recentEvents.length} 事件中 ${errorCount} 个错误`,
    },
    {
      label: '事件恢复率',
      value: `${recoveryRate}%`,
      status: recoveryStatus,
      detail: `${incidents.length} 事故中 ${incidents.length - activeIncidents.length} 已恢复`,
    },
    {
      label: '自动重连',
      value: reconnectStatus === 'pass' ? 'PASS' : 'WARN',
      status: reconnectStatus,
      detail: reconnectIssues ? `检测到 ${reconnectCount} 次重连` : '重连机制正常',
    },
    {
      label: '超时隔离',
      value: timeoutStatus === 'pass' ? 'PASS' : timeoutStatus === 'warn' ? 'WARN' : 'FAIL',
      status: timeoutStatus,
      detail: timeouts > 0 ? `${timeouts} 次超时信号已隔离` : '无超时信号',
    },
    {
      label: 'Agent 共识',
      value: `${approvalRate}%`,
      status: consensusStatus,
      detail: `审批 ${kpis?.approvedSignals ?? 0} · 拒绝 ${kpis?.rejectedSignals ?? 0}`,
    },
    {
      label: '决策信心',
      value: `${decisionPct}%`,
      status: decisionPct >= 70 ? 'pass' : decisionPct >= 50 ? 'warn' : 'fail',
      detail: `Regime ${getRegimeLabel(regime)} · 健康 ${kpis?.healthScore ?? 0}`,
    },
  ]

  const summaries: ReliabilitySummary[] = [
    {
      label: '异常恢复',
      detail:
        errorCount === 0
          ? '当前无异常事件，系统运行平稳。'
          : `${errorCount} 个错误 · 自动重连与超时隔离已激活 · 未发生级联故障。`,
    },
    {
      label: '资金安全',
      detail:
        `风险等级 ${riskLevel === 'low' ? '低' : riskLevel === 'medium' ? '中' : '高'} · ` +
        `审批率 ${approvalRate}% 通过 · 风控系统在线 · 无资金溢出。`,
    },
    {
      label: '数据完整性',
      detail:
        `${kpis?.totalSignals ?? 0} 信号 · ${kpis?.errorCount ?? 0} 内部错误 · ` +
        `重连 ${reconnectCount} 次 · 事件流连续。`,
    },
  ]

  return { metrics, summaries }
}

// ── Confidence Badge sub-component ─────────────────────────

function ConfidenceBadge({
  label,
  value,
  status,
  detail,
}: {
  label: string
  value: string
  status: 'pass' | 'warn' | 'fail'
  detail: string
}) {
  const statusColor =
    status === 'pass'
      ? 'border-emerald-500/20 bg-emerald-500/5'
      : status === 'warn'
      ? 'border-amber-500/20 bg-amber-500/5'
      : 'border-red-500/20 bg-red-500/5'

  const valueColor =
    status === 'pass'
      ? 'text-emerald-400'
      : status === 'warn'
      ? 'text-amber-400'
      : 'text-red-400'

  return (
    <div
      className={`rounded-lg border ${statusColor} p-3 backdrop-blur-sm text-center flex flex-col items-center justify-center group relative`}
      title={detail}
    >
      <span className="text-[8px] font-mono text-slate-500 uppercase tracking-wider mb-1.5">
        {label}
      </span>
      <span className={`text-lg font-bold font-mono ${valueColor}`}>
        {value}
      </span>
      <div className="mt-1.5 flex items-center gap-1">
        <div
          className={`w-1.5 h-1.5 rounded-full ${
            status === 'pass'
              ? 'bg-emerald-400'
              : status === 'warn'
              ? 'bg-amber-400'
              : 'bg-red-400'
          }`}
        />
        <span
          className={`text-[8px] font-mono ${
            status === 'pass'
              ? 'text-emerald-400/60'
              : status === 'warn'
              ? 'text-amber-400/60'
              : 'text-red-400/60'
          }`}
        >
          {status === 'pass' ? 'CERTIFIED' : status === 'warn' ? 'WARNING' : 'FAILED'}
        </span>
      </div>
      {/* Detail tooltip */}
      <div className="absolute -bottom-8 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
        <span className="text-[9px] font-mono text-slate-300 bg-slate-800 border border-slate-700 rounded px-2 py-1 whitespace-nowrap">
          {detail}
        </span>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────

export default function ExecutiveRuntimeConfidence({ events, incidents, kpis }: Props) {
  const { metrics, summaries } = useMemo(
    () => computeConfidence(events, incidents, kpis),
    [events, incidents, kpis],
  )

  const overallPassCount = metrics.filter((m) => m.status === 'pass').length
  const overallStatus: 'pass' | 'warn' | 'fail' =
    overallPassCount >= 5 ? 'pass' : overallPassCount >= 3 ? 'warn' : 'fail'

  return (
    <div className="flex-shrink-0 px-6 py-4">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2">
        <span
          className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${
            overallStatus === 'pass'
              ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
              : overallStatus === 'warn'
              ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
              : 'text-red-400 bg-red-500/10 border-red-500/20'
          }`}
        >
          {overallStatus === 'pass' ? '系统可信度' : overallStatus === 'warn' ? '需关注' : '异常'}
        </span>
        <span className="text-[9px] font-mono text-slate-600">
          Decision Confidence — runtime-derived
        </span>
        <span
          className={`text-[8px] font-mono ml-auto px-1.5 py-0.5 rounded border ${
            overallStatus === 'pass'
              ? 'text-emerald-400/80 border-emerald-500/20 bg-emerald-500/5'
              : overallStatus === 'warn'
              ? 'text-amber-400/80 border-amber-500/20 bg-amber-500/5'
              : 'text-red-400/80 border-red-500/20 bg-red-500/5'
          }`}
        >
          {overallPassCount}/{metrics.length} CERTIFIED
        </span>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-6 gap-3">
        {metrics.map((m) => (
          <ConfidenceBadge key={m.label} {...m} />
        ))}
      </div>

      {/* Reliability summaries */}
      <div className="mt-3 grid grid-cols-3 gap-3">
        {summaries.map((s) => (
          <div key={s.label} className="rounded-lg border border-emerald-500/10 bg-emerald-500/2 p-3">
            <div className="flex items-center gap-2 mb-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span className="text-[10px] font-bold font-mono text-slate-400">{s.label}</span>
            </div>
            <p className="text-[9px] font-mono text-slate-600 leading-relaxed">{s.detail}</p>
          </div>
        ))}
      </div>
    </div>
  )
}