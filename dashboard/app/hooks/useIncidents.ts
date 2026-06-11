'use client'

import { useMemo, useState, useCallback, useRef, useEffect } from 'react'
import type { LogEvent } from './useLogEvents'

// ═══════════════════════════════════════════════════════════
// useIncidents — Incident 聚合 + Replay 引擎
// ═══════════════════════════════════════════════════════════

export type IncidentSeverity = 'critical' | 'high' | 'medium' | 'low'

export type IncidentPhase =
  | 'start'
  | 'escalation'
  | 'mitigation'
  | 'recovery'
  | 'resolved'

export interface IncidentPhaseEvent {
  phase: IncidentPhase
  time: string
  title: string
  event: LogEvent
}

export interface Incident {
  id: string
  title: string
  severity: IncidentSeverity
  summary: string
  startTime: string
  resolvedTime: string | null
  durationMs: number
  affectedAgents: string[]
  totalEvents: number
  phases: IncidentPhaseEvent[]
  events: LogEvent[]
  recommendations: string[]
  tags: string[]
}

// ═══════════════════════════════════════════════════════════
// Phase classifier — maps event categories to timeline phases
// ═══════════════════════════════════════════════════════════

function classifyPhase(ev: LogEvent): IncidentPhase {
  const t = (ev.title + ' ' + ev.detail).toLowerCase()

  // Recovery & resolution
  if (
    t.includes('recovery') ||
    t.includes('recovered') ||
    t.includes('restore') ||
    t.includes('resolved') ||
    t.includes('normal') ||
    t.includes('healthy') ||
    ev.category === 'recovery'
  ) {
    return 'recovery'
  }

  // Mitigation
  if (
    t.includes('mitigat') ||
    t.includes('fallback') ||
    t.includes('retry') ||
    t.includes('reconnect success') ||
    t.includes('reconnect success') ||
    t.includes('auto reconnect') ||
    t.includes('switch') ||
    t.includes('reroute')
  ) {
    return 'mitigation'
  }

  // Escalation
  if (
    t.includes('escalat') ||
    t.includes('worsen') ||
    t.includes('degrade') ||
    t.includes('spread') ||
    t.includes('cascade')
  ) {
    return 'escalation'
  }

  // Start (default for trigger events)
  if (
    ev.level === 'ERROR' ||
    ev.category === 'stoploss' ||
    ev.category === 'drawdown' ||
    ev.category === 'connection' ||
    t.includes('timeout') ||
    t.includes('disconnect')
  ) {
    return 'start'
  }

  return 'escalation'
}

// ═══════════════════════════════════════════════════════════
// Severity from levels + categories
// ═══════════════════════════════════════════════════════════

function computeSeverity(events: LogEvent[]): IncidentSeverity {
  const errorCount = events.filter((e) => e.level === 'ERROR').length
  const drawdown = events.some((e) => e.category === 'drawdown')
  const stoploss = events.some((e) => e.category === 'stoploss')

  if (drawdown && errorCount >= 3) return 'critical'
  if (stoploss && errorCount >= 2) return 'high'
  if (errorCount >= 3) return 'high'
  if (errorCount >= 1) return 'medium'
  return 'low'
}

// ═══════════════════════════════════════════════════════════
// AI Summary Generator — 中文事故总结
// ═══════════════════════════════════════════════════════════

function generateSummary(incident: {
  title: string
  severity: IncidentSeverity
  events: LogEvent[]
  startTime: string
  resolvedTime: string | null
  affectedAgents: string[]
}): string {
  const { title, severity, events, startTime, resolvedTime, affectedAgents } = incident
  const errorEvents = events.filter((e) => e.level === 'ERROR')
  const warnEvents = events.filter((e) => e.level === 'WARN')
  const recoveryEvents = events.filter((e) => e.category === 'recovery' || e.title.toLowerCase().includes('recover'))

  const startTs = new Date(startTime).toLocaleTimeString('zh-CN', { hour12: false })
  const endTs = resolvedTime
    ? new Date(resolvedTime).toLocaleTimeString('zh-CN', { hour12: false })
    : '至今'

  const severityLabel =
    severity === 'critical'
      ? '严重'
      : severity === 'high'
        ? '高'
        : severity === 'medium'
          ? '中'
          : '低'

  const parts: string[] = []
  parts.push(`【${severityLabel}严重程度事故】`)

  // Root cause
  const triggerTitle = events[0]?.title ?? title
  parts.push(`系统在 ${startTs} 检测到 ${triggerTitle}。`)

  // Escalation
  if (errorEvents.length + warnEvents.length > 1) {
    parts.push(`随后共产生 ${errorEvents.length} 条错误和 ${warnEvents.length} 条警告。`)
  }

  // Affected
  if (affectedAgents.length > 0) {
    const names = affectedAgents.map((a) => a.toUpperCase()).join('、')
    parts.push(`影响范围：${names}，共 ${events.length} 条异常事件。`)
  }

  // Recovery
  if (recoveryEvents.length > 0) {
    const recoveryTitle = recoveryEvents[0]?.title ?? '系统自动恢复'
    const recoveryTime = new Date(recoveryEvents[0]?.timestamp ?? '').toLocaleTimeString('zh-CN', { hour12: false })
    parts.push(`${recoveryTime} ${recoveryTitle}。`)
  } else if (resolvedTime) {
    parts.push(`${endTs} 事件已解决。`)
  }

  // Final state
  const result =
    resolvedTime
      ? `事故已于 ${endTs} 完全恢复，系统运行正常。`
      : '事故仍在处理中，建议持续观察。'

  parts.push(result)

  return parts.join('')
}

