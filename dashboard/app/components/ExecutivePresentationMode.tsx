'use client'

import { useEffect, useRef, useCallback, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { DashboardKpis } from '../hooks/useDashboardSummary'
import type { DrillDownTarget } from './ExecutiveKpiCards'
import type { Incident } from '../hooks/useIncidents'

// ── Types ─────────────────────────────────────────────────

interface Props {
  /** Controls */
  isActive: boolean
  onExit: () => void

  /** Data inputs */
  kpis: DashboardKpis | null
  incidents: Incident[]
  hasHighVol: boolean
  isHighCorrelation: boolean
  activeIncidentId: string | null

  /** Callbacks for auto-navigation */
  onDrillDown: (target: DrillDownTarget) => void
  onSpotlightSection: (sectionId: string) => void
  onHighlightIncident: (id: string) => void

  /** Children (the actual page content) */
  children: React.ReactNode
}

// ── Presentation sections for auto-rotation ────────────────

const NARRATIVE_SECTIONS = [
  { id: 'demo-kpi', label: '核心 KPI', duration: 15000 },
  { id: 'demo-copilot', label: 'AI Copilot', duration: 12000 },
  { id: 'demo-flow', label: '因果链', duration: 12000 },
  { id: 'demo-business', label: '商业影响', duration: 15000 },
  { id: 'demo-response', label: '响应行动', duration: 12000 },
  { id: 'demo-confidence', label: '运行时置信度', duration: 10000 },
  { id: 'demo-topology', label: 'Agent 协同网络', duration: 15000 },
  { id: 'demo-roi', label: 'ROI 面板', duration: 10000 },
  { id: 'demo-dryrun', label: '验证', duration: 8000 },
]

const DRILL_DOWNS: DrillDownTarget[] = ['approval', 'stability', 'volatility', 'signals', 'risk', 'automation']

// ── Component ─────────────────────────────────────────────

export default function ExecutivePresentationMode({
  isActive,
  onExit,
  kpis,
  incidents,
  hasHighVol,
  isHighCorrelation,
  activeIncidentId,
  onDrillDown,
  onSpotlightSection,
  onHighlightIncident,
  children,
}: Props) {
  // ── State ───────────────────────────────────────────────
  const [currentSectionIdx, setCurrentSectionIdx] = useState(0)
  const [currentDrillIdx, setCurrentDrillIdx] = useState(0)
  const [isDrillDownOpen, setIsDrillDownOpen] = useState(false)
  const [spotlightKpiIdx, setSpotlightKpiIdx] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [idleAnim, setIdleAnim] = useState<'pulse-kpi' | 'pulse-flow' | 'pulse-topology' | null>(null)

  const narrativeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const drillTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const spotlightTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const idleTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Active incident detection ───────────────────────────
  const activeIncidents = useMemo(
    () => incidents.filter((i) => !i.resolvedTime),
    [incidents],
  )
  const hasActiveIncident = activeIncidents.length > 0

  const nextIncidentsRef = useRef(0)

  // ── Cleanup ─────────────────────────────────────────────
  const cleanupTimers = useCallback(() => {
    if (narrativeTimerRef.current) { clearInterval(narrativeTimerRef.current); narrativeTimerRef.current = null }
    if (drillTimerRef.current) { clearInterval(drillTimerRef.current); drillTimerRef.current = null }
    if (spotlightTimerRef.current) { clearInterval(spotlightTimerRef.current); spotlightTimerRef.current = null }
    if (idleTimerRef.current) { clearInterval(idleTimerRef.current); idleTimerRef.current = null }
    if (elapsedTimerRef.current) { clearInterval(elapsedTimerRef.current); elapsedTimerRef.current = null }
  }, [])

  // ── Section rotation ────────────────────────────────────
  const rotateSection = useCallback(() => {
    setCurrentSectionIdx((prev) => {
      // If active incident, auto-spotlight the confidence section
      if (hasActiveIncident && activeIncidents.length > 0) {
        const idx = nextIncidentsRef.current % activeIncidents.length
        onHighlightIncident(activeIncidents[idx].id)
        nextIncidentsRef.current = idx + 1
        return prev
      }

      // If high volatility, prefer risk/business sections
      if (hasHighVol && prev % 4 !== 0) {
        // Bias toward demo-business
        return NARRATIVE_SECTIONS.findIndex((s) => s.id === 'demo-business')
      }

      return (prev + 1) % NARRATIVE_SECTIONS.length
    })
  }, [hasActiveIncident, activeIncidents, hasHighVol, onHighlightIncident])

  const rotateDrillDown = useCallback(() => {
    setIsDrillDownOpen(true)
    setCurrentDrillIdx((prev) => {
      const next = (prev + 1) % DRILL_DOWNS.length
      onDrillDown(DRILL_DOWNS[next])
      return next
    })
  }, [onDrillDown])

  const rotateSpotlight = useCallback(() => {
    setSpotlightKpiIdx((prev) => (prev + 1) % 6)
  }, [])

  const rotateIdleAnimation = useCallback(() => {
    const idles: Array<'pulse-kpi' | 'pulse-flow' | 'pulse-topology'> = ['pulse-kpi', 'pulse-flow', 'pulse-topology']
    setIdleAnim((prev) => {
      const idx = idles.indexOf(prev as typeof idles[0])
      return idles[(idx + 1) % idles.length]
    })
  }, [])

  // ── Activate presentation ───────────────────────────────
  useEffect(() => {
    if (!isActive) {
      cleanupTimers()
      return
    }

    // Highlight first
    onSpotlightSection(NARRATIVE_SECTIONS[0].id)

    // Narrative rotation every 15s
    narrativeTimerRef.current = setInterval(rotateSection, 15000)

    // Drill-down rotation every 12s
    drillTimerRef.current = setInterval(rotateDrillDown, 12000)

    // KPI spotlight every 10s
    spotlightTimerRef.current = setInterval(rotateSpotlight, 10000)

    // Idle animation every 8s
    idleTimerRef.current = setInterval(rotateIdleAnimation, 8000)

    // Elapsed time
    elapsedTimerRef.current = setInterval(() => setElapsed((p) => p + 1), 1000)

    return () => cleanupTimers()
  }, [isActive, rotateSection, rotateDrillDown, rotateSpotlight, rotateIdleAnimation, onSpotlightSection, cleanupTimers])

  // ── Spotlight the current section ───────────────────────
  useEffect(() => {
    if (!isActive) return
    const section = NARRATIVE_SECTIONS[currentSectionIdx]
    if (section) onSpotlightSection(section.id)
  }, [currentSectionIdx, isActive, onSpotlightSection])

  // ── Spotlight KPI ───────────────────────────────────────
  const kpiNames = useMemo(() => ['审批通过率', '运行时稳定性', '市场波动率', '信号吞吐', '风险响应', '自动化率'] as const, [])

  // ── Elapsed display ─────────────────────────────────────
  const elapsedStr = useMemo(() => {
    const m = Math.floor(elapsed / 60)
    const s = elapsed % 60
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }, [elapsed])

  if (!isActive) return <>{children}</>

  return (
    <div className="relative">
      {/* ── Presentation Header ───────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex-shrink-0 bg-gradient-to-r from-slate-900/90 via-slate-800/80 to-slate-900/90 border-b border-cyan-500/20 px-6 py-3 flex items-center justify-between backdrop-blur-xl relative z-50"
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_12px_rgba(34,211,238,0.5)]" />
            <span className="text-sm font-bold font-mono text-cyan-300 uppercase tracking-[0.2em]">
              AI Runtime Command Center
            </span>
            <span className="text-[10px] font-mono text-slate-500 border border-slate-700/50 px-2 py-0.5 rounded-full">
              PRESENTATION
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Current section */}
          <span className="text-[10px] font-mono text-slate-400">
            ↑ {NARRATIVE_SECTIONS[currentSectionIdx]?.label || 'Overview'}
          </span>

          {/* KPI spotlight */}
          <span className="text-[10px] font-mono text-violet-400 bg-violet-500/10 border border-violet-500/20 px-2 py-0.5 rounded">
            ◎ {kpiNames[spotlightKpiIdx]}
          </span>

          {/* Active incident indicator */}
          {hasActiveIncident && (
            <span className="text-[10px] font-bold font-mono text-amber-400 bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 rounded animate-pulse">
              ⚡ {activeIncidents.length} 事故进行中
            </span>
          )}

          {/* High volatility indicator */}
          {hasHighVol && (
            <span className="text-[10px] font-mono text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded">
              ▲ 高波动
            </span>
          )}

          {/* Elapsed */}
          <span className="text-[10px] font-mono text-slate-500 tabular-nums">
            {elapsedStr}
          </span>

          {/* Exit button */}
          <button
            onClick={onExit}
            className="text-[10px] font-mono text-slate-400 hover:text-white px-3 py-1.5 rounded border border-slate-600/50 hover:border-slate-500 hover:bg-slate-700/50 transition-all"
          >
            退出演示
          </button>
        </div>
      </motion.div>

      {/* ── Content with enhanced styling ─────────────────── */}
      <motion.div
        className="presentation-content"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
      >
        <div
          className={`presentation-stage ${
            idleAnim === 'pulse-kpi'
              ? 'presentation-idle-kpi'
              : idleAnim === 'pulse-flow'
              ? 'presentation-idle-flow'
              : 'presentation-idle-topology'
          }`}
        >
          {children}
        </div>
      </motion.div>

      {/* ── Presentation legend bar ───────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex-shrink-0 bg-slate-900/60 border-t border-cyan-500/10 px-4 py-1.5 flex items-center justify-center gap-6"
      >
        <span className="text-[8px] font-mono text-slate-600">
          演示模式自动轮播中 · 每15s 切换视图 · 每12s 专项分析
        </span>
        <span className="text-[8px] font-mono text-slate-600">
          {hasActiveIncident ? '⚠ 事故聚焦模式已激活' : '系统运行正常'}
        </span>
        <span className="text-[8px] font-mono text-slate-600">
          {hasHighVol ? '高波动 — 风险策略收紧' : '波动率正常'}
        </span>
      </motion.div>
    </div>
  )
}