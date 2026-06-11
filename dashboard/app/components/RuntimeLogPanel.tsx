'use client'

import { useMemo, useRef, useState, useCallback, useEffect } from 'react'
import type { LogEvent } from '../hooks/useLogEvents'

// ── Helpers ──────────────────────────────────────────────

const LEVEL_STYLES: Record<string, { dot: string; text: string; badge: string }> = {
  ERROR: {
    dot: 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.6)]',
    text: 'text-red-400',
    badge: 'bg-red-500/15 text-red-400 border-red-500/30',
  },
  WARN: {
    dot: 'bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.5)]',
    text: 'text-amber-400',
    badge: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  },
  SUCCESS: {
    dot: 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.5)]',
    text: 'text-emerald-400',
    badge: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  },
  INFO: {
    dot: 'bg-sky-500 shadow-[0_0_6px_rgba(14,165,233,0.4)]',
    text: 'text-sky-400',
    badge: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  },
}

// Tags that trigger a 2s glow effect in presentation mode
const HIGH_VALUE_TAGS = new Set([
  'reconnect',
  'stoploss',
  'drawdown',
  'approve',
  'recovery',
  'high_confidence',
  'cycle_summary',
])

const TAG_LABELS: Record<string, string> = {
  stoploss: '止损',
  drawdown: '回撤',
  risk: '风控',
  error: '错误',
  timeout: '超时',
  reconnect: '重连',
  connection: '连接',
  recovery: '恢复',
  approve: '批准',
  reject: '拒绝',
  high_confidence: '高置信',
  cycle_summary: '周期汇总',
  cycle_start: '周期开始',
  signal_aggregation: '信号汇总',
  monitor_start: '监控启动',
  success: '成功',
  warning: '警告',
}

function tagLabel(tag: string): string {
  return TAG_LABELS[tag] ?? tag
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

function formatDate(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
  } catch {
    return ''
  }
}

// ── Glowing Row ─────────────────────────────────────────

