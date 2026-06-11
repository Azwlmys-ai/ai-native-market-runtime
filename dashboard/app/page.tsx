'use client'

import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { useRuntimeSnapshot } from './data/runtimeState'
import { useRealTimeData } from './data/realTimeData'
import { useRuntimeEvents } from './data/runtimeEvents'
import { deriveAgentStates } from './data/agentState'
import { useDashboardSummary, type DashboardKpis } from './hooks/useDashboardSummary'
import { useAgentRuntimeActivity } from './hooks/useAgentRuntimeActivity'
import { useVisualizationState, type VisualizationState } from './hooks/useVisualizationState'
import { useAutoDemo } from './hooks/useAutoDemo'
import { useFilteredRuntime } from './hooks/useFilteredRuntime'
import { useIncidents } from './hooks/useIncidents'
import { useRuntimeNarrative } from './hooks/useRuntimeNarrative'
import { useExecutiveMode } from './contexts/ExecutiveModeContext'
import DataTruthBadge, { deriveTruthMeta } from './components/DataTruthBadge'
import type { DataTruthMeta } from './types/dataTruth'
import IncidentTimeline from './components/IncidentTimeline'
import IncidentCommandCenter from './components/IncidentCommandCenter'
import ExecutiveStrategicSummary from './components/ExecutiveStrategicSummary'
import type { AgentRuntimeStatus } from './data/types'
import AgentTopology from './components/AgentTopology'
import AgentTopologyModal from './components/AgentTopologyModal'
import AgentRuntimeInspector from './components/AgentRuntimeInspector'
import ExecutiveScenarioEnginePanel from './components/ExecutiveScenarioEnginePanel'
import RuntimeCommandCenter from './components/RuntimeCommandCenter'
import SignalReviewPanel from './components/SignalReviewPanel'
import MarketDataPanel from './components/MarketDataPanel'
import RiskControlPanel from './components/RiskControlPanel'
import DryRunTimeline from './components/DryRunTimeline'
import SystemMetricsBar from './components/SystemMetricsBar'
import RuntimeLogPanel from './components/RuntimeLogPanel'
import RuntimeTimelineView from './components/RuntimeTimeline'
import RuntimeEventFeed from './components/RuntimeEventFeed'
import KpiHeader from './components/KpiHeader'
import SystemHealthPanel from './components/SystemHealthPanel'
import DemoModeController from './components/DemoModeController'
import ClockDisplay from './components/ClockDisplay'
import ExecutiveKpiCards, { type DrillDownTarget } from './components/ExecutiveKpiCards'
import ExecutiveScenarios from './components/ExecutiveScenarios'
import ExecutiveNarrativeStrip from './components/ExecutiveNarrativeStrip'
import ExecutiveRoiPanel from './components/ExecutiveRoiPanel'
import ExecutiveDryRunValidation from './components/ExecutiveDryRunValidation'
import ExecutiveRuntimeConfidence from './components/ExecutiveRuntimeConfidence'
import ExecutiveKeyRuntimeEvents from './components/ExecutiveKeyRuntimeEvents'
import ExecutiveCopilotPanel from './components/ExecutiveCopilotPanel'
import BusinessImpactPanel from './components/BusinessImpactPanel'
import ResponseActionPanel from './components/ResponseActionPanel'
import NarrativeFlowGraph from './components/NarrativeFlowGraph'
import RuntimeNarrativeBanner from './components/RuntimeNarrativeBanner'
import { buildRuntimeTimelines } from './data/runtimeTimeline'
import { derivePrimaryScenario, deriveCandidateScenarios } from './lib/executiveScenarioEngine'
import type { ExecutiveScenario } from './lib/executiveScenarioEngine'

// ── Helpers ─────────────────────────────────────────────

function PanelHeader({ title }: { title: string }) {
  return (
    <div className="flex items-center mb-2 pb-2 border-b border-slate-400/35 flex-shrink-0">
      <h2 className="text-base font-bold font-mono text-slate-100 uppercase tracking-wider">{title}</h2>
    </div>
  )
}

function formatNumber(value: number | null | undefined, suffix = '') {
  if (value == null || Number.isNaN(value)) return '--'
  return `${value}${suffix}`
}

function compactTime(value: string | null | undefined) {
  if (!value) return 'no timestamp'
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return value
  return new Date(parsed).toLocaleString('zh-CN', { hour12: false })
}

function deriveDashboardKpisFromVisualization(state: VisualizationState | null): DashboardKpis | null {
  if (!state) return null

  const signals = state.signals_summary
  const review = state.review_summary
  const execution = state.execution_summary
  const logFiles = state.agent_log_summary?.files ?? []
  const logLevels = logFiles.reduce(
    (acc, file) => {
      const counts = file.level_counts ?? {}
      acc.errors += counts.error ?? 0
      acc.warnings += counts.warning ?? 0
      return acc
    },
    { errors: 0, warnings: 0 },
  )
  const totalSignals = review?.total ?? signals?.total ?? 0
  const failed = execution?.failed ?? 0
  const healthPenalty = logLevels.errors * 4 + logLevels.warnings * 2 + failed * 6
  const healthScore = Math.max(0, Math.min(100, 100 - healthPenalty))

  return {
    totalSignals,
    approvedSignals: review?.approved ?? 0,
    rejectedSignals: review?.rejected ?? 0,
    timeoutSignals: 0,
    activeAgents: state.agent_log_summary?.files_scanned ?? 0,
    errorCount: logLevels.errors + failed,
    warningCount: logLevels.warnings,
    healthScore,
    pnl: 0,
    reconnects: 0,
    runtimeStatus: healthScore >= 85 ? 'ONLINE' : healthScore >= 60 ? 'DEGRADED' : 'OFFLINE',
    regime: execution?.success && execution.success > 0 ? 'LIVE_EXECUTION_RECORDED' : 'DRY_RUN_MONITOR',
  }
}

function VisualizationStateSummary({
  state,
  updatedAt,
  loading,
  error,
  onOpenReport,
}: {
  state: VisualizationState | null
  updatedAt: string | null
  loading: boolean
  error: string | null
  onOpenReport?: (reportId: string) => void
}) {
  const signals = state?.signals_summary
  const review = state?.review_summary
  const execution = state?.execution_summary
  const logs = state?.agent_log_summary
  const events = state?.recent_runtime_events ?? []
  const logFiles = logs?.files ?? []

  return (
    <section className="flex-shrink-0 border-b border-slate-500/35 bg-slate-800/70 px-5 py-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold font-mono text-cyan-100 bg-cyan-500/20 border border-cyan-400/45 px-2 py-1 rounded uppercase tracking-wider">
            Visualization State
          </span>
          <span className="text-xs font-mono text-slate-300">
            source=/api/visualization-state · updated {compactTime(updatedAt ?? state?.timestamp)}
          </span>
        </div>
        <span className={`text-xs font-mono px-2 py-1 rounded border ${
          error
            ? 'text-amber-100 bg-amber-500/20 border-amber-400/45'
            : 'text-emerald-100 bg-emerald-500/20 border-emerald-400/45'
        }`}>
          {loading ? 'LOADING' : error ? 'LAST GOOD STATE' : 'LIVE SNAPSHOT'}
        </span>
      </div>

      <div className="grid grid-cols-5 gap-4">
        <button
          type="button"
          onClick={() => onOpenReport?.('visualization-signals')}
          className="rounded border border-slate-500/45 bg-slate-700/55 p-3 min-h-28 text-left transition-transform hover:scale-[1.01] hover:border-cyan-300/60 focus:outline-none focus:ring-2 focus:ring-cyan-300/60"
          title="Signals 详细报告"
        >
          <div className="text-xs font-bold font-mono text-slate-200 uppercase tracking-wider mb-1">Signals</div>
          <div className="text-2xl font-bold font-mono text-cyan-200">{formatNumber(signals?.total)}</div>
          <div className="text-xs font-mono text-slate-200 mt-1">
            avg conf {formatNumber(signals?.average_confidence, '%')}
          </div>
          <div className="text-xs font-mono text-slate-300 truncate">
            latest {compactTime(signals?.latest_signal_timestamp)}
          </div>
        </button>

        <button
          type="button"
          onClick={() => onOpenReport?.('visualization-review')}
          className="rounded border border-slate-500/45 bg-slate-700/55 p-3 min-h-28 text-left transition-transform hover:scale-[1.01] hover:border-cyan-300/60 focus:outline-none focus:ring-2 focus:ring-cyan-300/60"
          title="Review 详细报告"
        >
          <div className="text-xs font-bold font-mono text-slate-200 uppercase tracking-wider mb-1">Review</div>
          <div className="flex items-baseline gap-2 font-mono">
            <span className="text-2xl font-bold text-emerald-200">{formatNumber(review?.approved)}</span>
            <span className="text-xs text-slate-300">approved</span>
          </div>
          <div className="text-xs font-mono text-amber-200">{formatNumber(review?.rejected)} rejected</div>
          <div className="text-xs font-mono text-slate-300">total {formatNumber(review?.total)}</div>
        </button>

        <button
          type="button"
          onClick={() => onOpenReport?.('visualization-execution')}
          className="rounded border border-slate-500/45 bg-slate-700/55 p-3 min-h-28 text-left transition-transform hover:scale-[1.01] hover:border-cyan-300/60 focus:outline-none focus:ring-2 focus:ring-cyan-300/60"
          title="Execution 详细报告"
        >
          <div className="text-xs font-bold font-mono text-slate-200 uppercase tracking-wider mb-1">Execution</div>
          <div className="text-2xl font-bold font-mono text-emerald-200">{formatNumber(execution?.dry_run)}</div>
          <div className="text-xs font-mono text-slate-200">dry-run executions</div>
          <div className="text-xs font-mono text-red-200">{formatNumber(execution?.success)} live success</div>
          <div className="text-xs font-mono text-slate-300">failed {formatNumber(execution?.failed)}</div>
        </button>

        <button
          type="button"
          onClick={() => onOpenReport?.('visualization-agent-logs')}
          className="rounded border border-slate-500/45 bg-slate-700/55 p-3 min-h-28 text-left transition-transform hover:scale-[1.01] hover:border-cyan-300/60 focus:outline-none focus:ring-2 focus:ring-cyan-300/60"
          title="Agent Logs 详细报告"
        >
          <div className="text-xs font-bold font-mono text-slate-200 uppercase tracking-wider mb-1">Agent Logs</div>
          <div className="text-2xl font-bold font-mono text-violet-200">{formatNumber(logs?.files_scanned)}</div>
          <div className="text-xs font-mono text-slate-200">files scanned</div>
          <div className="mt-1 space-y-0.5">
            {logFiles.slice(0, 2).map((file) => (
              <div key={file.file} className="text-xs font-mono text-slate-300 truncate">
                {file.file}
              </div>
            ))}
          </div>
        </button>

        <button
          type="button"
          onClick={() => onOpenReport?.('visualization-events')}
          className="rounded border border-slate-500/45 bg-slate-700/55 p-3 min-h-28 text-left transition-transform hover:scale-[1.01] hover:border-cyan-300/60 focus:outline-none focus:ring-2 focus:ring-cyan-300/60"
          title="Recent Events 详细报告"
        >
          <div className="text-xs font-bold font-mono text-slate-200 uppercase tracking-wider mb-1">Recent Events</div>
          <div className="space-y-1">
            {events.slice(-3).map((event, index) => (
              <div key={`${event.file}-${index}`} className="text-xs font-mono text-slate-200 leading-snug line-clamp-1" title={event.message}>
                {event.message || 'event'}
              </div>
            ))}
            {events.length === 0 && (
              <div className="text-xs font-mono text-slate-300">No runtime events in state</div>
            )}
          </div>
        </button>
      </div>
    </section>
  )
}

