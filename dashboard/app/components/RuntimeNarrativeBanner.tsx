'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRuntimeNarrative } from '../hooks/useRuntimeNarrative'
import type { NarrativeItem } from '../hooks/useRuntimeNarrative'
import type { LogEvent } from '../hooks/useLogEvents'
import type { AgentRuntimeStatus } from '../data/types'
import type { Incident } from '../hooks/useIncidents'
import type { DashboardKpis } from '../hooks/useDashboardSummary'

// ── Config ─────────────────────────────────────────────────

const ROTATE_INTERVAL_MS = 6000
const FADE_DURATION_MS = 300

// ── Priority styling ──────────────────────────────────────

const PRIORITY_STYLES: Record<
  NarrativeItem['priority'],
  { border: string; dot: string; label: string; labelColor: string }
> = {
  critical: {
    border: 'border-l-red-500',
    dot: 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.7)]',
    label: 'CRITICAL',
    labelColor: 'text-red-400 bg-red-500/10 border-red-500/30',
  },
  high: {
    border: 'border-l-amber-500',
    dot: 'bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.6)]',
    label: 'HIGH',
    labelColor: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  },
  medium: {
    border: 'border-l-cyan-500',
    dot: 'bg-cyan-400',
    label: 'INFO',
    labelColor: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
  },
  low: {
    border: 'border-l-slate-600',
    dot: 'bg-slate-500',
    label: 'STATUS',
    labelColor: 'text-slate-400 bg-slate-500/10 border-slate-500/30',
  },
}

const CATEGORY_ICONS: Record<NarrativeItem['category'], string> = {
  incident: '⚡',
  risk: '⚠',
  runtime: '⚙',
  regime: '◉',
  agent: '◈',
  correlation: '∿',
  health: '✓',
}

// ── Props ─────────────────────────────────────────────────

interface Props {
  events: LogEvent[]
  agentStates: AgentRuntimeStatus[]
  incidents: Incident[]
  kpis: DashboardKpis | null
  presentationMode?: boolean
  /** Executive mode: click on critical/high narrative opens Incident Command Center */
  onIncidentClick?: (incidentId: string) => void
  truthBadge?: React.ReactNode
}

// ── Dot progress indicator ────────────────────────────────

