'use client'

import { useState, useCallback, useMemo } from 'react'
import type { ExecutiveScenario, ScenarioSeverity } from '../lib/executiveScenarioEngine'
import { motion, AnimatePresence } from 'framer-motion'

interface Props {
  primaryScenario: ExecutiveScenario | null
  candidateScenarios: ExecutiveScenario[]
  selectedScenarioId: string | null
  onSelectScenario: (id: string) => void
  presentationMode: boolean
  truthBadge?: React.ReactNode
}

// ── Severity Config ─────────────────────────────────────────

const severityConfig: Record<ScenarioSeverity, { label: string; bg: string; border: string; text: string; glow: string }> = {
  critical: {
    label: '严重',
    bg: 'bg-red-950/60',
    border: 'border-red-500/40',
    text: 'text-red-300',
    glow: 'shadow-[0_0_30px_rgba(239,68,68,0.3)]',
  },
  high: {
    label: '高',
    bg: 'bg-amber-950/60',
    border: 'border-amber-500/40',
    text: 'text-amber-300',
    glow: 'shadow-[0_0_20px_rgba(245,158,11,0.25)]',
  },
  moderate: {
    label: '中',
    bg: 'bg-cyan-950/60',
    border: 'border-cyan-500/40',
    text: 'text-cyan-300',
    glow: 'shadow-[0_0_15px_rgba(6,182,212,0.2)]',
  },
  low: {
    label: '低',
    bg: 'bg-blue-950/60',
    border: 'border-blue-500/40',
    text: 'text-blue-300',
    glow: 'shadow-[0_0_10px_rgba(59,130,246,0.15)]',
  },
  normal: {
    label: '正常',
    bg: 'bg-emerald-950/60',
    border: 'border-emerald-500/40',
    text: 'text-emerald-300',
    glow: 'shadow-[0_0_12px_rgba(16,185,129,0.15)]',
  },
}

const kindLabelMap: Record<string, string> = {
  market_crash: '极端市场',
  data_outage: '数据异常',
  high_volatility: '高波动',
  liquidity_drop: '流动性下降',
  risk_lockdown: '风险锁定',
  agent_recovery: 'Agent 恢复',
  normal_operations: '常规运营',
}

// ── Timeline Dot ────────────────────────────────────────────

function TimelineDot({ status }: { status: 'completed' | 'in_progress' | 'pending' }) {
  if (status === 'completed') {
    return (
      <div className="flex-shrink-0 w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
    )
  }
  if (status === 'in_progress') {
    return (
      <div className="flex-shrink-0 w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse shadow-[0_0_8px_rgba(245,158,11,0.5)]" />
    )
  }
  return <div className="flex-shrink-0 w-2.5 h-2.5 rounded-full bg-slate-600" />
}

// ── Main Component ──────────────────────────────────────────

