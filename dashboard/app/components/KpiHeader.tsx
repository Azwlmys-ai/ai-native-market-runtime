'use client'

import { useMemo } from 'react'
import type { RuntimeEvent } from '../data/types'
import type { AgentRuntimeStatus } from '../data/types'
import type { DashboardKpis } from '../hooks/useDashboardSummary'

interface KpiHeaderProps {
  events: RuntimeEvent[]
  agentStates: AgentRuntimeStatus[]
  /** Real aggregated KPI data from /api/dashboard-summary */
  dashboardKpis?: DashboardKpis | null
  /** Source of dashboard KPI data */
  dashboardSource?: 'real' | 'mixed' | 'fallback'
  /** Presentation mode for meeting-room display */
  presentationMode?: boolean
  /** Optional external demo info for extended KPIs */
  demoInfo?: { incidentCount24h?: number; mttr?: number; throughput?: number }
  /** Executive mode: hides raw telemetry, shows only executive KPIs */
  executiveMode?: boolean
  /** Open a read-only detail report for a KPI tile. */
  onOpenReport?: (reportId: string) => void
}

interface KpiValue {
  label: string
  value: string
  sub?: string
  accent: 'cyan' | 'green' | 'amber' | 'red' | 'slate' | 'violet' | 'indigo'
  /** Larger tile for emphasis */
  emphasis?: boolean
}

const ACCENT_COLORS: Record<KpiValue['accent'], string> = {
  cyan: 'text-cyan-200',
  green: 'text-emerald-200',
  amber: 'text-amber-200',
  red: 'text-rose-200',
  slate: 'text-slate-200',
  violet: 'text-violet-200',
  indigo: 'text-indigo-200',
}

const ACCENT_BG: Record<KpiValue['accent'], string> = {
  cyan: 'bg-cyan-500/18 border-cyan-400/45',
  green: 'bg-emerald-500/18 border-emerald-400/45',
  amber: 'bg-amber-500/18 border-amber-400/45',
  red: 'bg-rose-500/18 border-rose-400/45',
  slate: 'bg-slate-500/18 border-slate-400/45',
  violet: 'bg-violet-500/18 border-violet-400/45',
  indigo: 'bg-indigo-500/18 border-indigo-400/45',
}

function KpiTile({ label, value, sub, accent, large }: KpiValue & { large?: boolean }) {
  const content = (
    <>
      <div
        className={`font-mono text-slate-100 uppercase tracking-wider mb-1 ${
          large ? 'text-lg font-semibold' : 'text-base'
        }`}
      >
        {label}
      </div>
      <div
        className={`font-mono font-black ${ACCENT_COLORS[accent]} leading-tight ${
          large ? 'text-5xl' : 'text-4xl'
        }`}
      >
        {value}
      </div>
      {sub && (
        <div className={`font-mono text-slate-200 mt-1 ${large ? 'text-base' : 'text-sm'}`}>
          {sub}
        </div>
      )}
      <div className="mt-3 text-xs font-mono text-slate-300/80">点击查看详细报告</div>
    </>
  )

  return (
    <div
      className={`flex-1 min-w-0 border rounded-lg ${
        large ? 'px-5 py-4' : 'px-4 py-3'
      } ${ACCENT_BG[accent]}`}
    >
      {content}
    </div>
  )
}

function KpiButton({
  reportId,
  onOpenReport,
  ...tile
}: KpiValue & { large?: boolean; reportId: string; onOpenReport?: (reportId: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpenReport?.(reportId)}
      className="flex-1 min-w-0 text-left rounded-lg transition-transform hover:scale-[1.01] focus:outline-none focus:ring-2 focus:ring-cyan-300/60"
      title={`${tile.label}详细报告`}
    >
      <KpiTile {...tile} />
    </button>
  )
}