function GlowingRow({
  ev,
  styles,
  glowIds,
  isPresent,
}: {
  ev: LogEvent
  styles: (typeof LEVEL_STYLES)[string]
  glowIds: Set<string>
  isPresent: boolean
}) {
  const isGlowing = isPresent && glowIds.has(ev.id)

  return (
    <div
      className={`flex items-start gap-2 px-2.5 rounded transition-all group py-1.5 ${
        isGlowing
          ? 'bg-cyan-500/10 border border-cyan-500/30 shadow-[0_0_12px_rgba(34,211,238,0.2)]'
          : 'hover:bg-slate-700/45'
      }`}
      style={{
        transitionProperty: 'background-color, border-color, box-shadow',
        transitionDuration: isGlowing ? '0.3s, 0.3s, 2s' : '0.15s',
      }}
    >
      {/* Level dot */}
      <div className="flex-shrink-0 mt-1">
        <div
          className={`rounded-full w-2 h-2 ${styles.dot} ${
            isGlowing ? 'animate-pulse' : ''
          }`}
        />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* Time */}
          <span
            className={`font-mono text-slate-400 flex-shrink-0 ${
              isPresent ? 'text-sm' : 'text-xs'
            }`}
          >
            {formatTime(ev.timestamp)}
          </span>
          {/* Agent */}
          <span
            className={`font-mono text-slate-200 bg-slate-700/60 px-1.5 py-0.5 rounded flex-shrink-0 ${
              isPresent ? 'text-xs' : 'text-xs'
            }`}
          >
            {ev.agent}
          </span>
          {/* Title */}
          <span
            className={`font-mono ${styles.text} leading-snug ${
              isPresent ? 'text-base' : 'text-sm'
            }`}
          >
            {ev.title}
          </span>
        </div>
        {/* Detail */}
        {ev.detail && ev.detail !== ev.title && (
          <div
            className="text-slate-300 font-mono mt-1 leading-snug text-xs line-clamp-2"
          >
            {ev.detail}
          </div>
        )}
        {/* Tags */}
        {ev.tags.length > 0 && (
          <div className="flex gap-1 mt-0.5 flex-wrap">
            {ev.tags.map((tag) => (
              <span
                key={tag}
                className={`font-mono px-1.5 py-0.5 rounded border ${styles.badge} ${
                  isPresent ? 'text-xs' : 'text-xs'
                }`}
              >
                {tagLabel(tag)}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Component ────────────────────────────────────────────

export default function RuntimeLogPanel({
  events,
  source,
  presentationMode = false,
}: {
  events: LogEvent[]
  source?: 'real' | 'fallback'
  presentationMode?: boolean
}) {
  const [glowIds, setGlowIds] = useState<Set<string>>(new Set())
  const glowTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  // ── Auto-glow for high-value events ──────────────────
  const scheduleHighValueGlow = useCallback(
    (incoming: LogEvent[]) => {
      if (!presentationMode) return

      for (const ev of incoming) {
        const isHighValue = ev.tags.some((t) => HIGH_VALUE_TAGS.has(t))
        if (!isHighValue) continue

        queueMicrotask(() => {
          setGlowIds((prev) => {
            if (prev.has(ev.id)) return prev
            const next = new Set(prev)
            next.add(ev.id)
            return next
          })

          const existing = glowTimersRef.current.get(ev.id)
          if (existing) {
            clearTimeout(existing)
            glowTimersRef.current.delete(ev.id)
          }

          const timer = setTimeout(() => {
            setGlowIds((prev) => {
              const next = new Set(prev)
              next.delete(ev.id)
              return next
            })
            glowTimersRef.current.delete(ev.id)
          }, 2000)

          glowTimersRef.current.set(ev.id, timer)
        })
      }
    },
    [presentationMode],
  )

  // Detect new high-value events when events change
  useEffect(() => {
    if (events.length === 0) return
    const recent = events.slice(0, 5)
    scheduleHighValueGlow(recent)
  }, [events, presentationMode, scheduleHighValueGlow])

  // Cleanup glow timers on unmount
  useEffect(() => {
    const timers = glowTimersRef.current
    return () => {
      for (const timer of timers.values()) {
        clearTimeout(timer)
      }
      timers.clear()
    }
  }, [])

  // ── Group events by date ──────────────────────────────
  const sections = useMemo(() => {
    const map = new Map<string, LogEvent[]>()
    for (const ev of events) {
      const key = formatDate(ev.timestamp)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(ev)
    }
    return Array.from(map.entries())
  }, [events])

  const isPresent = presentationMode

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className={`flex items-center justify-between mb-2 pb-1.5 border-b border-slate-700/50 flex-shrink-0 ${
          isPresent ? 'px-1' : ''
        }`}
      >
        <h2
          className={`font-bold font-mono text-slate-100 uppercase tracking-wider ${
            isPresent ? 'text-base' : 'text-sm'
          }`}
        >
          {isPresent ? '实时运行事件播报' : '实时运行日志'}
        </h2>
        <div className="flex items-center gap-2">
          {source === 'real' && (
            <span
              className={`font-bold font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/30 uppercase tracking-wider ${
                isPresent ? 'text-xs' : 'text-xs'
              }`}
            >
              REAL DATA
            </span>
          )}
          <span className={`font-mono text-slate-400 ${isPresent ? 'text-sm' : 'text-xs'}`}>
            {events.length} events
          </span>
        </div>
      </div>

      {/* Empty state */}
      {events.length === 0 && (
        <div className="flex items-center justify-center h-full">
          <span className="text-slate-400 font-mono text-sm">
            {source === 'real' ? 'No significant log events detected' : 'Waiting for log data...'}
          </span>
        </div>
      )}

      {/* Event list */}
      {events.length > 0 && (
        <div className="flex-1 overflow-y-auto overflow-x-hidden pr-1 space-y-1 presentation-scroll">
          {sections.map(([date, sectionEvents]) => (
            <div key={date}>
              <div
                className={`text-slate-300 py-1.5 px-1 sticky top-0 bg-slate-800/95 z-10 font-mono ${
                  isPresent ? 'text-sm' : 'text-xs'
                }`}
              >
                ── {date} ──
              </div>
              {sectionEvents.map((ev) => {
                const styles = LEVEL_STYLES[ev.level] ?? LEVEL_STYLES.INFO
                return (
                  <GlowingRow
                    key={ev.id}
                    ev={ev}
                    styles={styles}
                    glowIds={glowIds}
                    isPresent={isPresent}
                  />
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