export default function ExecutiveScenarioEnginePanel({
  primaryScenario,
  candidateScenarios,
  selectedScenarioId,
  onSelectScenario,
  presentationMode,
  truthBadge,
}: Props) {
  const currentScenarioId = selectedScenarioId || primaryScenario?.scenarioId || null
  const activeScenario = useMemo(
    () => candidateScenarios.find((s) => s.scenarioId === currentScenarioId) || primaryScenario,
    [candidateScenarios, currentScenarioId, primaryScenario],
  )

  const [selectedTab, setSelectedTab] = useState<'summary' | 'ai' | 'impact' | 'timeline'>('summary')

  const handleScenarioClick = useCallback(
    (id: string) => {
      onSelectScenario(id)
    },
    [onSelectScenario],
  )

  const isPrimary = activeScenario?.scenarioId === primaryScenario?.scenarioId

  const sev = severityConfig[activeScenario?.severity || 'normal']

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className={`${sev.bg} border ${sev.border} rounded-2xl ${sev.glow} overflow-hidden relative ${
        presentationMode ? 'mx-2' : 'mx-4'
      }`}
    >
      {/* Truth Badge */}
      {truthBadge && <div className="absolute top-3 right-4 z-10">{truthBadge}</div>}

      {/* Header */}
      <div className="px-5 pt-4 pb-2">
        <div className="flex items-center gap-2">
          <span
            className={`text-[10px] font-bold font-mono px-1.5 py-0.5 rounded uppercase tracking-wider ${sev.text} ${sev.text.replace('text-', 'bg-').replace('300', '500/15')} border-current/20 border`}
          >
            {kindLabelMap[activeScenario?.kind || 'normal_operations'] || '常规'}
          </span>
          <span
            className={`text-[10px] font-bold font-mono px-1.5 py-0.5 rounded uppercase tracking-wider ${sev.text} ${sev.text.replace('text-', 'bg-').replace('300', '500/15')} border-current/20 border`}
          >
            {sev.label} 风险
          </span>
          {isPrimary && (
            <span className="text-[9px] font-mono text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 px-1.5 py-0.5 rounded uppercase tracking-wider">
              当前情景
            </span>
          )}
        </div>

        <h2
          className={`mt-2 font-bold tracking-tight leading-tight ${presentationMode ? 'text-2xl' : 'text-lg'} text-white`}
        >
          {activeScenario?.title || '情景推演'}
        </h2>
      </div>

      {/* Scenario Tabs */}
      <div className="px-5 pb-2 flex items-center gap-1 overflow-x-auto">
        {candidateScenarios.map((s) => {
          const sk = severityConfig[s.severity]
          const isActive = s.scenarioId === currentScenarioId
          return (
            <button
              key={s.scenarioId}
              onClick={() => handleScenarioClick(s.scenarioId)}
              className={`text-[11px] font-mono px-2.5 py-1 rounded-lg border whitespace-nowrap transition-all ${
                isActive
                  ? `${sk.bg} ${sk.border} ${sk.text} ${sk.glow.replace('shadow', 'shadow-sm').replace('0_0', '0_1')}`
                  : 'bg-slate-800/40 border-slate-700/40 text-slate-400 hover:border-slate-600/60 hover:text-slate-300'
              }`}
            >
              {kindLabelMap[s.kind] || s.kind}
            </button>
          )
        })}
        {!presentationMode && candidateScenarios.length === 1 && (
          <span className="text-[10px] font-mono text-slate-600 ml-2">仅当前情景可用</span>
        )}
      </div>

      {/* Sub-tabs */}
      {activeScenario && (
        <div className="px-5 pb-1 flex items-center gap-3 border-b border-white/[0.06]">
          {(['summary', 'ai', 'impact', 'timeline'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setSelectedTab(tab)}
              className={`text-[11px] font-mono pb-2 border-b-2 transition-colors ${
                selectedTab === tab
                  ? `${sev.text} border-current`
                  : 'text-slate-500 border-transparent hover:text-slate-400'
              }`}
            >
              {tab === 'summary' && '情景概述'}
              {tab === 'ai' && 'AI 响应'}
              {tab === 'impact' && '业务影响'}
              {tab === 'timeline' && '时间线'}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      <AnimatePresence>
        <motion.div
          key={`${activeScenario?.scenarioId}-${selectedTab}`}
          initial={{ opacity: 0, x: 4 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -4 }}
          transition={{ duration: 0.25 }}
          className="px-5 py-4 space-y-4"
        >
          {!activeScenario && (
            <div className="text-slate-500 text-sm font-mono py-6 text-center">
              AI 正在分析当前市场状况，生成战略情景推演...
            </div>
          )}

          {activeScenario && selectedTab === 'summary' && (
            <div className="space-y-4">
              <div>
                <div className="text-[11px] font-bold font-mono text-slate-400 uppercase tracking-wider mb-1">
                  情景摘要
                </div>
                <p className={`${presentationMode ? 'text-base' : 'text-sm'} text-slate-200 leading-relaxed`}>
                  {activeScenario.executiveSummary}
                </p>
              </div>
              <div>
                <div className="text-[11px] font-bold font-mono text-slate-400 uppercase tracking-wider mb-1">
                  经营风险评估
                </div>
                <p className={`${presentationMode ? 'text-base' : 'text-sm'} text-slate-300 leading-relaxed`}>
                  {activeScenario.businessRisk}
                </p>
              </div>
              <div>
                <div className="text-[11px] font-bold font-mono text-slate-400 uppercase tracking-wider mb-1">
                  建议动作
                </div>
                <p className={`${presentationMode ? 'text-base' : 'text-sm'} text-amber-200 leading-relaxed font-medium`}>
                  {activeScenario.recommendedAction}
                </p>
              </div>
              <div className="flex items-center gap-4 text-[11px] font-mono text-slate-500">
                <span>
                  置信度：<span className={sev.text}>{activeScenario.confidence}%</span>
                </span>
                <span>
                  影响模块：
                  <span className="text-slate-400">
                    {activeScenario.affectedModules.slice(0, 3).join(' · ')}
                    {activeScenario.affectedModules.length > 3
                      ? ` +${activeScenario.affectedModules.length - 3}`
                      : ''}
                  </span>
                </span>
              </div>
            </div>
          )}

          {activeScenario && selectedTab === 'ai' && (
            <div className="space-y-4">
              <div>
                <div className="text-[11px] font-bold font-mono text-slate-400 uppercase tracking-wider mb-1">
                  AI 自动响应路径
                </div>
                <p
                  className={`${presentationMode ? 'text-base' : 'text-sm'} text-slate-200 leading-relaxed whitespace-pre-line`}
                >
                  {activeScenario.aiResponse}
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {activeScenario.affectedModules.map((mod) => (
                  <span
                    key={mod}
                    className={`text-[10px] font-mono px-2 py-0.5 rounded border ${sev.bg} ${sev.border} ${sev.text}`}
                  >
                    {mod}
                  </span>
                ))}
              </div>
            </div>
          )}

          {activeScenario && selectedTab === 'impact' && (
            <div className="space-y-4">
              <div>
                <div className="text-[11px] font-bold font-mono text-slate-400 uppercase tracking-wider mb-1">
                  预期业务影响
                </div>
                <p className={`${presentationMode ? 'text-base' : 'text-sm'} text-slate-200 leading-relaxed`}>
                  {activeScenario.expectedImpact}
                </p>
              </div>
              <div className={`rounded-xl ${sev.bg} border ${sev.border} p-3`}>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono text-slate-400">AI 置信度</span>
                  <span className={`text-lg font-bold font-mono ${sev.text}`}>
                    {activeScenario.confidence}%
                  </span>
                </div>
                <div className="mt-1 w-full bg-slate-700/50 rounded-full h-1.5">
                  <div
                    className={`h-full rounded-full transition-all ${
                      activeScenario.confidence >= 90
                        ? 'bg-emerald-500'
                        : activeScenario.confidence >= 70
                          ? 'bg-amber-500'
                          : 'bg-red-500'
                    }`}
                    style={{ width: `${activeScenario.confidence}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {activeScenario && selectedTab === 'timeline' && (
            <div className="space-y-0">
              <div className="text-[11px] font-bold font-mono text-slate-400 uppercase tracking-wider mb-3">
                AI 响应时间线
              </div>
              <div className="relative pl-4 border-l border-slate-700/50 space-y-3">
                {activeScenario.timelineSteps.map((step, i) => (
                  <div key={i} className="relative flex items-start gap-3">
                    <div className="absolute -left-[6px] top-1.5">
                      <TimelineDot status={step.status} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-bold font-mono text-slate-500">{step.timeOffset}</span>
                        <span
                          className={`text-[9px] font-mono uppercase tracking-wider ${
                            step.status === 'completed'
                              ? 'text-emerald-500'
                              : step.status === 'in_progress'
                                ? 'text-amber-400'
                                : 'text-slate-600'
                          }`}
                        >
                          {step.status === 'completed' ? '已完成' : step.status === 'in_progress' ? '执行中' : '待执行'}
                        </span>
                      </div>
                      <p className={`${presentationMode ? 'text-sm' : 'text-xs'} text-slate-300 mt-0.5 leading-relaxed`}>
                        {step.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      {/* Confidence bar at bottom */}
      {activeScenario && (
        <div className="px-5 pb-4 pt-1">
          <div className="flex items-center gap-2 text-[10px] font-mono text-slate-600">
            <span>情景置信度</span>
            <div className="flex-1 h-0.5 bg-slate-700/40 rounded-full">
              <div
                className={`h-full rounded-full transition-all ${
                  activeScenario.confidence >= 90
                    ? 'bg-emerald-500'
                    : activeScenario.confidence >= 70
                      ? 'bg-amber-500'
                      : 'bg-red-500'
                }`}
                style={{ width: `${activeScenario.confidence}%` }}
              />
            </div>
            <span className={sev.text}>{activeScenario.confidence}%</span>
          </div>
        </div>
      )}
    </motion.div>
  )
}