export default function KpiHeader({
  events,
  agentStates,
  dashboardKpis,
  dashboardSource,
  onOpenReport,
}: KpiHeaderProps) {
  // Fallback KPI values computed from SSE events (used when no real dashboard data)
  const fallbackKpis = useMemo(() => {
    let signalsToday = 0
    let approvals = 0
    let rejections = 0
    let dryRuns = 0
    let errors = 0

    for (const ev of events) {
      switch (ev.type) {
        case 'signal_created':
          signalsToday++
          break
        case 'review_approved':
          approvals++
          break
        case 'review_rejected':
          rejections++
          break
        case 'dry_run_executed':
          dryRuns++
          break
        case 'error':
          errors++
          break
      }
    }

    const activeAgents = agentStates.filter((a) => a.state !== 'IDLE').length
    const totalAgents = agentStates.length

    const totalOps = signalsToday + dryRuns + errors
    const healthScore =
      totalOps === 0 ? 100 : Math.max(0, Math.round(((totalOps - errors * 3) / totalOps) * 100))

    return {
      signalsToday,
      approvals,
      rejections,
      dryRuns,
      errors,
      activeAgents,
      totalAgents,
      healthScore,
    }
  }, [events, agentStates])

  // ── Enterprise KPIs ──────────────────────────────────────
  const enterpriseKpis = useMemo(() => {
    const totalAgentsCount = agentStates.length
    // "active" = agents currently processing events (not IDLE, not ERROR)
    // The rest are in STANDBY — event-driven, not offline
    const activeAgentCount = agentStates.filter(
      (a) => a.state !== 'IDLE' && a.state !== 'ERROR',
    ).length
    const standbyAgentCount = totalAgentsCount - activeAgentCount

    // Auto-approval rate: approved signals / total signals (exclude rejected)
    let totalSignals = 0
    let approvedCount = 0
    let rejectedCount = 0
    let errorCount = 0
    for (const ev of events) {
      switch (ev.type) {
        case 'signal_created':
          totalSignals++
          break
        case 'review_approved':
          approvedCount++
          break
        case 'review_rejected':
          rejectedCount++
          break
        case 'error':
          errorCount++
          break
      }
    }
    const autoApprovalRate =
      approvedCount + rejectedCount > 0
        ? Math.round((approvedCount / (approvedCount + rejectedCount)) * 100)
        : 100

    // Risk intercept rate
    const riskInterceptRate =
      totalSignals > 0 ? Math.round((rejectedCount / totalSignals) * 100) : 0

    // Error rate (runtime stability)
    const totalOps = totalSignals + errorCount + fallbackKpis.dryRuns
    const stabilityScore =
      totalOps > 0 ? Math.max(0, 100 - Math.round((errorCount / totalOps) * 100)) : 100

    // Throughput
    const throughput = events.length

    // Incident count (count errors as incident proxy)
    const incidentCount = errorCount

    return {
      activeAgentCount,
      standbyAgentCount,
      autoApprovalRate,
      riskInterceptRate,
      stabilityScore,
      throughput,
      incidentCount,
      totalAgents: totalAgentsCount,
    }
  }, [events, agentStates, fallbackKpis.dryRuns])

  // Determine which values to show
  const isReal = dashboardSource === 'real' && dashboardKpis
  const signalsValue = isReal ? dashboardKpis.totalSignals : fallbackKpis.signalsToday
  const approvedValue = isReal ? dashboardKpis.approvedSignals : fallbackKpis.approvals
  const rejectedValue = isReal ? dashboardKpis.rejectedSignals : fallbackKpis.rejections
  const dryRunsValue = fallbackKpis.dryRuns
  const errorsValue = isReal ? dashboardKpis.errorCount : fallbackKpis.errors
  const healthScoreValue = isReal ? dashboardKpis.healthScore : fallbackKpis.healthScore
  const activeAgents = fallbackKpis.activeAgents
  const totalAgents = fallbackKpis.totalAgents
  const runtimeStatus = dashboardKpis?.runtimeStatus
  const regime = dashboardKpis?.regime

  const healthAccent: KpiValue['accent'] =
    healthScoreValue >= 90 ? 'green' : healthScoreValue >= 70 ? 'amber' : 'red'

  const statusAccent: KpiValue['accent'] =
    runtimeStatus === 'ONLINE' ? 'green' : runtimeStatus === 'DEGRADED' ? 'amber' : 'red'

  return (
    <div className="flex flex-col bg-slate-700/80 border-b border-slate-500/45 relative">
      {/* Row 1: Operational KPIs */}
      <div className="flex items-stretch gap-4 px-5 py-4">
        {/* REAL DATA badge */}
        {isReal && (
          <div className="absolute top-1 right-3 text-xs font-mono text-emerald-400 bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 rounded tracking-wider uppercase font-bold">
            REAL DATA
          </div>
        )}
        <KpiButton reportId="signals" onOpenReport={onOpenReport} label="信号" value={String(signalsValue)} accent="cyan" />
        <KpiButton reportId="approved" onOpenReport={onOpenReport} label="已批准" value={String(approvedValue)} accent="green" />
        <KpiButton reportId="rejected" onOpenReport={onOpenReport} label="已拒绝" value={String(rejectedValue)} accent="amber" />
        <KpiButton reportId="dryrun" onOpenReport={onOpenReport} label="DryRun" value={String(dryRunsValue)} accent="violet" />
        <KpiButton
          reportId="errors"
          onOpenReport={onOpenReport}
          label="错误"
          value={String(errorsValue)}
          accent={errorsValue > 0 ? 'red' : 'slate'}
        />
        <KpiButton
          reportId="active-agents"
          onOpenReport={onOpenReport}
          label="活跃 Agent"
          value={`${activeAgents}/${totalAgents}`}
          accent={activeAgents > 0 ? 'cyan' : 'slate'}
        />
        <KpiButton
          reportId="health"
          onOpenReport={onOpenReport}
          label="健康评分"
          value={`${healthScoreValue}%`}
          sub={
            isReal && runtimeStatus
              ? `状态: ${runtimeStatus}${regime ? ` · ${regime}` : ''}`
              : healthScoreValue >= 90
                ? '健康'
                : healthScoreValue >= 70
                  ? '降级'
                  : '严重'
          }
          accent={healthAccent}
        />
        {isReal && runtimeStatus && (
          <KpiButton
            reportId="runtime-status"
            onOpenReport={onOpenReport}
            label="系统状态"
            value={runtimeStatus}
            sub={regime ?? undefined}
            accent={statusAccent}
          />
        )}
      </div>

      {/* Row 2: Enterprise KPIs */}
      <div className="flex items-stretch gap-4 px-5 py-3 border-t border-slate-500/35 bg-slate-700/55">
        <KpiButton
          reportId="agent-status"
          onOpenReport={onOpenReport}
          label="AGENT 状态"
          value={`${enterpriseKpis.activeAgentCount} ACTIVE`}
          sub={`${enterpriseKpis.standbyAgentCount} STANDBY — 事件驱动待命，非离线`}
          accent={enterpriseKpis.activeAgentCount > 0 ? 'green' : enterpriseKpis.totalAgents > 0 ? 'amber' : 'slate'}
        />
        <KpiButton
          reportId="auto-approval"
          onOpenReport={onOpenReport}
          label="自动决策通过率"
          value={`${enterpriseKpis.autoApprovalRate}%`}
          sub="AI 自动审核"
          accent={enterpriseKpis.autoApprovalRate >= 80 ? 'green' : 'amber'}
        />
        <KpiButton
          reportId="risk-intercept"
          onOpenReport={onOpenReport}
          label="风险拦截率"
          value={`${enterpriseKpis.riskInterceptRate}%`}
          sub="风控阻断"
          accent={enterpriseKpis.riskInterceptRate <= 20 ? 'green' : enterpriseKpis.riskInterceptRate <= 40 ? 'amber' : 'red'}
        />
        <KpiButton
          reportId="runtime-stability"
          onOpenReport={onOpenReport}
          label="运行时稳定性"
          value={`${enterpriseKpis.stabilityScore}%`}
          sub="无故障运行"
          accent={enterpriseKpis.stabilityScore >= 95 ? 'green' : enterpriseKpis.stabilityScore >= 85 ? 'amber' : 'red'}
        />
        <KpiButton
          reportId="event-throughput"
          onOpenReport={onOpenReport}
          label="事件处理量"
          value={String(enterpriseKpis.throughput)}
          sub="总事件数"
          accent="indigo"
        />
        <KpiButton
          reportId="incidents-24h"
          onOpenReport={onOpenReport}
          label="近 24h 事故"
          value={String(enterpriseKpis.incidentCount)}
          sub="Incident"
          accent={enterpriseKpis.incidentCount === 0 ? 'green' : enterpriseKpis.incidentCount <= 3 ? 'amber' : 'red'}
        />
      </div>
    </div>
  )
}
