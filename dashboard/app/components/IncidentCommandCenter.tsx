'use client'

import { useEffect, useCallback, useRef, useState, useMemo } from 'react'
import type { Incident, IncidentPhase, IncidentPhaseEvent } from '../hooks/useIncidents'
import type { LogEvent } from '../hooks/useLogEvents'
import type { AgentRuntimeStatus } from '../data/types'

// ── Type aliases matching useIncidents runtime types ──────────
type ReplayMode = 'stopped' | 'playing' | 'paused'
type ReplaySpeed = 1 | 2 | 5

// ── Color / label constants ──────────────────────────────────
const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#3b82f6',
}
const SEVERITY_LABELS: Record<string, string> = {
  critical: '严重', high: '高', medium: '中', low: '低',
}
const PHASE_COLORS: Record<IncidentPhase, string> = {
  start: '#f97316', escalation: '#ef4444', mitigation: '#eab308',
  recovery: '#3b82f6', resolved: '#22c55e',
}
const PHASE_LABELS: Record<IncidentPhase, string> = {
  start: '触发', escalation: '升级', mitigation: '缓解',
  recovery: '恢复', resolved: '已解决',
}

function fmtTime(ts: string): string {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })
}
function fmtDuration(ms: number): string {
  const sec = Math.round(ms / 1000)
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.round(sec / 60)}m`
  return `${(sec / 3600).toFixed(1)}h`
}

// ── AI narrative generator for replay events ─────────────────
function aiNarrativeText(phase: IncidentPhase, event: LogEvent): string {
  const p = PHASE_LABELS[phase]
  const agent = event.agent.toUpperCase()
  const detail = event.detail || event.title
  return `[${p}] ${agent} — ${detail}`
}

// ═══════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════

interface Props {
  incident: Incident
  onClose: () => void
  agentStates: AgentRuntimeStatus[]
  // Replay hooks
  replayMode: ReplayMode
  replaySpeed: ReplaySpeed
  replayIndex: number
  replayProgress: number
  replayEvents: LogEvent[]
  currentReplayEvent: LogEvent | null
  startReplay: () => void
  pauseReplay: () => void
  resumeReplay: () => void
  stopReplay: () => void
  stepForward: () => void
  stepBackward: () => void
  setReplaySpeed: (s: ReplaySpeed) => void
}

export default function IncidentCommandCenter({
  incident,
  onClose,
  agentStates,
  replayMode, replaySpeed, replayIndex, replayProgress,
  replayEvents, currentReplayEvent,
  startReplay, pauseReplay, resumeReplay, stopReplay,
  stepForward, stepBackward, setReplaySpeed,
}: Props) {
  const overlayRef = useRef<HTMLDivElement>(null)
  const timelineRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [activeTab, setActiveTab] = useState<'timeline' | 'events' | 'agents' | 'risk'>('timeline')

  // ESC to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        stopReplay()
        onClose()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, stopReplay])

  // Click outside to close
  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === overlayRef.current) {
        stopReplay()
        onClose()
      }
    },
    [onClose, stopReplay],
  )

  // Auto-scroll timeline
  useEffect(() => {
    if (autoScroll && timelineRef.current) {
      const el = timelineRef.current
      const activeEl = el.querySelector('[data-active="true"]')
      if (activeEl) {
        activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
      }
    }
  }, [replayIndex, autoScroll])

  const isPlaying = replayMode === 'playing'
  const isPaused = replayMode === 'paused'
  const isStopped = replayMode === 'stopped'
  const isActive = !incident.resolvedTime
  const sevColor = SEVERITY_COLORS[incident.severity] ?? '#64748b'
  const sevLabel = SEVERITY_LABELS[incident.severity] ?? incident.severity

  // ── Agent activation during incident ───────────────────────
  const incidentAgents = useMemo(() => {
    const affected = new Set(incident.affectedAgents)
    return agentStates.filter((a) => affected.has(a.agent))
  }, [incident.affectedAgents, agentStates])

  // ── Risk state evolution (from incident events) ────────────
  const riskEvolution = useMemo(() => {
    return incident.events
      .filter(
        (e) =>
          e.category === 'stoploss' ||
          e.category === 'drawdown' ||
          e.category === 'connection' ||
          e.category === 'recovery' ||
          e.level === 'ERROR' ||
          e.level === 'WARN',
      )
      .slice(0, 8)
  }, [incident.events])

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-[100] bg-black/75 backdrop-blur-md flex items-center justify-center animate-in fade-in duration-200"
    >
      <div
        className="w-[95vw] h-[92vh] bg-slate-900 border border-slate-700/60 rounded-2xl shadow-2xl shadow-black/60 flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ══════════ HEADER ═══════════════════════════════════ */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700/50 bg-slate-800/60 flex-shrink-0">
          <div className="flex items-center gap-4">
            {/* Status pulse */}
            <div className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full shadow-[0_0_12px_currentColor]"
                style={{
                  backgroundColor: sevColor,
                  color: sevColor,
                }}
              />
              <span className="text-xs font-bold font-mono uppercase tracking-widest text-slate-200">
                事故指挥中心
              </span>
            </div>
            <span className="text-slate-600">|</span>
            <span className="text-sm font-bold font-mono text-slate-100">{incident.title}</span>
          </div>

          <div className="flex items-center gap-3">
            {/* Severity + Status badges */}
            <span
              className="text-[10px] font-bold font-mono px-2 py-1 rounded border uppercase"
              style={{ color: sevColor, borderColor: sevColor + '40', backgroundColor: sevColor + '10' }}
            >
              {sevLabel} 严重度
            </span>
            <span
              className="text-[10px] font-bold font-mono px-2 py-1 rounded border"
              style={{
                color: isActive ? '#ef4444' : '#22c55e',
                borderColor: isActive ? '#ef444440' : '#22c55e40',
                backgroundColor: isActive ? '#ef444410' : '#22c55e10',
              }}
            >
              {isActive ? '● 进行中' : '✓ 已解决'}
            </span>
            <button
              onClick={() => { stopReplay(); onClose() }}
              className="text-sm font-mono text-slate-400 hover:text-slate-200 transition-colors ml-4"
              title="关闭 (ESC)"
            >
              ✕
            </button>
          </div>
        </div>

        {/* ══════════ INCIDENT INFO BAR ════════════════════════ */}
        <div className="grid grid-cols-5 gap-0 bg-slate-800/30 border-b border-slate-700/30 flex-shrink-0">
          <InfoCell label="开始时间" value={fmtTime(incident.startTime)} />
          <InfoCell label="持续时间" value={fmtDuration(incident.durationMs)} color={isActive ? 'amber' : 'emerald'} />
          <InfoCell label="影响 Agent" value={`${incident.affectedAgents.length} 个`} color="amber" />
          <InfoCell label="关联事件" value={`${incident.totalEvents} 条`} />
          <InfoCell label="当前状态" value={isActive ? '处理中' : '已恢复'} color={isActive ? 'red' : 'emerald'} />
        </div>

        {/* ══════════ REQUEST CONTROL BAR ═══════════════════════ */}
        <div className="flex items-center gap-3 px-5 py-2.5 border-b border-slate-700/30 bg-slate-800/20 flex-shrink-0">
          {isStopped && (
            <button onClick={startReplay} className="text-[11px] font-bold font-mono px-3 py-1.5 rounded-lg border border-cyan-500/40 bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20 transition-colors">
              ▶ 开始复盘
            </button>
          )}
          {isPlaying && (
            <button onClick={pauseReplay} className="text-[11px] font-bold font-mono px-3 py-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors">
              ⏸ 暂停
            </button>
          )}
          {isPaused && (
            <button onClick={resumeReplay} className="text-[11px] font-bold font-mono px-3 py-1.5 rounded-lg border border-cyan-500/40 bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20 transition-colors">
              ▶ 继续
            </button>
          )}
          {!isStopped && (
            <button onClick={stopReplay} className="text-[11px] font-bold font-mono px-3 py-1.5 rounded-lg border border-red-500/30 bg-red-500/5 text-red-400 hover:bg-red-500/10 transition-colors">
              ■ 停止
            </button>
          )}

          <span className="w-px h-5 bg-slate-600/50" />

          <button onClick={stepBackward} disabled={isPlaying} className="text-[11px] font-mono px-2 py-1 rounded border border-slate-600/40 text-slate-400 hover:border-slate-500/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
            ◀◀
          </button>
          <button onClick={stepForward} disabled={isPlaying} className="text-[11px] font-mono px-2 py-1 rounded border border-slate-600/40 text-slate-400 hover:border-slate-500/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
            ▶▶
          </button>

          <span className="w-px h-5 bg-slate-600/50" />

          <span className="text-[9px] font-mono text-slate-500">速度</span>
          {([1, 2, 5] as ReplaySpeed[]).map((s) => (
            <button
              key={s}
              onClick={() => setReplaySpeed(s)}
              className={`text-[10px] font-mono px-2 py-0.5 rounded border transition-colors ${
                replaySpeed === s
                  ? 'border-cyan-500/50 text-cyan-400 bg-cyan-500/10'
                  : 'border-slate-600/30 text-slate-500 hover:border-slate-500/60'
              }`}
            >
              {s}×
            </button>
          ))}

          <span className="text-[9px] font-mono text-slate-500 ml-2">
            {replayIndex + 1} / {replayEvents.length}
          </span>

          {/* Progress bar */}
          <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden ml-2">
            <div
              className="h-full bg-cyan-500 rounded-full transition-all duration-300 shadow-[0_0_8px_rgba(6,182,212,0.4)]"
              style={{ width: `${Math.min(100, Math.max(0, replayProgress))}%` }}
            />
          </div>

          <label className="flex items-center gap-1 text-[9px] font-mono text-slate-500 cursor-pointer ml-2">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="w-3 h-3 accent-cyan-500"
            />
            自动跟随
          </label>
        </div>

        {/* ══════════ TAB BAR ═══════════════════════════════════ */}
        <div className="flex items-center gap-0 px-5 border-b border-slate-700/30 bg-slate-800/10 flex-shrink-0">
          {(['timeline', 'events', 'agents', 'risk'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`text-[10px] font-bold font-mono uppercase tracking-wider px-4 py-2 border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-cyan-400 text-cyan-400'
                  : 'border-transparent text-slate-500 hover:text-slate-300'
              }`}
            >
              {tab === 'timeline' && '⏱ 复盘时间线'}
              {tab === 'events' && '📋 事件流'}
              {tab === 'agents' && '🤖 Agent 激活'}
              {tab === 'risk' && '⚠ 风险演化'}
            </button>
          ))}
        </div>

        {/* ══════════ MAIN CONTENT ═══════════════════════════════ */}
        <div className="flex-1 min-h-0 overflow-hidden flex">
          {/* ── LEFT: Main content area ──────────────────────── */}
          <div className="flex-[3] min-w-0 flex flex-col">
            {activeTab === 'timeline' && (
              <div ref={timelineRef} className="flex-1 overflow-y-auto p-4 space-y-3">
                {/* Incident summary card */}
                <div className="p-4 rounded-xl border border-slate-700/40 bg-slate-800/40">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[9px] font-mono text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 px-1.5 py-0.5 rounded uppercase tracking-wider">
                      AI 根因分析
                    </span>
                  </div>
                  <p className="text-sm font-mono text-slate-200 leading-relaxed">{incident.summary}</p>
                  {incident.recommendations.length > 0 && (
                    <div className="mt-3 pt-2 border-t border-slate-700/30">
                      <span className="text-[9px] font-mono text-amber-400/80 block mb-1.5">处置建议</span>
                      {incident.recommendations.map((rec, i) => (
                        <div key={i} className="text-[11px] font-mono text-amber-400/70 leading-relaxed">· {rec}</div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Phase timeline */}
                {incident.phases.map((phase, idx) => {
                  const isCurrent =
                    replayMode !== 'stopped' &&
                    replayEvents[replayIndex]?.id === phase.event.id
                  return (
                    <div
                      key={`${phase.phase}-${idx}`}
                      data-active={isCurrent ? 'true' : 'false'}
                      className={`relative pl-6 border-l-2 ${
                        isCurrent
                          ? 'border-cyan-400 shadow-[0_0_16px_rgba(6,182,212,0.2)]'
                          : 'border-slate-700/50'
                      } py-2`}
                    >
                      {/* Phase dot */}
                      <span
                        className={`absolute left-[-5px] top-3 w-2 h-2 rounded-full ${
                          isCurrent ? 'bg-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.6)]' : 'bg-slate-600'
                        }`}
                      />

                      {/* Phase label */}
                      <span
                        className="text-[9px] font-bold font-mono px-1.5 py-0.5 rounded border uppercase tracking-wider"
                        style={{
                          color: PHASE_COLORS[phase.phase],
                          borderColor: PHASE_COLORS[phase.phase] + '40',
                          backgroundColor: PHASE_COLORS[phase.phase] + '10',
                        }}
                      >
                        {PHASE_LABELS[phase.phase]}
                      </span>

                      {/* Timestamp */}
                      <span className="text-[10px] font-mono text-slate-500 ml-2">{fmtTime(phase.time)}</span>

                      {/* AI narrative */}
                      <p className={`text-sm font-mono mt-1.5 leading-relaxed ${
                        isCurrent ? 'text-cyan-200' : 'text-slate-300'
                      }`}>
                        {aiNarrativeText(phase.phase, phase.event)}
                      </p>

                      {/* Event detail */}
                      <div className={`mt-1 text-[10px] font-mono leading-snug ${
                        isCurrent ? 'text-cyan-400/60' : 'text-slate-500'
                      }`}>
                        Agent: {phase.event.agent.toUpperCase()} · {phase.event.category}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {activeTab === 'events' && (
              <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
                {incident.events.map((ev) => {
                  const isCurrent = replayMode !== 'stopped' && currentReplayEvent?.id === ev.id
                  return (
                    <div
                      key={ev.id}
                      className={`p-2.5 rounded-lg border transition-all ${
                        isCurrent
                          ? 'border-cyan-500/40 bg-cyan-500/10 shadow-[0_0_8px_rgba(6,182,212,0.15)]'
                          : 'border-slate-700/30 bg-slate-800/30'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          ev.level === 'ERROR' ? 'bg-red-400' : ev.level === 'WARN' ? 'bg-amber-400' : 'bg-slate-500'
                        }`} />
                        <span className="text-[10px] font-mono text-slate-400">{fmtTime(ev.timestamp)}</span>
                        <span className="text-[10px] font-mono text-slate-600 bg-slate-700/50 px-1 rounded">{ev.agent}</span>
                        <span className="text-[10px] font-mono text-slate-500">{ev.category}</span>
                      </div>
                      <div className={`text-xs font-mono ${isCurrent ? 'text-cyan-200' : 'text-slate-300'} leading-snug`}>
                        {ev.title}
                      </div>
                      <div className="text-[10px] font-mono text-slate-500 leading-snug mt-0.5">
                        {ev.detail}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {activeTab === 'agents' && (
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                <div className="text-[10px] font-mono text-slate-500 mb-2">
                  事故期间被激活的 Agent ({incidentAgents.length})
                </div>
                {incidentAgents.length === 0 && (
                  <div className="text-xs font-mono text-slate-600 italic">无匹配 Agent 数据</div>
                )}
                {incidentAgents.map((a) => {
                  const isError = a.state === 'ERROR'
                  const isActive = a.state !== 'IDLE' && a.state !== 'ERROR'
                  return (
                    <div
                      key={a.agent}
                      className={`p-4 rounded-xl border ${
                        isError
                          ? 'border-red-500/30 bg-red-500/5'
                          : isActive
                            ? 'border-cyan-500/20 bg-cyan-500/5'
                            : 'border-slate-700/30 bg-slate-800/20'
                      }`}
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <span
                          className={`w-2.5 h-2.5 rounded-full ${
                            isError ? 'bg-red-400 shadow-[0_0_8px_rgba(239,68,68,0.5)]' :
                            isActive ? 'bg-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.5)]' : 'bg-slate-500'
                          }`}
                        />
                        <span className="text-sm font-bold font-mono text-slate-200">{a.agent.toUpperCase()}</span>
                        <span className="text-[10px] font-mono text-slate-500 bg-slate-700/50 px-1.5 py-0.5 rounded">
                          {a.state}
                        </span>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-[9px] font-mono text-slate-400">
                        <span>状态: {a.state}</span>
                        <span>更新: {new Date(a.updatedAt).toLocaleTimeString('zh-CN', { hour12: false })}</span>
                        <span className={isError ? 'text-red-400' : 'text-emerald-400'}>
                          {isError ? '需关注' : '运行中'}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {activeTab === 'risk' && (
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                <div className="text-[10px] font-mono text-slate-500 mb-2">
                  事故期间风险状态演化
                </div>
                <div className="grid grid-cols-4 gap-3 mb-3">
                  <RiskMiniCard
                    label="错误事件" value={incident.events.filter((e) => e.level === 'ERROR').length}
                    color="red"
                  />
                  <RiskMiniCard
                    label="警告事件" value={incident.events.filter((e) => e.level === 'WARN').length}
                    color="amber"
                  />
                  <RiskMiniCard
                    label="止损触发" value={incident.events.filter((e) => e.category === 'stoploss').length}
                    color="orange"
                  />
                  <RiskMiniCard
                    label="恢复操作" value={incident.events.filter((e) => e.category === 'recovery').length}
                    color="emerald"
                  />
                </div>

                {riskEvolution.map((ev, idx) => {
                  const isCurrent = replayMode !== 'stopped' && currentReplayEvent?.id === ev.id
                  return (
                    <div
                      key={`risk-${ev.id}-${idx}`}
                      className={`p-3 rounded-lg border transition-all ${
                        isCurrent
                          ? 'border-cyan-500/30 bg-cyan-500/5 shadow-[0_0_8px_rgba(6,182,212,0.1)]'
                          : 'border-slate-700/30 bg-slate-800/20'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`w-2 h-2 rounded-full ${
                          ev.category === 'stoploss' ? 'bg-orange-400' :
                          ev.category === 'drawdown' ? 'bg-red-400' :
                          ev.category === 'recovery' ? 'bg-emerald-400' :
                          ev.level === 'ERROR' ? 'bg-red-400' : 'bg-amber-400'
                        }`} />
                        <span className="text-[10px] font-mono text-slate-400">{fmtTime(ev.timestamp)}</span>
                        <span className="text-[10px] font-mono text-slate-600 bg-slate-700/50 px-1 rounded">
                          {ev.category}
                        </span>
                      </div>
                      <div className={`text-xs font-mono ${isCurrent ? 'text-cyan-200' : 'text-slate-300'} leading-snug`}>
                        {ev.title}
                      </div>
                      <div className="text-[10px] font-mono text-slate-500 leading-snug mt-0.5">
                        {ev.detail}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* ── RIGHT: Current event detail ──────────────────── */}
          {replayMode !== 'stopped' && currentReplayEvent && (
            <div className="w-72 border-l border-slate-700/30 bg-slate-800/20 flex-shrink-0 p-4 flex flex-col">
              <span className="text-[9px] font-mono text-cyan-400/60 uppercase tracking-wider mb-3">
                当前复盘事件
              </span>
              <div className="flex-1 space-y-3">
                <div>
                  <span className="text-[8px] font-mono text-slate-500 block">时间</span>
                  <span className="text-xs font-mono text-slate-300">{fmtTime(currentReplayEvent.timestamp)}</span>
                </div>
                <div>
                  <span className="text-[8px] font-mono text-slate-500 block">Agent</span>
                  <span className="text-xs font-mono text-cyan-400">{currentReplayEvent.agent.toUpperCase()}</span>
                </div>
                <div>
                  <span className="text-[8px] font-mono text-slate-500 block">事件级别</span>
                  <span className={`text-xs font-mono font-bold ${
                    currentReplayEvent.level === 'ERROR' ? 'text-red-400' :
                    currentReplayEvent.level === 'WARN' ? 'text-amber-400' : 'text-slate-400'
                  }`}>
                    {currentReplayEvent.level}
                  </span>
                </div>
                <div>
                  <span className="text-[8px] font-mono text-slate-500 block">分类</span>
                  <span className="text-xs font-mono text-slate-300">{currentReplayEvent.category}</span>
                </div>
                <div>
                  <span className="text-[8px] font-mono text-slate-500 block">标题</span>
                  <span className="text-xs font-mono text-slate-200 leading-snug">{currentReplayEvent.title}</span>
                </div>
                <div>
                  <span className="text-[8px] font-mono text-slate-500 block">详情</span>
                  <span className="text-xs font-mono text-slate-400 leading-snug">{currentReplayEvent.detail}</span>
                </div>
              </div>
              <div className="text-[9px] font-mono text-slate-600 text-right">
                {replayIndex + 1} / {replayEvents.length}
              </div>
            </div>
          )}
        </div>

        {/* ══════════ BOTTOM STATUS BAR ════════════════════════ */}
        <div className="flex items-center justify-between px-5 py-2 border-t border-slate-700/30 bg-slate-800/40 flex-shrink-0 text-[9px] font-mono text-slate-500">
          <span>
            事故 ID: {incident.id} · {incident.totalEvents} 条事件 · {incident.affectedAgents.length} 个 Agent 受影响
          </span>
          <span className="text-slate-600">
            {isPlaying ? '▶ 复盘进行中…' : isPaused ? '⏸ 已暂停' : '■ 就绪'}
          </span>
        </div>
      </div>
    </div>
  )
}