function reportTitle(reportId: string) {
  const titles: Record<string, string> = {
    signals: '信号详细报告',
    approved: '已批准信号报告',
    rejected: '已拒绝信号报告',
    dryrun: 'DryRun 执行报告',
    errors: '错误与异常报告',
    'active-agents': '活跃 Agent 报告',
    health: '健康评分报告',
    'runtime-status': '系统状态报告',
    'agent-status': 'Agent 状态报告',
    'auto-approval': '自动决策通过率报告',
    'risk-intercept': '风险拦截率报告',
    'runtime-stability': '运行时稳定性报告',
    'event-throughput': '事件处理量报告',
    'incidents-24h': '近 24H 事故报告',
    'visualization-signals': 'Visualization Signals 报告',
    'visualization-review': 'Visualization Review 报告',
    'visualization-execution': 'Visualization Execution 报告',
    'visualization-agent-logs': 'Visualization Agent Logs 报告',
    'visualization-events': 'Visualization Recent Events 报告',
  }
  return titles[reportId] ?? '状态详细报告'
}

function buildReportRows({
  reportId,
  dashboardKpis,
  visualizationState,
  agentStates,
  runtimeEvents,
  filteredEvents,
}: {
  reportId: string
  dashboardKpis: DashboardKpis | null
  visualizationState: VisualizationState | null
  agentStates: AgentRuntimeStatus[]
  runtimeEvents: ReturnType<typeof useRuntimeEvents>['events']
  filteredEvents: ReturnType<typeof useFilteredRuntime>['filteredEvents']
}) {
  const signals = visualizationState?.signals_summary
  const review = visualizationState?.review_summary
  const execution = visualizationState?.execution_summary
  const logs = visualizationState?.agent_log_summary
  const events = visualizationState?.recent_runtime_events ?? []
  const activeAgents = agentStates.filter((a) => a.state !== 'IDLE' && a.state !== 'ERROR').length
  const rows: Array<[string, string]> = []

  const pushCommon = () => {
    rows.push(['数据源', 'data/visualization_state.json + dashboard runtime hooks'])
    rows.push(['状态时间', compactTime(visualizationState?.timestamp)])
    rows.push(['运行事件', `${filteredEvents.length || runtimeEvents.length} 条`])
  }

  if (reportId.includes('signal') || reportId === 'approved' || reportId === 'rejected') {
    rows.push(['总信号', formatNumber(signals?.total)])
    rows.push(['平均置信度', formatNumber(signals?.average_confidence, '%')])
    rows.push(['平均期望值', formatNumber(signals?.average_expected_value)])
    rows.push(['最新信号时间', compactTime(signals?.latest_signal_timestamp)])
    rows.push(['已批准', formatNumber(review?.approved)])
    rows.push(['已拒绝', formatNumber(review?.rejected)])
  } else if (reportId.includes('execution') || reportId === 'dryrun') {
    rows.push(['执行总数', formatNumber(execution?.total)])
    rows.push(['DryRun', formatNumber(execution?.dry_run)])
    rows.push(['真实成功', formatNumber(execution?.success)])
    rows.push(['失败', formatNumber(execution?.failed)])
    rows.push(['最新执行时间', compactTime(execution?.latest_execution_timestamp)])
  } else if (reportId.includes('agent') || reportId === 'active-agents') {
    rows.push(['活跃 Agent', `${activeAgents}/${agentStates.length}`])
    rows.push(['日志文件扫描', formatNumber(logs?.files_scanned)])
    rows.push(['Runtime Agent 状态数', String(agentStates.length)])
    rows.push(['最新日志文件', logs?.files?.[0]?.file ?? '--'])
  } else if (reportId.includes('event') || reportId.includes('incident') || reportId === 'errors') {
    rows.push(['错误数', formatNumber(dashboardKpis?.errorCount)])
    rows.push(['警告数', formatNumber(dashboardKpis?.warningCount)])
    rows.push(['近 24H 事故', formatNumber(dashboardKpis?.errorCount)])
    rows.push(['Visualization recent events', String(events.length)])
  } else {
    rows.push(['系统状态', dashboardKpis?.runtimeStatus ?? '--'])
    rows.push(['健康评分', formatNumber(dashboardKpis?.healthScore, '%')])
    rows.push(['市场/运行体制', dashboardKpis?.regime ?? '--'])
    rows.push(['自动审批通过', formatNumber(dashboardKpis?.approvedSignals)])
    rows.push(['风险拦截', formatNumber(dashboardKpis?.rejectedSignals)])
  }

  pushCommon()
  return rows
}