function generateRecommendations(events: LogEvent[]): string[] {
  const recs: string[] = []
  const text = events.map((e) => e.title + ' ' + e.detail).join(' ').toLowerCase()

  if (text.includes('ws') || text.includes('websocket') || text.includes('disconnect')) {
    recs.push('检查 WebSocket 连接稳定性，考虑切换备用接入点')
  }
  if (text.includes('timeout') || text.includes('latency')) {
    recs.push('审查 API 超时配置，增加连接超时重试机制')
  }
  if (text.includes('drawdown') || text.includes('stoploss')) {
    recs.push('收紧风险敞口控制参数，降低单笔仓位上限')
  }
  if (text.includes('reconnect') && text.includes('fail')) {
    recs.push('加强自动重连机制，增加 fallback provider 切换速度')
  }
  if (text.includes('rate limit') || text.includes('throttle')) {
    recs.push('优化请求频率控制，检查 API 配额使用情况')
  }
  if (text.includes('approve') || text.includes('reject')) {
    recs.push('审查信号审核规则，检查风险阈值是否合理')
  }

  if (recs.length === 0) {
    recs.push('排查系统日志，定位根本原因')
    recs.push('加强监控告警覆盖')
  }

  return recs.slice(0, 3)
}

// ═══════════════════════════════════════════════════════════
// Incident aggregation window (2 minutes)
// ═══════════════════════════════════════════════════════════

const INCIDENT_WINDOW_MS = 2 * 60 * 1000 // 2 minutes

function aggregateIncidents(events: LogEvent[]): Incident[] {
  if (events.length === 0) return []

  // Sort ascending by timestamp
  const sorted = [...events].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  )

  // Find trigger events
  const incidentTriggers = sorted.filter((e) => {
    const t = (e.title + ' ' + e.detail).toLowerCase()
    return (
      e.level === 'ERROR' ||
      e.level === 'WARN' ||
      e.category === 'stoploss' ||
      e.category === 'drawdown' ||
      t.includes('disconnect') ||
      t.includes('timeout')
    )
  })

  if (incidentTriggers.length === 0) return []

  // Group by time proximity
  const clusters: LogEvent[][] = []
  const used = new Set<string>()

  for (const trigger of incidentTriggers) {
    if (used.has(trigger.id)) continue

    const triggerTime = new Date(trigger.timestamp).getTime()
    const cluster: LogEvent[] = [trigger]
    used.add(trigger.id)

    // Collect nearby events within window
    for (const ev of sorted) {
      if (used.has(ev.id)) continue
      const evTime = new Date(ev.timestamp).getTime()
      if (Math.abs(evTime - triggerTime) <= INCIDENT_WINDOW_MS) {
        const t = (ev.title + ' ' + ev.detail).toLowerCase()
        // Only include related events (ERROR, WARN, recovery, connection, etc.)
        if (
          ev.level === 'ERROR' ||
          ev.level === 'WARN' ||
          ev.category === 'recovery' ||
          ev.category === 'connection' ||
          ev.category === 'stoploss' ||
          ev.category === 'drawdown' ||
          t.includes('reconnect') ||
          t.includes('timeout') ||
          t.includes('retry') ||
          t.includes('fallback') ||
          t.includes('switch') ||
          t.includes('degrade')
        ) {
          cluster.push(ev)
          used.add(ev.id)
        }
      }
    }

    if (cluster.length >= 1) {
      clusters.push(cluster)
    }
  }

  // Build incidents from clusters
  return clusters.map((cluster, idx) => {
    const sortedCluster = cluster.sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    )

    const startEvent = sortedCluster[0]
    const lastEvent = sortedCluster[sortedCluster.length - 1]
    const hasRecovery = sortedCluster.some(
      (e) =>
        e.category === 'recovery' ||
        e.title.toLowerCase().includes('recover') ||
        e.title.toLowerCase().includes('resolved'),
    )

    // Determine title from trigger
    let title = startEvent.title
    const cats = new Map<string, number>()
    for (const e of sortedCluster) cats.set(e.category, (cats.get(e.category) ?? 0) + 1)

    if ((cats.get('connection') ?? 0) >= 1) title = 'WS 连接中断事故'
    else if ((cats.get('stoploss') ?? 0) >= 1) title = '止损保护触发事故'
    else if ((cats.get('drawdown') ?? 0) >= 1) title = '回撤预警事故'
    else if (title.toLowerCase().includes('timeout')) title = '超时故障事故'
    else if (title.toLowerCase().includes('error')) title = '系统错误事故'

    const severity = computeSeverity(sortedCluster)
    const startTime = startEvent.timestamp
    const resolvedTime = hasRecovery ? lastEvent.timestamp : null
    const durationMs = hasRecovery
      ? new Date(lastEvent.timestamp).getTime() - new Date(startTime).getTime()
      : Date.now() - new Date(startTime).getTime()

    const affectedAgents = [...new Set(sortedCluster.map((e) => e.agent))]

    // Build phases
    const phases: IncidentPhaseEvent[] = sortedCluster.map((ev) => ({
      phase: classifyPhase(ev),
      time: ev.timestamp,
      title: ev.title,
      event: ev,
    }))

    // Check if we have resolution
    if (hasRecovery && !phases.some((p) => p.phase === 'resolved')) {
      const lastPhase = phases[phases.length - 1]
      if (lastPhase.phase === 'recovery') {
        phases.push({
          phase: 'resolved',
          time: lastPhase.time,
          title: '事故已解决',
          event: lastPhase.event,
        })
      }
    }

    const summary = generateSummary({
      title,
      severity,
      events: sortedCluster,
      startTime,
      resolvedTime,
      affectedAgents,
    })

    const recommendations = generateRecommendations(sortedCluster)

    return {
      id: `incident-${idx}-${startTime.slice(0, 10)}`,
      title,
      severity,
      summary,
      startTime,
      resolvedTime,
      durationMs,
      affectedAgents,
      totalEvents: sortedCluster.length,
      phases,
      events: sortedCluster,
      recommendations,
      tags: [...new Set(sortedCluster.flatMap((e) => e.tags))],
    }
  })
}

