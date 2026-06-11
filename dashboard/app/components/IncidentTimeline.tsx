'use client'

import { useMemo } from 'react'
import type { Incident } from '../hooks/useIncidents'
import type { LogEvent } from '../hooks/useLogEvents'

// Local type aliases matching useIncidents runtime types
type ReplayMode = 'stopped' | 'playing' | 'paused'
type ReplaySpeed = 1 | 2 | 5

// ── Color mapping ────────────────────────────────────────

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#3b82f6',
}

const SEVERITY_LABELS: Record<string, string> = {
  critical: '严重',
  high: '高',
  medium: '中',
  low: '低',
}

type IncidentStatus = 'active' | 'resolved'

const STATUS_COLORS: Record<IncidentStatus, string> = {
  active: '#ef4444',
  resolved: '#22c55e',
}

const STATUS_LABELS: Record<IncidentStatus, string> = {
  active: '进行中',
  resolved: '已解决',
}

function deriveStatus(incident: Incident): IncidentStatus {
  return incident.resolvedTime ? 'resolved' : 'active'
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// ── AI Recovery Narrative ─────────────────────────────────

/** Generate a plausible AI recovery narrative from incident + replay events */
function generateAISummary(
  incident: Incident,
  replayEvents: LogEvent[],
  isReplaying: boolean,
): string {
  const sevLabel = SEVERITY_LABELS[incident.severity] ?? incident.severity
  const agentCount = incident.affectedAgents.length

  if (incident.resolvedTime) {
    const durationMs = new Date(incident.resolvedTime).getTime() - new Date(incident.startTime).getTime()
    const durationMin = Math.round(durationMs / 60_000)
    return `AI 复盘：${sevLabel}级事故已解决。影响 ${agentCount} 个 Agent，持续约 ${durationMin} 分钟。根因定位: ${incident.title}。恢复措施: ${incident.recommendations?.[0] ?? '自动故障转移成功'}。`
  }

  if (isReplaying) {
    const replayCount = replayEvents.length
    return `AI 实时分析：${sevLabel}级事故正在进行中。已重放 ${replayCount} 个关联事件。当前阶段: ${replayEvents[replayEvents.length - 1]?.category ?? '分析中'}。预计自动恢复剩余 2-3 周期。`
  }

  return `AI 诊断：${sevLabel}级事故待处理。影响 ${agentCount} 个 Agent。建议立即启动故障回放以定位根因。`
}

// ── Component ────────────────────────────────────────────

export default function IncidentTimeline({
  incidents,
  onSelectIncident,
  onIncidentClick,
  selectedId,
  // ── Replay props (optional for standalone use) ──────
  replayMode,
  replaySpeed,
  replayProgress,
  replayEvents = [],
  currentReplayEvent,
  startReplay,
  pauseReplay,
  resumeReplay,
  stopReplay,
  stepForward,
  stepBackward,
  setReplaySpeed,
  truthBadge,
}: {
  incidents: Incident[]
  onSelectIncident?: (incident: Incident) => void
  onIncidentClick?: (incidentId: string) => void
  selectedId?: string | null
  // Replay control
  replayMode?: ReplayMode
  replaySpeed?: ReplaySpeed
  replayProgress?: number
  replayEvents?: LogEvent[]
  currentReplayEvent?: LogEvent | null
  startReplay?: () => void
  pauseReplay?: () => void
  resumeReplay?: () => void
  stopReplay?: () => void
  stepForward?: () => void
  stepBackward?: () => void
  setReplaySpeed?: (speed: ReplaySpeed) => void
  truthBadge?: React.ReactNode
}) {
  const isReplaying = replayMode === 'playing'
  const isPaused = replayMode === 'paused'
  const isStopped = replayMode === 'stopped' || !replayMode
  const hasReplayControls = !!startReplay

  const selectedIncident = incidents.find((i) => i.id === selectedId) ?? null
  const aiSummary = selectedIncident
    ? generateAISummary(selectedIncident, replayEvents, isReplaying)
    : null
  // Sort: active first, then by startTime descending
  const sorted = useMemo(() => {
    return [...incidents].sort((a, b) => {
      const aIsActive = !a.resolvedTime
      const bIsActive = !b.resolvedTime
      if (aIsActive && !bIsActive) return -1
      if (!aIsActive && bIsActive) return 1
      return new Date(b.startTime).getTime() - new Date(a.startTime).getTime()
    })
  }, [incidents])

  if (sorted.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-[10px] font-mono text-slate-600">未检测到事故</span>
      </div>
    )
  }

  const speedOptions: ReplaySpeed[] = [1, 2, 5]

  return (
    <div className="flex flex-col h-full space-y-2 overflow-y-auto pr-1 relative">
      {truthBadge && <div className="absolute top-0 right-1 z-10">{truthBadge}</div>}
      {/* ── Replay Controls Bar ────────────────────── */}
      {hasReplayControls && (
        <div className="flex-shrink-0 bg-slate-800/50 border border-slate-700/40 rounded-lg p-2.5 space-y-2">
          {/* Title */}
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">回放控制</span>
            {isReplaying && (
              <span className="text-[9px] font-mono font-bold text-cyan-400 animate-pulse">
                ▶ 回放中
              </span>
            )}
            {isPaused && (
              <span className="text-[9px] font-mono font-bold text-amber-400">
                ⏸ 已暂停
              </span>
            )}
          </div>

          {/* Progress bar */}
          {replayProgress !== undefined && (
            <div className="h-1 rounded-full bg-slate-700 overflow-hidden">
              <div
                className="h-full bg-cyan-500 rounded-full transition-all duration-300"
                style={{ width: `${Math.min(100, Math.max(0, replayProgress))}%` }}
              />
            </div>
          )}

          {/* Current replay event */}
          {currentReplayEvent && (
            <div className="text-[9px] font-mono text-slate-400 truncate">
              <span className="text-slate-500">当前阶段: </span>
              <span className="text-cyan-400">{currentReplayEvent.category}</span>
              <span className="text-slate-600"> — {currentReplayEvent.detail}</span>
            </div>
          )}

          {/* Controls row 1: Play/Pause/Resume/Stop/Step */}
          <div className="flex items-center gap-1">
            {isStopped && (
              <button
                onClick={() => startReplay?.()}
                disabled={!selectedIncident}
                className="text-[9px] font-mono px-2 py-1 rounded border border-cyan-500/40 bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20 disabled:opacity-30 disabled:cursor-not-allowed"
                title="开始回放"
              >
                ▶ 开始
              </button>
            )}
            {isReplaying && (
              <button
                onClick={() => pauseReplay?.()}
                className="text-[9px] font-mono px-2 py-1 rounded border border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                title="暂停"
              >
                ⏸ 暂停
              </button>
            )}
            {isPaused && (
              <button
                onClick={() => resumeReplay?.()}
                className="text-[9px] font-mono px-2 py-1 rounded border border-cyan-500/40 bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20"
                title="继续"
              >
                ▶ 继续
              </button>
            )}
            {!isStopped && (
              <button
                onClick={() => stopReplay?.()}
                className="text-[9px] font-mono px-2 py-1 rounded border border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/20"
                title="停止"
              >
                ■ 停止
              </button>
            )}

            <div className="flex-1" />

            <button
              onClick={() => stepBackward?.()}
              disabled={!selectedIncident || isReplaying}
              className="text-[9px] font-mono px-1.5 py-1 rounded border border-slate-600/40 bg-slate-800/80 text-slate-400 hover:bg-slate-700/80 disabled:opacity-30 disabled:cursor-not-allowed"
              title="上一步"
            >
              ◀
            </button>
            <button
              onClick={() => stepForward?.()}
              disabled={!selectedIncident || isReplaying}
              className="text-[9px] font-mono px-1.5 py-1 rounded border border-slate-600/40 bg-slate-800/80 text-slate-400 hover:bg-slate-700/80 disabled:opacity-30 disabled:cursor-not-allowed"
              title="下一步"
            >
              ▶
            </button>
          </div>

          {/* Speed selector */}
          {setReplaySpeed && (
            <div className="flex items-center gap-1">
              <span className="text-[9px] font-mono text-slate-500 flex-shrink-0">回放速度:</span>
              {speedOptions.map((speed) => (
                <button
                  key={speed}
                  onClick={() => setReplaySpeed?.(speed)}
                  className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${
                    replaySpeed === speed
                      ? 'border-cyan-500/60 bg-cyan-500/20 text-cyan-400'
                      : 'border-slate-600/40 bg-slate-800/80 text-slate-400 hover:border-slate-500/60'
                  }`}
                >
                  {speed}x
                </button>
              ))}
            </div>
          )}

          {/* Progress percentage text */}
          {replayProgress !== undefined && (
            <div className="text-center text-[9px] font-mono text-slate-600">
              复盘进度: {Math.round(replayProgress)}%
            </div>
          )}
        </div>
      )}

      {/* ── AI Recovery Narrative ──────────────────── */}
      {aiSummary && (
        <div className="flex-shrink-0 bg-violet-500/5 border border-violet-500/20 rounded-lg p-2">
          <p className="text-xs font-mono text-slate-300 leading-relaxed">
            🤖 {aiSummary}
          </p>
        </div>
      )}

      {/* ── Incident Cards ────────────────────────── */}
      {sorted.map((incident) => {
        const status = deriveStatus(incident)
        const severityColor = SEVERITY_COLORS[incident.severity] ?? '#64748b'
        const statusColor = STATUS_COLORS[status] ?? '#64748b'
        const isSelected = selectedId === incident.id
        const isActive = status === 'active'
        const recommendation = incident.recommendations?.[0]

        return (
          <div
            key={incident.id}
            onClick={() => {
              onSelectIncident?.(incident)
              onIncidentClick?.(incident.id)
            }}
            className={`
              rounded-lg border px-3 py-2.5 cursor-pointer transition-all duration-200
              ${isSelected
                ? 'border-cyan-500/60 bg-cyan-500/10 shadow-[0_0_12px_rgba(6,182,212,0.2)]'
                : 'border-slate-700/60 bg-slate-900/80 hover:border-slate-600/60'
              }
            `}
          >
            {/* Header row */}
            <div className="flex items-center gap-2 mb-1">
              {/* Severity badge */}
              <span
                className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border uppercase"
                style={{
                  color: severityColor,
                  borderColor: severityColor + '40',
                  backgroundColor: severityColor + '10',
                }}
              >
                {SEVERITY_LABELS[incident.severity] ?? incident.severity}
              </span>

              {/* Status badge */}
              <span
                className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border"
                style={{
                  color: statusColor,
                  borderColor: statusColor + '40',
                  backgroundColor: statusColor + '10',
                }}
              >
                {STATUS_LABELS[status] ?? status}
              </span>

              {/* Active pulse */}
              {isActive && (
                <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse shadow-[0_0_6px_rgba(239,68,68,0.6)]" />
              )}
            </div>

            {/* Issue description (title) */}
            <div className="text-xs font-mono text-slate-200 leading-snug mb-1.5">
              {incident.title}
            </div>

            {/* Recommendation */}
            {recommendation && (
              <div className="text-[10px] font-mono text-amber-400/80 leading-snug mb-1.5 line-clamp-2">
                {recommendation}
              </div>
            )}

            {/* Footer: timestamp + affected agents count */}
            <div className="flex items-center justify-between text-[10px] font-mono text-slate-600">
              <span>{formatTimestamp(incident.startTime)}</span>
              <span>{incident.affectedAgents.length} agents</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}