// ── Helper components ────────────────────────────────────────

function InfoCell({
  label, value, color,
}: {
  label: string; value: string; color?: string
}) {
  const colorClass =
    color === 'amber' ? 'text-amber-400' :
    color === 'red' ? 'text-red-400' :
    color === 'emerald' ? 'text-emerald-400' : 'text-slate-300'
  return (
    <div className="flex flex-col items-center py-2 px-2 border-r border-slate-700/20">
      <span className="text-[8px] font-mono text-slate-500 uppercase tracking-wider">{label}</span>
      <span className={`text-xs font-bold font-mono mt-0.5 ${colorClass}`}>{value}</span>
    </div>
  )
}

function RiskMiniCard({
  label, value, color,
}: {
  label: string; value: number; color: string
}) {
  const bg =
    color === 'red' ? 'bg-red-500/5 border-red-500/20' :
    color === 'amber' ? 'bg-amber-500/5 border-amber-500/20' :
    color === 'orange' ? 'bg-orange-500/5 border-orange-500/20' :
    'bg-emerald-500/5 border-emerald-500/20'
  const textColor =
    color === 'red' ? 'text-red-400' :
    color === 'amber' ? 'text-amber-400' :
    color === 'orange' ? 'text-orange-400' : 'text-emerald-400'
  return (
    <div className={`rounded-lg border ${bg} p-3 text-center`}>
      <span className="text-[8px] font-mono text-slate-500 uppercase block mb-1">{label}</span>
      <span className={`text-xl font-bold font-mono ${textColor}`}>{value}</span>
    </div>
  )
}