function NavDots({
  total,
  current,
  onSelect,
}: {
  total: number
  current: number
  onSelect: (i: number) => void
}) {
  return (
    <div className="flex items-center gap-1 flex-shrink-0">
      {Array.from({ length: total }).map((_, i) => (
        <button
          key={i}
          onClick={() => onSelect(i)}
          className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
            i === current ? 'bg-cyan-400 scale-125' : 'bg-slate-600 hover:bg-slate-500'
          }`}
          aria-label={`Switch to narrative ${i + 1}`}
        />
      ))}
    </div>
  )
}

// ── Main component ────────────────────────────────────────

export default function RuntimeNarrativeBanner({
  events,
  agentStates,
  incidents,
  kpis,
  presentationMode = false,
  onIncidentClick,
  truthBadge,
}: Props) {
  const { narratives, loading } = useRuntimeNarrative({
    events,
    agentStates,
    incidents,
    kpis,
  })

  const [idx, setIdx] = useState(0)
  const [visible, setVisible] = useState(true)
  const [showWhy, setShowWhy] = useState(false)

  // Reset index when narratives change
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset on data change
    setIdx(0)
  }, [narratives.length])

  const rotateTo = useCallback(
    (next: number) => {
      if (narratives.length <= 1) return
      setVisible(false)
      setTimeout(() => {
        setIdx(next % narratives.length)
        setShowWhy(false)
        setVisible(true)
      }, FADE_DURATION_MS)
    },
    [narratives.length],
  )

  const rotateNext = useCallback(() => {
    rotateTo((idx + 1) % Math.max(narratives.length, 1))
  }, [idx, narratives.length, rotateTo])

  const rotatePrev = useCallback(() => {
    rotateTo((idx - 1 + narratives.length) % Math.max(narratives.length, 1))
  }, [idx, narratives.length, rotateTo])

  // Auto-rotate
  useEffect(() => {
    if (narratives.length <= 1) return
    const id = setInterval(rotateNext, ROTATE_INTERVAL_MS)
    return () => clearInterval(id)
  }, [narratives.length, rotateNext])

  if (loading) {
    return (
      <div className="flex-shrink-0 h-8 bg-slate-800/40 border-b border-white/[0.04] flex items-center px-4">
        <span className="text-[9px] font-mono text-slate-600 animate-pulse">
          NARRATIVE ENGINE 初始化…
        </span>
      </div>
    )
  }

  if (narratives.length === 0) {
    return (
      <div className="flex-shrink-0 bg-slate-800/40 border-b border-white/[0.04] flex items-center px-4 py-1.5">
        <span className="text-[9px] font-mono text-slate-600">— 系统正常运行，无告警 —</span>
      </div>
    )
  }

  const item = narratives[idx]
  const styles = PRIORITY_STYLES[item.priority]
  const icon = CATEGORY_ICONS[item.category]

  // Extract incident ID from narrative when it's an incident narrative
  const linkedIncidentId =
    item.category === 'incident' && (item.priority === 'critical' || item.priority === 'high')
      ? item.id.startsWith('incident:')
        ? item.id.slice('incident:'.length)
        : null
      : null
  const isClickableIncident = Boolean(linkedIncidentId && onIncidentClick)

  const handleClick = useCallback(() => {
    if (linkedIncidentId && onIncidentClick) {
      onIncidentClick(linkedIncidentId)
    }
  }, [linkedIncidentId, onIncidentClick])

  return (
    <div
      className={`flex-shrink-0 border-b border-white/[0.06] bg-slate-900/60 border-l-2 ${styles.border} transition-all duration-200 ${
        isClickableIncident ? 'cursor-pointer hover:bg-slate-800/60 hover:brightness-110 group clickable-incident' : ''
      }`}
      onClick={isClickableIncident ? handleClick : undefined}
      title={isClickableIncident ? '点击打开事故指挥中心' : undefined}
      role={isClickableIncident ? 'button' : undefined}
      tabIndex={isClickableIncident ? 0 : undefined}
      onKeyDown={isClickableIncident ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleClick() } } : undefined}
    >
      {/* Main row */}
      <div
        className={`flex items-center gap-3 px-4 transition-opacity duration-300 ${
          presentationMode ? 'py-2.5' : 'py-1.5'
        } ${visible ? 'opacity-100' : 'opacity-0'}`}
      >
        {/* Truth Badge (compact) */}
        {truthBadge && <div className="mr-1 scale-75 origin-left">{truthBadge}</div>}
        {/* Priority dot */}
        <div
          className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${styles.dot} ${
            item.priority === 'critical' ? 'animate-pulse' : ''
          }`}
        />

        {/* Priority + category badge */}
        <span
          className={`text-[8px] font-bold font-mono px-1.5 py-0.5 rounded border flex-shrink-0 ${styles.labelColor}`}
        >
          {styles.label}
        </span>

        {/* Category icon */}
        <span className="text-[10px] text-slate-500 flex-shrink-0">{icon}</span>

        {/* Headline */}
        <span
          className={`font-mono font-medium flex-1 min-w-0 truncate leading-tight ${
            presentationMode ? 'text-sm text-slate-100' : 'text-[11px] text-slate-200'
          } ${isClickableIncident ? 'group-hover:text-white group-hover:underline decoration-amber-500/30' : ''}`}
        >
          {item.headline}
        </span>

        {/* Click indicator for clickable incidents */}
        {isClickableIncident && (
          <span className="text-[8px] font-mono text-amber-500/60 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
            → 指挥中心
          </span>
        )}

        {/* Data chips */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {item.dataRef.slice(0, 3).map((ref, i) => (
            <span
              key={i}
              className="text-[8px] font-mono text-slate-500 bg-slate-800/60 border border-slate-700/40 px-1.5 py-0.5 rounded"
            >
              {ref}
            </span>
          ))}
        </div>

        {/* Why button (AI Explain Layer) */}
        {item.whyDetail && (
          <button
            onClick={() => setShowWhy((v) => !v)}
            className={`text-[8px] font-mono px-1.5 py-0.5 rounded border flex-shrink-0 transition-colors ${
              showWhy
                ? 'text-violet-400 bg-violet-500/10 border-violet-500/30'
                : 'text-slate-600 border-slate-700/40 hover:text-slate-400 hover:border-slate-600/50'
            }`}
            title="显示推导依据"
          >
            ? 为什么
          </button>
        )}

        {/* Nav controls */}
        {narratives.length > 1 && (
          <div className="flex items-center gap-1 flex-shrink-0 ml-1">
            <button
              onClick={rotatePrev}
              className="text-[9px] text-slate-600 hover:text-slate-400 px-0.5"
              aria-label="Previous narrative"
            >
              ‹
            </button>
            <NavDots total={Math.min(narratives.length, 8)} current={idx} onSelect={rotateTo} />
            <button
              onClick={rotateNext}
              className="text-[9px] text-slate-600 hover:text-slate-400 px-0.5"
              aria-label="Next narrative"
            >
              ›
            </button>
            <span className="text-[8px] font-mono text-slate-600 ml-1">
              {idx + 1}/{narratives.length}
            </span>
          </div>
        )}
      </div>

      {/* Why detail row — AI Explain Layer */}
      {showWhy && item.whyDetail && (
        <div
          className={`border-t border-violet-500/10 bg-violet-500/5 px-4 py-1.5 ${
            visible ? 'opacity-100' : 'opacity-0'
          }`}
        >
          <div className="flex items-start gap-2">
            <span className="text-[8px] font-bold font-mono text-violet-400 flex-shrink-0 mt-0.5 uppercase tracking-wider">
              推导依据
            </span>
            <span className="text-[10px] font-mono text-slate-300 leading-snug">{item.whyDetail}</span>
          </div>
        </div>
      )}

      {/* Detail row (always visible below headline) */}
      {item.detail && visible && !showWhy && (
        <div className="px-4 pb-1 flex items-center gap-2">
          <span className="text-[8px] font-mono text-slate-500 leading-snug">{item.detail}</span>
        </div>
      )}
    </div>
  )
}