function valueText(value: unknown) {
  if (value == null || value === '') return '--'
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '--'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function buildReportDetails({
  reportId,
  visualizationState,
  agentStates,
  runtimeEvents,
  filteredEvents,
}: {
  reportId: string
  visualizationState: VisualizationState | null
  agentStates: AgentRuntimeStatus[]
  runtimeEvents: ReturnType<typeof useRuntimeEvents>['events']
  filteredEvents: ReturnType<typeof useFilteredRuntime>['filteredEvents']
}): { title: string; items: Array<Record<string, unknown>> } {
  const signals = visualizationState?.signal_details ?? []
  const approved = visualizationState?.review_details?.approved_signals ?? []
  const rejected = visualizationState?.review_details?.rejected_signals ?? []
  const executions = visualizationState?.execution_details ?? []
  const logs = visualizationState?.agent_log_summary?.files ?? []
  const recentEvents = visualizationState?.recent_runtime_events ?? []

  if (reportId === 'signals' || reportId === 'visualization-signals') {
    return { title: `具体信号列表 (${signals.length})`, items: signals }
  }
  if (reportId === 'approved' || reportId === 'auto-approval') {
    return { title: `已批准信号 (${approved.length})`, items: approved }
  }
  if (reportId === 'rejected' || reportId === 'risk-intercept') {
    return { title: `已拒绝 / 风控拦截信号 (${rejected.length})`, items: rejected }
  }
  if (reportId === 'visualization-review') {
    return {
      title: `审查明细 (${approved.length + rejected.length})`,
      items: [
        ...approved.map((item) => ({ ...item, bucket: 'approved' })),
        ...rejected.map((item) => ({ ...item, bucket: 'rejected' })),
      ],
    }
  }
  if (reportId === 'dryrun' || reportId === 'visualization-execution') {
    return { title: `执行明细 (${executions.length})`, items: executions }
  }
  if (reportId === 'active-agents' || reportId === 'agent-status') {
    return {
      title: `Agent 状态明细 (${agentStates.length})`,
      items: agentStates.map((agent) => ({
        agent: agent.agent,
        state: agent.state,
        message: agent.message,
        updated_at: agent.updatedAt,
      })),
    }
  }
  if (reportId === 'visualization-agent-logs' || reportId === 'health' || reportId === 'runtime-status' || reportId === 'runtime-stability') {
    return {
      title: `Agent 日志与健康明细 (${logs.length})`,
      items: logs.map((log) => ({
        file: log.file,
        size_bytes: log.size_bytes,
        modified_at: log.modified_at,
        recent_line_count: log.recent_line_count,
        levels: log.level_counts,
        recent_lines: log.recent_lines?.slice(0, 3).join(' | '),
      })),
    }
  }
  if (reportId === 'visualization-events' || reportId === 'event-throughput' || reportId === 'incidents-24h' || reportId === 'errors') {
    const liveEvents = filteredEvents.length > 0 ? filteredEvents : runtimeEvents
    const normalizedLiveEvents = liveEvents.slice(0, 30).map((event) => ({
      timestamp: 'timestamp' in event ? event.timestamp : event.ts,
      agent: 'agent' in event ? event.agent : event.source,
      level: 'level' in event ? event.level : event.type,
      title: 'title' in event ? event.title : event.message,
      detail: 'detail' in event ? event.detail : event.message,
    }))
    return {
      title: `运行事件明细 (${recentEvents.length || normalizedLiveEvents.length})`,
      items: recentEvents.length > 0 ? recentEvents : normalizedLiveEvents,
    }
  }
  return { title: '明细', items: [] }
}

function StatusReportModal({
  reportId,
  onClose,
  dashboardKpis,
  visualizationState,
  agentStates,
  runtimeEvents,
  filteredEvents,
}: {
  reportId: string | null
  onClose: () => void
  dashboardKpis: DashboardKpis | null
  visualizationState: VisualizationState | null
  agentStates: AgentRuntimeStatus[]
  runtimeEvents: ReturnType<typeof useRuntimeEvents>['events']
  filteredEvents: ReturnType<typeof useFilteredRuntime>['filteredEvents']
}) {
  if (!reportId) return null

  const rows = buildReportRows({
    reportId,
    dashboardKpis,
    visualizationState,
    agentStates,
    runtimeEvents,
    filteredEvents,
  })
  const recentEvents = visualizationState?.recent_runtime_events ?? []
  const details = buildReportDetails({
    reportId,
    visualizationState,
    agentStates,
    runtimeEvents,
    filteredEvents,
  })

  return (
    <div className="fixed inset-0 z-[70] bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-6" onClick={onClose}>
      <div
        className="w-full max-w-5xl max-h-[86vh] overflow-hidden rounded-xl border border-cyan-400/35 bg-slate-800 shadow-2xl shadow-black/50"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-500/35 bg-slate-700/80">
          <div>
            <div className="text-xs font-mono text-cyan-200 uppercase tracking-widest">Detail Report</div>
            <h2 className="text-xl font-bold font-mono text-slate-100">{reportTitle(reportId)}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-sm font-mono text-slate-200 border border-slate-400/40 rounded px-3 py-1 hover:border-cyan-300/60 hover:text-cyan-100"
          >
            关闭
          </button>
        </div>

        <div className="overflow-y-auto max-h-[calc(86vh-80px)] p-5 space-y-5">
          <div className="grid grid-cols-3 gap-3">
            {rows.map(([label, value]) => (
              <div key={label} className="rounded border border-slate-500/35 bg-slate-700/50 p-3">
                <div className="text-xs font-bold font-mono text-slate-300 uppercase tracking-wider">{label}</div>
                <div className="mt-1 text-base font-mono text-slate-100 break-words">{value}</div>
              </div>
            ))}
          </div>

          {details.items.length > 0 && (
            <div className="rounded border border-slate-500/35 bg-slate-700/45 p-4">
              <div className="text-sm font-bold font-mono text-slate-100 mb-3">{details.title}</div>
              <div className="space-y-3">
                {details.items.map((item, index) => (
                  <div key={index} className="rounded border border-slate-500/30 bg-slate-800/45 p-3">
                    <div className="grid grid-cols-4 gap-3">
                      {Object.entries(item)
                        .filter(([, value]) => value != null && value !== '')
                        .slice(0, 8)
                        .map(([key, value]) => (
                          <div key={key} className={key === 'market_name' || key === 'reason' || key === 'detail' || key === 'message' || key === 'recent_lines' ? 'col-span-4' : ''}>
                            <div className="text-xs font-bold font-mono text-slate-400 uppercase tracking-wider">{key}</div>
                            <div className="text-sm font-mono text-slate-100 break-words">{valueText(value)}</div>
                          </div>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="rounded border border-slate-500/35 bg-slate-700/45 p-4">
            <div className="text-sm font-bold font-mono text-slate-100 mb-3">Recent Runtime Events</div>
            <div className="space-y-2">
              {recentEvents.slice(0, 8).map((event, index) => (
                <div key={`${event.file}-${index}`} className="text-sm font-mono text-slate-200 leading-relaxed">
                  <span className="text-cyan-300">{event.file}</span>
                  <span className="text-slate-500"> · </span>
                  {event.message}
                </div>
              ))}
              {recentEvents.length === 0 && (
                <div className="text-sm font-mono text-slate-400">暂无 recent runtime events</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}


// ── Main Dashboard ─────────────────────────────────────

export default function DashboardPage() {
  const snapshot = useRuntimeSnapshot()
  const agents = snapshot.agents
  const agentIds = agents.map((a) => a.id)

  const realData = useRealTimeData()
  const { events: runtimeEvents, sseConnected } = useRuntimeEvents()
  const { kpis: legacyDashboardKpis, source: legacyDashboardSource } = useDashboardSummary()
  const { agents: agentActivity, source: activitySource } = useAgentRuntimeActivity()
  const visualizationState = useVisualizationState()
  const visualizationKpis = useMemo(
    () => deriveDashboardKpisFromVisualization(visualizationState.state),
    [visualizationState.state],
  )
  const dashboardKpis = visualizationKpis ?? legacyDashboardKpis
  const dashboardSource = visualizationKpis ? 'real' : legacyDashboardSource
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedSignal, setSelectedSignal] = useState<string | null>(null)
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null)
  const [showDebug, setShowDebug] = useState(false)
  const [showDemoPopover, setShowDemoPopover] = useState(false)
  const [presentationMode, setPresentationMode] = useState(false)
  const [drillDown, setDrillDown] = useState<DrillDownTarget>(null)
  const [topologyExpanded, setTopologyExpanded] = useState(false)
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null)
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)

  // ── Executive Mode Context ──────────────────────────
  const {
    mode: viewMode,
    setMode: setViewMode,
    incidentCommandOpen,
    commandIncidentId,
    openIncidentCommand,
    closeIncidentCommand,
  } = useExecutiveMode()

  // ── Command Center Filters (Global Source of Truth) ──
  const {
    allEvents,
    filteredEvents,
    source: logSource,
    filterState,
    setLevelFilter,
    setAgentFilter,
    setCategoryFilters,
    setSearchQuery,
    setRuntimeViewMode,
  } = useFilteredRuntime()
  const { levelFilter, agentFilter, categoryFilters, searchQuery, runtimeViewMode } = filterState
  const demoBtnRef = useRef<HTMLButtonElement>(null)
  const demoPopoverRef = useRef<HTMLDivElement>(null)

  // ── Incident & Replay ───────────────────────────────
  const {
    incidents,
    selectedIncidentId,
    setSelectedIncidentId,
    selectedIncident,
    replayMode,
    replaySpeed,
    setReplaySpeed,
    replayIndex,
    replayProgress,
    replayEvents,
    currentReplayEvent,
    startReplay,
    pauseReplay,
    resumeReplay,
    stopReplay,
    stepForward,
    stepBackward,
  } = useIncidents(allEvents)

  // ── Runtime Narrative ───────────────────────────────
  const derivedAgentStates: AgentRuntimeStatus[] = useMemo(
    () => deriveAgentStates(runtimeEvents),
    [runtimeEvents],
  )
  const { narratives } = useRuntimeNarrative({
    events: filteredEvents,
    agentStates: derivedAgentStates,
    incidents,
    kpis: dashboardKpis,
  })

  // ── Find the command center incident ─────────────────
  const commandIncident = commandIncidentId
    ? incidents.find((i) => i.id === commandIncidentId) ?? null
    : null

  // ── When command center opens for an incident, auto-select it for replay ──
  useEffect(() => {
    if (commandIncidentId && commandIncidentId !== selectedIncidentId) {
      stopReplay()
      setSelectedIncidentId(commandIncidentId)
    }
  }, [commandIncidentId, selectedIncidentId, setSelectedIncidentId, stopReplay])

  // ── Auto Demo ────────────────────────────────────────
  // useAutoDemo expects 'runtime' | 'executive' but our context uses 'engineer'.
  // Map 'engineer' → 'runtime' for compatibility.
  const autoDemoViewMode = viewMode === 'engineer' ? 'runtime' as const : 'executive' as const
  const { status: demoStatus, currentLabel, currentSectionId, toggleDemo: toggleAutoDemo, stopDemo: stopAutoDemo } =
    useAutoDemo(autoDemoViewMode, (m) => setViewMode(m === 'runtime' ? 'engineer' : 'executive'))

  // ── Keyboard shortcuts (F, D, ESC) ──────────────────
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement
      const isInput =
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable

      if (isInput) return

      if (e.key === 'f' || e.key === 'F') {
        e.preventDefault()
        setPresentationMode((v) => !v)
      } else if (e.key === 'd' || e.key === 'D') {
        e.preventDefault()
        toggleAutoDemo()
      } else if (e.key === 'Escape') {
        e.preventDefault()
        if (incidentCommandOpen) {
          closeIncidentCommand()
          return
        }
        if (demoStatus !== 'OFF') {
          stopAutoDemo()
        }
        if (presentationMode) {
          setPresentationMode(false)
        }
        if (topologyExpanded) {
          setTopologyExpanded(false)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [presentationMode, demoStatus, toggleAutoDemo, stopAutoDemo, incidentCommandOpen, closeIncidentCommand, topologyExpanded])

  // ── Auto-collapse debug when entering presentation ──
  const togglePresentation = useCallback(() => {
    setPresentationMode((v) => {
      if (!v) {
        // Entering presentation: close debug + demo popover
        setShowDebug(false)
        setShowDemoPopover(false)
      }
      return !v
    })
  }, [])

  // Close demo popover on outside click
  useEffect(() => {
    if (!showDemoPopover) return
    function handleClick(e: MouseEvent) {
      const target = e.target as Node
      if (
        demoPopoverRef.current &&
        !demoPopoverRef.current.contains(target) &&
        demoBtnRef.current &&
        !demoBtnRef.current.contains(target)
      ) {
        setShowDemoPopover(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showDemoPopover])

  const agentStates = derivedAgentStates

  const selectedAgentRuntimeState = selectedId
    ? agentStates.find((s) => s.agent === selectedId) ?? null
    : null

  // Build runtime timelines from events
  const runtimeTimelines = useMemo(
    () => buildRuntimeTimelines(runtimeEvents),
    [runtimeEvents],
  )

  function handleSelectAgent(id: string | null) {
    setSelectedId(id)
  }

  function handleSelectSignal(signalId: string | null) {
    setSelectedSignal(signalId)
  }

  function handleSelectEvent(eventId: string | null) {
    setSelectedEvent(eventId)
  }

  const selectedAgent = selectedId
    ? agents.find((a) => a.id === selectedId) ?? null
    : null

  // Agent info chips for Command Center
  const agentChips = useMemo(
    () =>
      agents.map((a) => ({ id: a.id, name: a.name, layer: a.layer ?? '' })),
    [agents],
  )

  const isPresent = presentationMode
  const isExec = viewMode === 'executive'

  // ── Derived values for Executive modules ───────────
  const approvalRate = dashboardKpis && dashboardKpis.totalSignals > 0
    ? Math.round((dashboardKpis.approvedSignals / dashboardKpis.totalSignals) * 100)
    : 100
  const hasHighVol = dashboardKpis?.regime === '高波动' || (dashboardKpis?.errorCount ?? 0) > 2
  const isHighCorrelation = (dashboardKpis?.errorCount ?? 0) > 3 && (dashboardKpis?.reconnects ?? 0) > 0
  const unresolvedIncidents = incidents.filter((i) => !i.resolvedTime).length

  // ── Data Truth Layer: derive metadata from runtime state ──
  const isDemoActive = demoStatus === 'RUNNING'
  const hasRuntimeEvents = runtimeEvents.length > 0 || filteredEvents.length > 0
  const lastEventTs = useMemo(() => {
    const tss: number[] = []
    if (runtimeEvents.length > 0) {
      const d = Date.parse(runtimeEvents[0].ts)
      if (!Number.isNaN(d)) tss.push(d)
    }
    if (filteredEvents.length > 0) {
      const d = Date.parse(filteredEvents[0].timestamp)
      if (!Number.isNaN(d)) tss.push(d)
    }
    return tss.length > 0 ? Math.max(...tss) : undefined
  }, [runtimeEvents, filteredEvents])

  const [truthNow, setTruthNow] = useState(() => Date.now())
  useEffect(() => {
    const iv = setInterval(() => setTruthNow(Date.now()), 1000)
    return () => clearInterval(iv)
  }, [])

  const executiveTruthMeta: DataTruthMeta = useMemo(() =>
    deriveTruthMeta({
      sseConnected,
      lastEventTimestamp: lastEventTs,
      demoMode: isDemoActive,
      source: 'Runtime Command Center · 多 Agent 协同数据',
      isEmpty: !hasRuntimeEvents,
    }, truthNow),
    [sseConnected, lastEventTs, isDemoActive, hasRuntimeEvents, truthNow],
  )

  const kpiTruthMeta: DataTruthMeta = useMemo(() =>
    deriveTruthMeta({
      sseConnected,
      lastEventTimestamp: dashboardKpis ? truthNow : undefined,
      demoMode: isDemoActive,
      source: 'Dashboard KPI 汇总引擎',
      isEmpty: !dashboardKpis,
    }, truthNow),
    [sseConnected, dashboardKpis, isDemoActive, truthNow],
  )

  const narrativeTruthMeta: DataTruthMeta = useMemo(() =>
    deriveTruthMeta({
      sseConnected,
      lastEventTimestamp: truthNow,
      demoMode: isDemoActive,
      source: 'AI 叙事推理引擎',
      isEmpty: narratives.length === 0,
    }, truthNow),
    [sseConnected, narratives, isDemoActive, truthNow],
  )

  // ── Handle incident click from Narrative ────────────
  const handleNarrativeIncidentClick = useCallback(
    (incidentId: string) => {
      openIncidentCommand(incidentId)
    },
    [openIncidentCommand],
  )

  // ── Scenario Engine derivation ──────────────────────
  const hasActiveRecovery = useMemo(
    () => incidents.some(
      (i) => !i.resolvedTime && i.phases.some((p) => p.phase === 'recovery' || p.phase === 'mitigation'),
    ),
    [incidents],
  )

  const primaryScenario: ExecutiveScenario | null = useMemo(
    () =>
      derivePrimaryScenario({
        kpis: dashboardKpis,
        unresolvedIncidents: unresolvedIncidents,
        hasActiveRecovery,
        sseConnected,
      }),
    [dashboardKpis, unresolvedIncidents, hasActiveRecovery, sseConnected],
  )

  const candidateScenarios: ExecutiveScenario[] = useMemo(
    () =>
      deriveCandidateScenarios({
        kpis: dashboardKpis,
        unresolvedIncidents: unresolvedIncidents,
        hasActiveRecovery,
        sseConnected,
      }),
    [dashboardKpis, unresolvedIncidents, hasActiveRecovery, sseConnected],
  )

  // ── Handle incident click from IncidentTimeline ──────
  const handleIncidentTimelineClick = useCallback(
    (incident: { id: string }) => {
      openIncidentCommand(incident.id)
    },
    [openIncidentCommand],
  )

  return (
    <div
      className={`flex flex-col min-h-screen bg-[#17264a] text-slate-100 ${
        isPresent ? 'presentation-mode recording-safe' : ''
      }`}
    >
      {/* ══════ ROW 0: TOP HEADER ═══════════════════════ */}
      <header
        className={`flex items-center justify-between border-b border-slate-500/35 bg-slate-700/90 flex-shrink-0 ${
          isPresent ? 'px-6 py-3' : 'px-4 py-2'
        }`}
      >
        <div className="flex items-center gap-3">
          <div className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.5)]" />
          <div className="flex flex-col">
            {isExec ? (
              <>
                <span
                  className={`font-bold font-mono text-cyan-400 tracking-wider leading-tight ${
                    isPresent ? 'text-2xl' : 'text-base'
                  }`}
                >
                  POLYMARKET AI 企业智能指挥中心
                </span>
                <span
                  className={`font-mono text-slate-400 tracking-wide ${
                    isPresent ? 'text-sm mt-0.5' : 'text-xs'
                  }`}
                >
                  多智能体协同 · 风险控制 · 实时决策 · 企业自动化
                </span>
              </>
            ) : (
              <>
                <span
                  className={`font-bold font-mono text-cyan-400 tracking-wider leading-tight ${
                    isPresent ? 'text-2xl' : 'text-base'
                  }`}
                >
                  POLYMARKET AI 指挥中心
                </span>
                <span
                  className={`font-mono text-slate-400 tracking-wide ${
                    isPresent ? 'text-sm mt-0.5' : 'text-xs'
                  }`}
                >
                  实时多智能体运行时监控 · 风险审查 · 交易信号编排
                </span>
              </>
            )}
          </div>
          <span className="text-xs font-mono text-slate-500 border border-slate-600/50 px-2 py-0.5 rounded">
            v0.3.0
          </span>

          {/* View Mode Switch */}
          <div className="flex items-center rounded border border-slate-600/30 overflow-hidden ml-2">
            <button
              onClick={() => setViewMode('executive')}
              className={`text-xs font-mono px-2.5 py-0.5 transition-colors ${
                isExec
                  ? 'bg-indigo-500/20 text-indigo-400 border-r border-indigo-500/30'
                  : 'text-slate-500 hover:text-slate-300 border-r border-slate-600/20'
              }`}
            >
              Executive
            </button>
            <button
              onClick={() => setViewMode('engineer')}
              className={`text-xs font-mono px-2.5 py-0.5 transition-colors ${
                !isExec
                  ? 'bg-cyan-500/20 text-cyan-400'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              Engineer
            </button>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Presentation Mode Toggle */}
          <button
            onClick={togglePresentation}
            className={`text-[11px] font-bold font-mono px-2 py-1 rounded border transition-all ${
              isPresent
                ? 'text-cyan-400 bg-cyan-500/15 border-cyan-500/50 shadow-[0_0_8px_rgba(34,211,238,0.3)]'
                : 'text-slate-500 border-slate-700/50 hover:border-cyan-500/30 hover:text-cyan-400'
            }`}
            title={isPresent ? '退出演示模式 (ESC)' : '进入演示模式 (F)'}
          >
            {isPresent ? '■ EXIT' : '◉ PRESENT'}
          </button>
          <span className="text-[11px] font-bold font-mono text-red-400 bg-red-500/10 border border-red-500/30 px-2 py-0.5 rounded tracking-wider">
            ⛔ 只读监控 — 禁止交易
          </span>
          {!isPresent && (
            <>
              <span className="text-[10px] font-mono text-amber-400 bg-amber-500/10 border border-amber-500/30 px-1.5 py-0.5 rounded">
                ◇ 模拟运行监控
              </span>
              {/* Demo mode compact control */}
              <div className="relative">
                <button
                  ref={demoBtnRef}
                  onClick={() => setShowDemoPopover((v) => !v)}
                  className="text-[11px] font-mono text-slate-500 hover:text-cyan-400 border border-slate-700/50 hover:border-cyan-500/30 px-1.5 py-0.5 rounded transition-colors"
                  title="演示模式"
                >
                  ◈ 演示
                </button>

                {showDemoPopover && (
                  <div
                    ref={demoPopoverRef}
                    className="absolute right-0 top-full mt-1.5 w-52 bg-slate-900 border border-slate-700/80 rounded-lg shadow-2xl shadow-black/50 z-50 p-3"
                  >
                    <DemoModeController
                      agentIds={agentIds}
                      selectedId={selectedId}
                      onSelectAgent={(id) => {
                        handleSelectAgent(id)
                      }}
                    />
                  </div>
                )}
              </div>
            </>
          )}
          {/* Auto Demo Toggle */}
          <button
            onClick={toggleAutoDemo}
            className={`text-[11px] font-bold font-mono px-2 py-0.5 rounded border transition-all ${
              demoStatus === 'RUNNING'
                ? 'text-emerald-400 bg-emerald-500/15 border-emerald-500/50 shadow-[0_0_8px_rgba(16,185,129,0.3)] animate-pulse'
                : demoStatus === 'PAUSED'
                  ? 'text-amber-400 bg-amber-500/15 border-amber-500/50'
                  : 'text-slate-500 border-slate-700/50 hover:border-emerald-500/30 hover:text-emerald-400'
            }`}
            title={
              demoStatus === 'RUNNING'
                ? '暂停自动演示'
                : demoStatus === 'PAUSED'
                  ? '恢复自动演示'
                  : '开启自动演示 (D)'
            }
          >
            {demoStatus === 'RUNNING' ? '⬤ AUTO DEMO' : demoStatus === 'PAUSED' ? '▶ AUTO DEMO' : '▶ AUTO DEMO'}
          </button>
          <ClockDisplay presentationMode={isPresent} />
          {demoStatus !== 'OFF' && (
            <span className="text-[10px] font-mono text-slate-300 ml-2 border-l border-emerald-500/40 pl-2">
              NOW PRESENTING<span className="text-emerald-400 font-bold tracking-wider"> · {currentLabel}</span>
            </span>
          )}
        </div>
      </header>

      {/* ══════ ROW 1: KPI HEADER ═══════════════════════ */}
      <KpiHeader
        events={runtimeEvents}
        agentStates={agentStates}
        dashboardKpis={dashboardKpis}
        dashboardSource={dashboardSource}
        presentationMode={isPresent}
        executiveMode={isExec}
        onOpenReport={setSelectedReportId}
      />

      <VisualizationStateSummary
        state={visualizationState.state}
        updatedAt={visualizationState.updatedAt}
        loading={visualizationState.loading}
        error={visualizationState.error}
        onOpenReport={setSelectedReportId}
      />

      {/* ══════ ROW 1.5: EXECUTIVE STRATEGIC SUMMARY (Executive only) ══════ */}
      {isExec && !isPresent && (
        <ExecutiveStrategicSummary
          kpis={dashboardKpis}
          narratives={narratives}
          incidents={incidents}
          regime={dashboardKpis?.regime}
        />
      )}

      {/* ══════ ROW 2: RUNTIME NARRATIVE BANNER (both modes) ═════════ */}
      <RuntimeNarrativeBanner
        events={filteredEvents}
        agentStates={agentStates}
        incidents={incidents}
        kpis={dashboardKpis}
        presentationMode={isPresent}
        onIncidentClick={isExec ? handleNarrativeIncidentClick : undefined}
      />

      {/* ══════ ROW 2.5: SYSTEM METRICS BAR (hidden in executive + presentation) ═══════ */}
      {!isPresent && !isExec && (
        <div className="flex-shrink-0 bg-slate-800/50 border-b border-white/[0.05] h-9">
          <SystemMetricsBar />
        </div>
      )}

      {/* ══════ ROW 3: COMMAND CENTER (Engineer mode only, not presentation) ══════ */}
      {!isPresent && !isExec && (
        <div className="flex-shrink-0">
          <RuntimeCommandCenter
            levelFilter={levelFilter}
            onLevelFilterChange={setLevelFilter}
            agentFilter={agentFilter}
            onAgentFilterChange={setAgentFilter}
            categoryFilters={categoryFilters}
            onCategoryFilterChange={setCategoryFilters}
            searchQuery={searchQuery}
            onSearchQueryChange={setSearchQuery}
            runtimeViewMode={runtimeViewMode}
            onRuntimeViewModeChange={setRuntimeViewMode}
            filteredEvents={filteredEvents}
            source={logSource}
            agents={agentChips}
            onSelectAgent={handleSelectAgent}
          />
        </div>
      )}

      {/* ══════ ROW 4: INCIDENT TIMELINE STRIP (Executive mode, always visible) ══════ */}
      {isExec && !isPresent && (
        <div className="flex-shrink-0 border-b border-slate-700/30 bg-slate-800/20 px-5 py-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold font-mono text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded uppercase tracking-wider">
                Incident 概览
              </span>
              <span className="text-[10px] font-mono text-slate-500">
                点击任意事故进入指挥中心
              </span>
            </div>
            <span className="text-[9px] font-mono text-slate-600">
              {incidents.filter((i) => !i.resolvedTime).length} 进行中 · {incidents.length} 总计
            </span>
          </div>
          <IncidentTimeline
            incidents={incidents}
            onSelectIncident={handleIncidentTimelineClick}
            selectedId={selectedIncidentId}
          />
        </div>
      )}

      {/* ══════ ROW 5: MAIN CONTENT ═════════════════════ */}
      {isExec ? (
        /* ────── EXECUTIVE MODE ────── */
        <div className={`flex-1 overflow-y-auto min-h-0 ${isPresent ? 'presentation-scroll' : ''}`}>
          {/* ROW 1: Strategic Summary + AI Copilot */}
          <div id="demo-kpi" className={currentSectionId === 'demo-kpi' ? 'demo-section-active' : ''}>
            <ExecutiveKpiCards kpis={dashboardKpis} drillDown={drillDown} onDrillDown={setDrillDown} truthBadge={<DataTruthBadge meta={kpiTruthMeta} />} />
          </div>
          <div id="demo-copilot" className="px-4 pb-3">
            <div className="grid grid-cols-2 gap-4">
              <ExecutiveStrategicSummary
                kpis={dashboardKpis}
                narratives={narratives}
                incidents={incidents}
                regime={dashboardKpis?.regime}
              />
              <ExecutiveCopilotPanel
                kpis={dashboardKpis}
                narratives={narratives}
                incidents={incidents}
                regime={dashboardKpis?.regime}
                hasHighVol={hasHighVol}
                isHighCorrelation={isHighCorrelation}
                truthBadge={<DataTruthBadge meta={executiveTruthMeta} />}
              />
            </div>
          </div>

          {/* ROW 1.5: NarrativeFlowGraph (因果链) */}
          <div id="demo-flow" className="px-4 pb-3">
            <NarrativeFlowGraph
              narratives={narratives}
              incidents={incidents}
              events={filteredEvents}
              kpis={dashboardKpis}
              hasHighVol={hasHighVol}
              isHighCorrelation={isHighCorrelation}
              truthBadge={<DataTruthBadge meta={narrativeTruthMeta} />}
            />
          </div>

          {/* ROW 1.8: Executive Scenario Engine 情景推演 */}
          <div id="demo-scenario-engine" className="px-4 pb-3">
            <ExecutiveScenarioEnginePanel
              primaryScenario={primaryScenario}
              candidateScenarios={candidateScenarios}
              selectedScenarioId={selectedScenarioId}
              onSelectScenario={setSelectedScenarioId}
              presentationMode={isPresent}
              truthBadge={<DataTruthBadge meta={executiveTruthMeta} />}
            />
          </div>

          {/* ROW 2: KPI + Business Impact */}
          <div id="demo-business" className="px-4 pb-3">
            <BusinessImpactPanel
              kpis={dashboardKpis}
              incidents={incidents}
              events={filteredEvents}
              truthBadge={<DataTruthBadge meta={kpiTruthMeta} />}
            />
          </div>

          {/* ROW 3: Incident Strip + ResponseActionPanel */}
          <div id="demo-response" className="px-4 pb-3">
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-2xl border border-slate-700/30 bg-gradient-to-b from-slate-800/60 to-slate-900/60 backdrop-blur-sm p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold font-mono text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded uppercase tracking-wider">
                      Incident 概览
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">点击进入指挥中心</span>
                  </div>
                  <span className="text-[9px] font-mono text-slate-600">
                    {unresolvedIncidents} 进行中 · {incidents.length} 总计
                  </span>
                </div>
                <IncidentTimeline
                  incidents={incidents}
                  onSelectIncident={handleIncidentTimelineClick}
                  selectedId={selectedIncidentId}
                />
              </div>
              <ResponseActionPanel
                kpis={dashboardKpis}
                incidents={incidents}
                events={filteredEvents}
                truthBadge={<DataTruthBadge meta={executiveTruthMeta} />}
              />
            </div>
          </div>

          {/* Drill-down detail sections */}
          {drillDown && (
            <div className="px-4 pb-3">
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="rounded-2xl border border-indigo-500/30 bg-gradient-to-b from-indigo-950/40 to-slate-900/60 backdrop-blur-sm p-5"
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-bold text-indigo-300 tracking-wide">
                    {drillDown === 'approval' && '审批通过率专项分析'}
                    {drillDown === 'stability' && '运行时稳定性专项分析'}
                    {drillDown === 'volatility' && '市场波动率专项分析'}
                    {drillDown === 'signals' && '信号吞吐专项分析'}
                    {drillDown === 'risk' && '风险响应专项分析'}
                    {drillDown === 'automation' && '自动化率专项分析'}
                  </h3>
                  <button
                    onClick={() => setDrillDown(null)}
                    className="text-[10px] font-mono text-slate-500 hover:text-slate-300 px-2 py-1 rounded border border-slate-700/50 hover:border-slate-600/50"
                  >
                    收起 ▲
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-4 text-xs font-mono text-slate-400">
                  {drillDown === 'approval' && (
                    <>
                      <div className="p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">当前审批通过率</p>
                        <p className="text-lg font-bold text-emerald-400">{approvalRate}%</p>
                        <p className="text-[9px] text-slate-600 mt-1">{dashboardKpis?.approvedSignals ?? 0} / {dashboardKpis?.totalSignals ?? 0} 信号通过</p>
                      </div>
                      <div className="p-3 rounded-lg border border-amber-500/20 bg-amber-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">风控拦截率</p>
                        <p className="text-lg font-bold text-amber-400">{100 - approvalRate}%</p>
                        <p className="text-[9px] text-slate-600 mt-1">风险控制自动生效中</p>
                      </div>
                      <div className="p-3 rounded-lg border border-cyan-500/20 bg-cyan-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">审批策略</p>
                        <p className="text-sm font-bold text-cyan-400">{approvalRate >= 80 ? '标准审批模式' : '严格审批模式'}</p>
                        <p className="text-[9px] text-slate-600 mt-1">根据风险体制动态调整</p>
                      </div>
                    </>
                  )}
                  {drillDown === 'stability' && (
                    <>
                      <div className="p-3 rounded-lg border border-cyan-500/20 bg-cyan-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">系统异常数</p>
                        <p className="text-lg font-bold text-cyan-400">{dashboardKpis?.errorCount ?? 0}</p>
                        <p className="text-[9px] text-slate-600 mt-1">自动恢复机制已激活</p>
                      </div>
                      <div className="p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">自动重连次数</p>
                        <p className="text-lg font-bold text-emerald-400">{dashboardKpis?.reconnects ?? 0}</p>
                        <p className="text-[9px] text-slate-600 mt-1">WebSocket/REST fallback 切换</p>
                      </div>
                      <div className="p-3 rounded-lg border border-purple-500/20 bg-purple-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">已恢复事故</p>
                        <p className="text-lg font-bold text-purple-400">{incidents.filter((i) => i.resolvedTime).length}</p>
                        <p className="text-[9px] text-slate-600 mt-1">系统自愈能力正常</p>
                      </div>
                    </>
                  )}
                  {drillDown === 'volatility' && (
                    <>
                      <div className="p-3 rounded-lg border border-amber-500/20 bg-amber-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">当前市场体制</p>
                        <p className="text-lg font-bold text-amber-400">{dashboardKpis?.regime || '标准模式'}</p>
                        <p className="text-[9px] text-slate-600 mt-1">基于波动率与相关性推导</p>
                      </div>
                      <div className="p-3 rounded-lg border border-violet-500/20 bg-violet-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">波动率状态</p>
                        <p className="text-lg font-bold text-violet-400">{hasHighVol ? '⚠ 高于基准' : '✓ 正常区间'}</p>
                        <p className="text-[9px] text-slate-600 mt-1">实时监测中</p>
                      </div>
                      <div className="p-3 rounded-lg border border-indigo-500/20 bg-indigo-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">跨市场相关性</p>
                        <p className="text-lg font-bold text-indigo-400">{isHighCorrelation ? '上升趋势' : '正常水平'}</p>
                        <p className="text-[9px] text-slate-600 mt-1">组合分散化效果监测</p>
                      </div>
                    </>
                  )}
                  {drillDown === 'signals' && (
                    <>
                      <div className="p-3 rounded-lg border border-blue-500/20 bg-blue-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">总信号量</p>
                        <p className="text-lg font-bold text-blue-400">{dashboardKpis?.totalSignals?.toLocaleString() ?? '0'}</p>
                        <p className="text-[9px] text-slate-600 mt-1">多 Agent 并行审查</p>
                      </div>
                      <div className="p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">已通过</p>
                        <p className="text-lg font-bold text-emerald-400">{dashboardKpis?.approvedSignals?.toLocaleString() ?? '0'}</p>
                        <p className="text-[9px] text-slate-600 mt-1">风控审核通过</p>
                      </div>
                      <div className="p-3 rounded-lg border border-amber-500/20 bg-amber-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">Agent 集群</p>
                        <p className="text-sm font-bold text-amber-400">{derivedAgentStates.length} Agent 在线</p>
                        <p className="text-[9px] text-slate-600 mt-1">研究 · 风控 · 执行协同</p>
                      </div>
                    </>
                  )}
                  {(drillDown === 'risk' || drillDown === 'automation') && (
                    <>
                      <div className="p-3 rounded-lg border border-amber-500/20 bg-amber-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">端到端延迟</p>
                        <p className="text-lg font-bold text-amber-400">{dashboardKpis && dashboardKpis.errorCount > 2 ? '1250' : '800'}ms</p>
                        <p className="text-[9px] text-slate-600 mt-1">从信号发现到风控响应</p>
                      </div>
                      <div className="p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">自动恢复</p>
                        <p className="text-lg font-bold text-emerald-400">{dashboardKpis?.reconnects ?? 0} 次</p>
                        <p className="text-[9px] text-slate-600 mt-1">系统自愈激活</p>
                      </div>
                      <div className="p-3 rounded-lg border border-cyan-500/20 bg-cyan-500/5">
                        <p className="text-[9px] text-slate-500 mb-1">AI 接管率</p>
                        <p className="text-lg font-bold text-cyan-400">{drillDown === 'automation' ? '84%' : '78%'}</p>
                        <p className="text-[9px] text-slate-600 mt-1">全流程自动化占比</p>
                      </div>
                    </>
                  )}
                </div>
              </motion.div>
            </div>
          )}

          {/* ROW 4: Confidence + AgentTopology + Scenario */}
          <div id="demo-confidence" className={currentSectionId === 'demo-confidence' ? 'demo-section-active' : ''}>
            <ExecutiveRuntimeConfidence events={filteredEvents} incidents={incidents} kpis={dashboardKpis} />
          </div>
          <div id="demo-topology" className={`${isPresent ? 'px-8 pb-4' : 'px-6 pb-3'} ${currentSectionId === 'demo-topology' ? 'demo-section-active' : ''}`}>
            <div className="bg-slate-700/60 border border-slate-500/35 rounded-xl overflow-hidden" style={{ minHeight: isPresent ? '680px' : '560px', height: isPresent ? '680px' : '560px' }}>
              <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
                <div>
                  <h3 className={`font-bold font-mono text-slate-300 uppercase tracking-widest ${isPresent ? 'text-base' : 'text-sm'}`}>
                    Agent 协同价值网络
                  </h3>
                  <p className={`font-mono text-slate-500 mt-0.5 ${isPresent ? 'text-sm' : 'text-xs'}`}>
                    研究 · 风控 · 审核 · 执行 · 学习 — 全链路智能决策
                  </p>
                </div>
              </div>
              <div className="flex-1" style={{ height: 'calc(100% - 52px)', minHeight: isPresent ? '610px' : '500px' }}>
                <AgentTopology
                  selectedId={selectedId}
                  onSelectAgent={handleSelectAgent}
                  agentStates={agentStates}
                  agentActivity={agentActivity}
                  activitySource={activitySource}
                  onRequestExpand={() => setTopologyExpanded(true)}
                />
              </div>
            </div>
          </div>
          <div id="demo-scenarios" className={currentSectionId === 'demo-scenarios' ? 'demo-section-active' : ''}>
            <ExecutiveScenarios />
          </div>
          <div id="demo-roi" className={currentSectionId === 'demo-roi' ? 'demo-section-active' : ''}>
            <ExecutiveRoiPanel />
          </div>
          <div id="demo-dryrun" className={currentSectionId === 'demo-dryrun' ? 'demo-section-active' : ''}>
            <ExecutiveDryRunValidation />
          </div>
          <div id="demo-narrative" className={currentSectionId === 'demo-narrative' ? 'demo-section-active' : ''}>
            <ExecutiveNarrativeStrip />
          </div>
          <div id="demo-keyevents" className={currentSectionId === 'demo-keyevents' ? 'demo-section-active' : ''}>
            <ExecutiveKeyRuntimeEvents events={runtimeEvents} />
          </div>

          {/* Live proof — compact event stream */}
          <div id="demo-feed" className={`${isPresent ? 'px-8 pb-6' : 'px-6 pb-6'} ${currentSectionId === 'demo-feed' ? 'demo-section-active' : ''}`}>
            <div className="bg-slate-800/30 border border-white/[0.06] rounded-xl overflow-hidden">
              <div className="px-4 py-2 border-b border-white/[0.06] flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <span className={`font-mono text-slate-400 uppercase tracking-widest ${isPresent ? 'text-sm' : 'text-xs'}`}>
                  系统实时运行证明
                </span>
                <span className={`font-mono text-slate-400 ml-auto ${isPresent ? 'text-xs' : 'text-xs'}`}>
                  最近 20 条事件
                </span>
              </div>
              <div className={`${isPresent ? 'max-h-48 p-3' : 'max-h-32 p-2'} overflow-y-auto presentation-scroll`}>
                <RuntimeEventFeed
                  events={filteredEvents}
                  source={logSource}
                  onSelectAgent={handleSelectAgent}
                  onSelectEvent={handleSelectEvent}
                  selectedEvent={selectedEvent}
                />
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* ────── ENGINEER (RUNTIME) MODE ────── */
        <div className={`flex flex-1 min-h-[680px] ${isPresent ? 'gap-0' : ''}`}>
          {/* LEFT: Market Data (hidden in presentation) */}
          {!isPresent && (
            <div className="w-48 flex-shrink-0 border-r border-slate-500/25 bg-slate-800/60 flex flex-col min-h-0">
              <div className="p-3 flex-1 overflow-hidden flex flex-col">
                <PanelHeader title="市场数据" />
                <div className="flex-1 overflow-y-auto">
                  <MarketDataPanel />
                </div>
              </div>
            </div>
          )}

          {/* CENTER: Agent Topology */}
          <div className="flex-1 flex flex-col min-h-0 bg-[#16284d]">
            <div className={`flex flex-col flex-1 min-h-0 ${isPresent ? 'p-6' : 'p-3'}`}>
              <div className="flex items-center justify-between mb-2 pb-1.5 border-b border-slate-600/40 flex-shrink-0">
                <h2 className={`font-bold font-mono text-slate-300 uppercase tracking-wider ${isPresent ? 'text-base' : 'text-sm'}`}>
                  Agent 拓扑
                </h2>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setTopologyExpanded(true)}
                    className="text-[10px] font-mono text-slate-500 hover:text-cyan-400 border border-slate-600/40 hover:border-cyan-500/40 px-2 py-0.5 rounded transition-colors"
                    title="全屏拓扑"
                  >
                    🔍 全屏拓扑
                  </button>
                  {isPresent && (
                    <span className="text-[9px] font-mono text-cyan-400 bg-cyan-500/10 px-1.5 py-0.5 rounded border border-cyan-500/20">
                      PRESENTATION
                    </span>
                  )}
                </div>
              </div>
              <div className="flex-1 min-h-[500px]">
                <AgentTopology
                  selectedId={selectedId}
                  onSelectAgent={handleSelectAgent}
                  agentStates={agentStates}
                  agentActivity={agentActivity}
                  activitySource={activitySource}
                  onRequestExpand={() => setTopologyExpanded(true)}
                />
              </div>
            </div>
          </div>

          {/* RIGHT: Signal Review + Risk (hidden in presentation) */}
          {!isPresent && (
            <div className="w-64 flex-shrink-0 border-l border-slate-500/25 bg-slate-800/60 flex flex-col min-h-0">
              {/* Signal Review */}
              <div className="flex-[2] min-h-0 p-3 flex flex-col border-b border-white/[0.03]">
                <PanelHeader title="信号审查" />
                <div className="flex-1 overflow-y-auto">
                  <SignalReviewPanel
                    onSelectSignal={handleSelectSignal}
                    selectedSignal={selectedSignal}
                  />
                </div>
              </div>

              {/* Risk Control — always visible */}
              <div className="flex-1 min-h-0 p-3 flex flex-col border-b border-white/[0.03]">
                <PanelHeader title="风险控制" />
                <div className="flex-1 overflow-y-auto">
                  <RiskControlPanel />
                </div>
              </div>

              {/* Agent Runtime Inspector — replaces old Agent Detail */}
              <div className="flex-[1.8] min-h-0 flex flex-col">
                <AgentRuntimeInspector
                  agent={selectedAgent ? {
                    id: selectedAgent.id,
                    name: selectedAgent.name,
                    layer: selectedAgent.layer,
                    status: selectedAgent.status,
                    currentTask: selectedAgent.currentTask,
                    latencyMs: selectedAgent.latencyMs,
                    tokensUsed: selectedAgent.tokensUsed,
                    llmCalls: selectedAgent.llmCalls,
                    cacheHit: selectedAgent.cacheHit,
                    queueSize: selectedAgent.queueSize,
                    successRate: selectedAgent.successRate,
                  } : null}
                  agentRuntimeState={selectedAgentRuntimeState}
                  selectedEvent={selectedEvent}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══════ BOTTOM PANEL: Runtime Logs (always visible in presentation) ══════ */}
      {isPresent ? (
        <div className="flex-shrink-0 border-t border-slate-800/60 bg-slate-900/30 flex h-56 presentation-bottom-anchor">
          <div className="flex-1 min-w-0 p-4 flex flex-col">
            <RuntimeLogPanel presentationMode={true} events={filteredEvents} source={logSource} />
          </div>
        </div>
      ) : (
        <>
          {/* ══════ BOTTOM PANEL TOGGLE BAR (Engineer only) ══════════════════ */}
          {!isExec && (
            <>
              <div className="flex-shrink-0 border-t border-white/[0.07] bg-slate-800/80 debug-toggle-bar">
                <button
                  onClick={() => setShowDebug((v) => !v)}
                  className="w-full flex items-center justify-center gap-2 px-4 py-1.5 text-xs font-mono text-slate-400 hover:text-cyan-400 hover:bg-slate-700/40 transition-colors"
                  aria-label={showDebug ? 'Collapse debug panels' : 'Expand debug panels'}
                >
                  <span>{showDebug ? '▲ 收起调试面板' : '▼ 展开调试面板'}</span>
                </button>
              </div>

              {/* ══════ ROW 4: TIMELINE + EVENT STREAM ══════ */}
              {showDebug && (
                <div className="flex-shrink-0 border-t border-white/[0.04] bg-slate-900/25 flex h-52 debug-panels-area opacity-90">
                  {/* DryRun Timeline */}
                  <div className="w-[40%] min-w-0 p-3 flex flex-col border-r border-white/[0.03]">
                    <PanelHeader title="模拟执行时间轴" />
                    <div className="flex-1 overflow-y-auto">
                      <DryRunTimeline realData={realData} />
                    </div>
                  </div>

                  {/* Runtime Execution Timeline */}
                  <div className="w-[30%] min-w-0 p-3 flex flex-col border-r border-white/[0.03]">
                    <RuntimeTimelineView timelines={runtimeTimelines} />
                  </div>

                  {/* Live Event Stream */}
                  <div className="flex-1 min-w-0 p-3 flex flex-col">
                    <RuntimeEventFeed
                      events={filteredEvents}
                      source={logSource}
                      onSelectAgent={handleSelectAgent}
                      onSelectEvent={handleSelectEvent}
                      selectedEvent={selectedEvent}
                    />
                  </div>
                </div>
              )}

              {/* ══════ ROW 5: SYSTEM HEALTH + LOGS ══ */}
              {showDebug && (
                <div className="flex-shrink-0 border-t border-slate-800/50 bg-slate-900/25 flex h-40 debug-panels-area opacity-90">
                  {/* System Health */}
                  <div className="w-64 flex-shrink-0 p-3 flex flex-col border-r border-slate-800/60">
                    <SystemHealthPanel events={runtimeEvents} agentStates={agentStates} sseConnected={sseConnected} />
                  </div>

                  {/* Runtime Logs */}
                  <div className="flex-1 min-w-0 p-3 flex flex-col">
                    <PanelHeader title="运行日志" />
                    <div className="flex-1 overflow-hidden">
                      <RuntimeLogPanel events={filteredEvents} source={logSource} />
                    </div>
                  </div>
                </div>
              )}

              {/* ══════ ROW 6: 事故复盘 & Replay ═══════════════ */}
              {showDebug && (
                <div className="flex-shrink-0 border-t border-slate-800/50 bg-slate-900/25 flex h-48 debug-panels-area opacity-90">
                  {/* Incident Timeline — 事故列表 */}
                  <div className="w-72 flex-shrink-0 p-3 flex flex-col border-r border-slate-800/60">
                    <div className="flex items-center mb-2 pb-1.5 border-b border-slate-700/50 flex-shrink-0">
                      <h2 className="text-[11px] font-bold font-mono text-slate-400 uppercase tracking-widest">事故复盘</h2>
                      <span className="ml-auto text-[9px] font-mono text-slate-600">{incidents.length} 起事故</span>
                    </div>
                    <div className="flex-1 overflow-y-auto">
                      <IncidentTimeline
                        incidents={incidents}
                        onSelectIncident={(incident) => setSelectedIncidentId(incident.id)}
                        selectedId={selectedIncidentId}
                      />
                    </div>
                  </div>

                  {/* Replay Panel — 复盘播放器 */}
                  <div className="flex-1 min-w-0 p-3 flex flex-col">
                    <div className="flex items-center mb-2 pb-1.5 border-b border-slate-700/50 flex-shrink-0">
                      <h2 className="text-[11px] font-bold font-mono text-slate-400 uppercase tracking-widest">运行复盘</h2>
                      {selectedIncident && (
                        <span className="ml-2 text-[9px] font-mono text-slate-500 truncate max-w-xs">
                          {selectedIncident.title}
                        </span>
                      )}
                      {replayMode !== 'stopped' && (
                        <span className="ml-auto text-[9px] font-mono text-cyan-400">
                          {replayIndex + 1}/{replayEvents.length}
                        </span>
                      )}
                    </div>

                    {!selectedIncident ? (
                      <div className="flex-1 flex items-center justify-center">
                        <span className="text-[10px] font-mono text-slate-600">← 选择事故以开始复盘</span>
                      </div>
                    ) : (
                      <div className="flex-1 flex flex-col min-h-0">
                        {/* 事故信息网格：根因 + 影响范围 + 恢复耗时 */}
                        {(() => {
                          const rootCause = selectedIncident.summary
                          const affectedCount = selectedIncident.affectedAgents.length
                          const isOngoing = selectedIncident.resolvedTime == null
                          const durationMs = selectedIncident.durationMs
                          const durationSec = Math.round(durationMs / 1000)
                          const durationDisplay =
                            durationSec < 120
                              ? `${durationSec}s`
                              : durationSec < 3600
                                ? `${Math.round(durationSec / 60)}m`
                                : `${Math.round(durationSec / 3600)}h`
                          return (
                            <div className="grid grid-cols-3 gap-1.5 mb-2 flex-shrink-0">
                              <div className="p-1.5 rounded border border-slate-700/40 bg-slate-900/50">
                                <div className="text-[8px] font-mono text-slate-500 mb-0.5">根因摘要</div>
                                <div className="text-[9px] font-mono text-slate-300 leading-snug line-clamp-2" title={rootCause}>
                                  {rootCause && rootCause.length > 40 ? rootCause.slice(0, 40) + '…' : (rootCause || '分析中')}
                                </div>
                              </div>
                              <div className="p-1.5 rounded border border-slate-700/40 bg-slate-900/50">
                                <div className="text-[8px] font-mono text-slate-500 mb-0.5">影响范围</div>
                                <div className="text-[9px] font-mono text-amber-400">
                                  {affectedCount > 0 ? `${affectedCount} 个 Agent` : '无'}
                                </div>
                              </div>
                              <div className="p-1.5 rounded border border-slate-700/40 bg-slate-900/50">
                                <div className="text-[8px] font-mono text-slate-500 mb-0.5">恢复耗时</div>
                                <div className={`text-[9px] font-mono ${isOngoing ? 'text-amber-400' : 'text-emerald-400'}`}>
                                  {isOngoing ? '进行中' : durationDisplay}
                                </div>
                              </div>
                            </div>)
                        })()}

                        {/* AI 自动处置说明 */}
                        {selectedIncident.recommendations.length > 0 && (
                          <div className="mb-2 p-1.5 rounded border border-cyan-500/20 bg-cyan-500/5 flex-shrink-0">
                            <div className="flex items-center gap-1 mb-0.5">
                              <span className="text-[8px] font-mono text-cyan-400/60 uppercase tracking-wider">AI 自动处置</span>
                            </div>
                            <div className="text-[9px] font-mono text-slate-400 leading-snug line-clamp-2">
                              {selectedIncident.recommendations[0]}
                            </div>
                          </div>
                        )}

                        {/* 当前回放事件 */}
                        {currentReplayEvent && replayMode !== 'stopped' && (
                          <div className="mb-2 p-1.5 rounded border border-cyan-500/30 bg-cyan-500/5 flex-shrink-0">
                            <div className="flex items-center gap-1.5">
                              <span className="text-[9px] font-mono text-slate-500">
                                {new Date(currentReplayEvent.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}
                              </span>
                              <span className="text-[9px] font-mono text-slate-600 bg-slate-800/50 px-1 rounded">
                                {currentReplayEvent.agent}
                              </span>
                              <span className="text-[10px] font-mono text-slate-300 leading-tight line-clamp-1">
                                {currentReplayEvent.title}
                              </span>
                            </div>
                          </div>
                        )}

                        {/* 进度条 */}
                        {replayMode !== 'stopped' && (
                          <div className="mb-2 flex-shrink-0">
                            <div className="flex items-center justify-between text-[9px] font-mono text-slate-500 mb-0.5">
                              <span>复盘进度</span>
                              <span>{Math.round(replayProgress)}%</span>
                            </div>
                            <div className="w-full h-1 bg-slate-800 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-cyan-500 transition-all duration-300"
                                style={{ width: `${replayProgress}%` }}
                              />
                            </div>
                          </div>
                        )}

                        {/* 阶段提示 */}
                        {currentReplayEvent && replayMode !== 'stopped' && (
                          <div className="mb-2 text-[9px] font-mono text-cyan-400 flex-shrink-0">
                            当前阶段：{currentReplayEvent.title}
                          </div>
                        )}

                        {/* 空白占位 */}
                        <div className="flex-1" />

                        {/* Replay 控件 */}
                        <div className="flex items-center gap-1 flex-shrink-0 pt-1 border-t border-slate-700/30">
                          {/* 步骤控制 */}
                          <button
                            onClick={stepBackward}
                            disabled={replayMode !== 'paused'}
                            className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-slate-600/50 text-slate-400 hover:border-slate-500 hover:text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            title="上一步（暂停时可用）"
                          >
                            ◀◀
                          </button>
                          <button
                            onClick={stepForward}
                            disabled={replayMode !== 'paused'}
                            className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-slate-600/50 text-slate-400 hover:border-slate-500 hover:text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            title="下一步（暂停时可用）"
                          >
                            ▶▶
                          </button>

                          <span className="w-px h-4 bg-slate-700/50 mx-0.5" />

                          {/* 播放控制 */}
                          {replayMode === 'stopped' || replayMode === 'paused' ? (
                            <button
                              onClick={replayMode === 'paused' ? resumeReplay : startReplay}
                              className="text-[10px] font-mono px-2 py-0.5 rounded border border-emerald-600/50 text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 transition-colors"
                              title={replayMode === 'paused' ? '继续' : '开始回放'}
                            >
                              {replayMode === 'paused' ? '继续' : '▶ 开始回放'}
                            </button>
                          ) : (
                            <button
                              onClick={pauseReplay}
                              className="text-[10px] font-mono px-2 py-0.5 rounded border border-amber-600/50 text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 transition-colors"
                              title="暂停"
                            >
                              ⏸ 暂停
                            </button>
                          )}

                          <button
                            onClick={stopReplay}
                            disabled={replayMode === 'stopped'}
                            className="text-[10px] font-mono px-2 py-0.5 rounded border border-red-600/50 text-red-400 hover:bg-red-500/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            title="停止"
                          >
                            ■ 停止
                          </button>

                          <span className="w-px h-4 bg-slate-700/50 mx-0.5" />

                          {/* 回放速度 */}
                          <span className="text-[9px] font-mono text-slate-600 ml-0.5">回放速度</span>
                          {([1, 2, 5] as const).map((speed) => (
                            <button
                              key={speed}
                              onClick={() => setReplaySpeed(speed)}
                              className={`text-[9px] font-mono px-1.5 py-0.5 rounded border transition-colors ${
                                replaySpeed === speed
                                  ? 'border-cyan-500/50 text-cyan-400 bg-cyan-500/10'
                                  : 'border-slate-600/40 text-slate-500 hover:border-slate-500 hover:text-slate-400'
                              }`}
                              title={`${speed}×`}
                            >
                              {speed}×
                            </button>
                          ))}
                        </div>

                        {/* 完整建议列表 */}
                        {selectedIncident.recommendations.length > 1 && (
                          <div className="mt-2 pt-1.5 border-t border-slate-700/30 flex-shrink-0">
                            <span className="text-[9px] font-mono text-amber-400/60 mb-1 block">处置建议</span>
                            {selectedIncident.recommendations.slice(1).map((rec, idx) => (
                              <div key={idx} className="text-[9px] font-mono text-amber-400/80 leading-snug line-clamp-1">
                                · {rec}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {/* Executive mode bottom: Incident Command Center trigger + live proof */}
          {isExec && (
            <div className="flex-shrink-0 border-t border-slate-700/30 bg-slate-800/30 px-5 py-2 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-[9px] font-mono text-slate-500">
                  事故总数: {incidents.length} · 进行中: {incidents.filter((i) => !i.resolvedTime).length}
                </span>
                {selectedIncident && (
                  <button
                    onClick={() => openIncidentCommand(selectedIncident.id)}
                    className="text-[10px] font-bold font-mono px-3 py-1 rounded border border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors"
                  >
                    ⚡ 打开事故指挥中心
                  </button>
                )}
              </div>
              <span className="text-[9px] font-mono text-slate-600">
                {isExec ? 'Executive View' : 'Engineer View'} · v0.3.0
              </span>
            </div>
          )}
        </>
      )}

      {/* ══════ INCIDENT COMMAND CENTER OVERLAY ═══════════════════ */}
      {incidentCommandOpen && commandIncident && (
        <IncidentCommandCenter
          incident={commandIncident}
          onClose={closeIncidentCommand}
          agentStates={agentStates}
          replayMode={replayMode}
          replaySpeed={replaySpeed}
          replayIndex={replayIndex}
          replayProgress={replayProgress}
          replayEvents={replayEvents}
          currentReplayEvent={currentReplayEvent}
          startReplay={startReplay}
          pauseReplay={pauseReplay}
          resumeReplay={resumeReplay}
          stopReplay={stopReplay}
          stepForward={stepForward}
          stepBackward={stepBackward}
          setReplaySpeed={setReplaySpeed}
        />
      )}

      {/* ══════ AGENT TOPOLOGY FULL-SCREEN MODAL ════════════ */}
      <AgentTopologyModal
        open={topologyExpanded}
        onClose={() => setTopologyExpanded(false)}
        selectedId={selectedId}
        onSelectAgent={setSelectedId}
        agentStates={agentStates}
        agentActivity={agentActivity}
        activitySource={activitySource}
        onToggleLayer={() => {}}
      />

      <StatusReportModal
        reportId={selectedReportId}
        onClose={() => setSelectedReportId(null)}
        dashboardKpis={dashboardKpis}
        visualizationState={visualizationState.state}
        agentStates={agentStates}
        runtimeEvents={runtimeEvents}
        filteredEvents={filteredEvents}
      />
    </div>
  )
}