// ═══════════════════════════════════════════════════════════
// Hook
// ═══════════════════════════════════════════════════════════

export function useIncidents(filteredEvents: LogEvent[]) {
  const incidents = useMemo(() => aggregateIncidents(filteredEvents), [filteredEvents])

  // ── Replay State ─────────────────────────────────────
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null)
  const [replayMode, setReplayMode] = useState<'stopped' | 'playing' | 'paused'>('stopped')
  const [replaySpeed, setReplaySpeed] = useState<1 | 2 | 5>(1)
  const [replayIndex, setReplayIndex] = useState(0)
  const [replayProgress, setReplayProgress] = useState(0)
  const replayRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const selectedIncident = useMemo(
    () => incidents.find((i) => i.id === selectedIncidentId) ?? null,
    [incidents, selectedIncidentId],
  )

  const replayEvents = useMemo(() => {
    if (!selectedIncident) return []
    return selectedIncident.events
  }, [selectedIncident])

  const currentReplayEvent = replayEvents[replayIndex] ?? null

  // ── Replay Controls ──────────────────────────────────
  const startReplay = useCallback(() => {
    setReplayIndex(0)
    setReplayProgress(0)
    setReplayMode('playing')
  }, [])

  const pauseReplay = useCallback(() => {
    setReplayMode('paused')
  }, [])

  const resumeReplay = useCallback(() => {
    setReplayMode('playing')
  }, [])

  const stopReplay = useCallback(() => {
    setReplayMode('stopped')
    setReplayIndex(0)
    setReplayProgress(0)
    if (replayRef.current) {
      clearInterval(replayRef.current)
      replayRef.current = null
    }
  }, [])

  const stepForward = useCallback(() => {
    setReplayIndex((prev) => {
      const next = Math.min(prev + 1, replayEvents.length - 1)
      setReplayProgress((next / Math.max(replayEvents.length - 1, 1)) * 100)
      return next
    })
  }, [replayEvents.length])

  const stepBackward = useCallback(() => {
    setReplayIndex((prev) => {
      const next = Math.max(prev - 1, 0)
      setReplayProgress((next / Math.max(replayEvents.length - 1, 1)) * 100)
      return next
    })
  }, [replayEvents.length])

  // Replay interval
  useEffect(() => {
    if (replayMode !== 'playing') {
      if (replayRef.current) {
        clearInterval(replayRef.current)
        replayRef.current = null
      }
      return
    }

    const intervalMs = replaySpeed === 1 ? 1200 : replaySpeed === 2 ? 600 : 240

    replayRef.current = setInterval(() => {
      setReplayIndex((prev) => {
        const next = prev + 1
        if (next >= replayEvents.length) {
          setReplayMode('stopped')
          return replayEvents.length - 1
        }
        setReplayProgress(((next + 1) / replayEvents.length) * 100)
        return next
      })
    }, intervalMs)

    return () => {
      if (replayRef.current) {
        clearInterval(replayRef.current)
        replayRef.current = null
      }
    }
  }, [replayMode, replaySpeed, replayEvents.length])

  return {
    incidents,
    selectedIncidentId,
    setSelectedIncidentId,
    selectedIncident,
    // Replay
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
  }
}